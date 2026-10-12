"""Durable jobs bound to raw/context/taxonomy/model; provider injected explicitly."""
import json
import uuid
from datetime import timedelta
from engine.classification_input import build_batches,job_key,make_request
from src.acquisition.models import parse_utc,utcnow
from src.analysis.classification_contract import ContractError,validate_response
from src.storage.conversations import encode
from src.analysis.gemini_gateway import ProviderError


class ClassificationJobs:
    def __init__(self,raw,*,initialize=True):
        self.raw=raw
        if not initialize: return
        raw.db.executescript('''
          CREATE TABLE IF NOT EXISTS classification_jobs(
            job_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
            binding TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,lease_token TEXT,lease_until TEXT,error_code TEXT);
          CREATE TABLE IF NOT EXISTS node_analyses(
            job_id TEXT PRIMARY KEY REFERENCES classification_jobs(job_id),node_id TEXT NOT NULL,
            payload TEXT NOT NULL,validated_at TEXT NOT NULL);
        ''')
        raw.db.execute('CREATE INDEX IF NOT EXISTS classification_job_node ON classification_jobs(node_id)')
        if 'next_attempt_at' not in {r[1] for r in raw.db.execute('PRAGMA table_info(classification_jobs)')}:
            raw.db.execute('ALTER TABLE classification_jobs ADD COLUMN next_attempt_at TEXT')
            raw.db.commit()

    def enqueue(self,items,snapshot,model):
        if not model: raise ValueError('Model ID required')
        count=0
        with self.raw.transaction():
            for item in items:
                make_request([item],snapshot)
                key=job_key(item,snapshot,model)
                binding={'taxonomy':snapshot,'model':model}
                count+=self.raw.db.execute('INSERT OR IGNORE INTO classification_jobs(job_id,node_id,binding,payload,status) VALUES (?,?,?,?,?)',
                    (key,item['item_id'],encode(binding),encode(item),'PENDING')).rowcount
        return count

    def completed_item_ids(self, items, snapshot):
        """Reuse accepted results for identical inputs across provider model changes.

        Historical jobs retain their actual model. A new target/context/OCR,
        taxonomy, prompt or rule binding still requires fresh classification.
        Explicit enqueue remains available for intentional model comparisons.
        """
        wanted = {item['item_id']: item for item in items}
        completed = set()
        bindings = {}
        rows = self.raw.db.execute("""SELECT j.job_id,j.node_id,j.binding
            FROM classification_jobs j JOIN node_analyses a ON a.job_id=j.job_id AND a.node_id=j.node_id
            WHERE j.status='DONE'""")
        for row in rows:
            if row['node_id'] not in wanted or row['node_id'] in completed:
                continue
            binding = bindings.setdefault(row['binding'], None)
            if binding is None:
                binding = bindings[row['binding']] = json.loads(row['binding'])
            if binding['taxonomy'] == snapshot and row['job_id'] == job_key(wanted[row['node_id']], snapshot, binding['model']):
                completed.add(row['node_id'])
        return completed

    def _current(self,item):
        from src.storage.image_evidence import input_current
        return all(self.raw.get(n['item_id']) and self.raw.get(n['item_id'])['revision_id']==n['revision_id'] for n in [item,*item['context']]) and input_current(self.raw,item)

    def claim(self,snapshot,model,now,limit=10,lease_seconds=120,max_attempts=3,node_ids=None):
        if not 0 < limit <= 100 or min(lease_seconds,max_attempts)<=0: raise ValueError('Invalid worker limits')
        now=parse_utc(now); claimed=[]; token=uuid.uuid4().hex
        if node_ids is not None and (not isinstance(node_ids,list) or not 1<=len(node_ids)<=100 or any(not isinstance(n,str) or not n for n in node_ids)):
            raise ValueError('Invalid target node selection')
        with self.raw.transaction():
            rows=self.raw.db.execute("SELECT * FROM classification_jobs WHERE (status='PENDING' AND (next_attempt_at IS NULL OR next_attempt_at<=?)) OR (status='RUNNING' AND lease_until<=?) ORDER BY rowid",(now.isoformat(),now.isoformat())).fetchall()
            for row in rows:
                if node_ids is not None and row['node_id'] not in node_ids:continue
                item=json.loads(row['payload']); binding=json.loads(row['binding'])
                if binding!={'taxonomy':snapshot,'model':model}: continue
                status='STALE' if not self._current(item) or row['job_id']!=job_key(item,snapshot,model) else 'FAILED' if row['attempts']>=max_attempts else None
                if status:
                    self.raw.db.execute('UPDATE classification_jobs SET status=? WHERE job_id=?',(status,row['job_id'])); continue
                self.raw.db.execute("UPDATE classification_jobs SET status='RUNNING',attempts=attempts+1,lease_token=?,lease_until=? WHERE job_id=?",
                    (token,(now+timedelta(seconds=lease_seconds)).isoformat(),row['job_id']))
                claimed.append({'job_id':row['job_id'],'item':item,'lease_token':token})
                if len(claimed)==limit: break
        return claimed

    def resolve(self,jobs,request,response,snapshot,now):
        validated=validate_response(response,request,snapshot,allow_partial=True)
        accepted={r['item_id']:r for r in validated['accepted']}
        now=parse_utc(now).isoformat()
        with self.raw.transaction():
            for job in jobs:
                row=self.raw.db.execute('SELECT * FROM classification_jobs WHERE job_id=?',(job['job_id'],)).fetchone()
                if not row or row['status']!='RUNNING' or row['lease_token']!=job['lease_token'] or row['lease_until']<=now:
                    raise ValueError('Classification lease lost')
                item=job['item']
                if not self._current(item): status,code='STALE','RAW_OR_CONTEXT_CHANGED'
                elif item['item_id'] in accepted:
                    self.raw.db.execute('INSERT INTO node_analyses VALUES (?,?,?,?)',
                        (job['job_id'],item['item_id'],encode(accepted[item['item_id']]),now))
                    status,code='DONE',None
                else: status,code='PENDING' if row['attempts']<3 else 'FAILED',validated['rejected'].get(item['item_id'],'INVALID_BATCH_RESULT')
                retry_at=(parse_utc(now)+timedelta(seconds=30*2**max(0,row['attempts']-1))).isoformat() if status=='PENDING' else None
                self.raw.db.execute('UPDATE classification_jobs SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,lease_token=NULL WHERE job_id=?',
                    (status,code,retry_at,job['job_id']))
        return validated

    def release(self,jobs,code,now=None,retryable=True):
        now=parse_utc(now or utcnow())
        with self.raw.transaction():
            for job in jobs:
                row=self.raw.db.execute('SELECT attempts FROM classification_jobs WHERE job_id=?',(job['job_id'],)).fetchone()
                status='PENDING' if retryable and row and row[0]<3 else 'FAILED'
                delay=min(300,30*2**max(0,(row[0] if row else 1)-1))
                self.raw.db.execute("UPDATE classification_jobs SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,lease_token=NULL WHERE job_id=? AND status='RUNNING' AND lease_token=?",
                    (status,code,(now+timedelta(seconds=delay)).isoformat() if status=='PENDING' else None,job['job_id'],job['lease_token']))


def process_jobs(queue,snapshot,model,provider,now=None,node_ids=None,**batch_limits):
    """Offline/fake provider integration. Live callers must apply the runtime gate."""
    clock=now if callable(now) else (lambda:now) if now else utcnow
    jobs=queue.claim(snapshot,model,clock(),lease_seconds=600,node_ids=node_ids)
    if not jobs: return {'status':'NO_PENDING_JOBS'}
    try:
        built=build_batches([job['item'] for job in jobs],snapshot,**batch_limits)
        oversized={r['item_id'] for r in built['oversized']}
        with queue.raw.transaction():
            for job in jobs:
                if job['item']['item_id'] in oversized:
                    queue.raw.db.execute("UPDATE classification_jobs SET status='OVERSIZED',error_code='INPUT_OR_OUTPUT_LIMIT',lease_until=NULL WHERE job_id=? AND lease_token=?",
                        (job['job_id'],job['lease_token']))
        outcomes=[]
        for request in built['batches']:
            group=[job for job in jobs if job['item']['item_id'] in {i['item_id'] for i in request['items']}]
            try:
                response=provider(request)
                if getattr(provider,'require_intents',False):
                    from src.analysis.classification_contract import parse_json
                    parsed=parse_json(response)
                    if not isinstance(parsed,dict) or not isinstance(parsed.get('results'),list): raise ContractError('INVALID_RESPONSE_ENVELOPE')
                    # Live classification requires intent labels; old saved v2 outputs stay readable.
                    for result in parsed['results']:
                        if isinstance(result,dict) and not result.get('content_intents'):
                            result['content_intents']=[]  # Invalid per-item schema triggers partial retry.
                    response=parsed
                outcomes.append(queue.resolve(group,request,response,snapshot,clock()))
            except ProviderError as error:
                queue.release(group,error.code,clock(),retryable=error.retryable)
                outcomes.append({'error_code':error.code,'retryable':error.retryable})
            except ContractError as error:
                queue.release(group,error.code,clock()); outcomes.append({'error_code':error.code})
            except Exception:
                queue.release(group,'PROVIDER_OR_WORKER_FAILED',clock()); outcomes.append({'error_code':'PROVIDER_OR_WORKER_FAILED'})
        return {'status':'PROCESSED','outcomes':outcomes,'oversized':built['oversized']}
    except Exception:
        queue.release(jobs,'INPUT_BUILD_FAILED',clock())
        raise
