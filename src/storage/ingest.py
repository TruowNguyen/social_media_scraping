"""Durable immutable pages; ACK/checkpoint shares the raw commit transaction."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import time
import uuid
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore, encode
from src.acquisition.models import utcnow,parse_utc


class IngestQueue:
    def __init__(self, directory):
        self.directory=Path(directory)
        for name in ('ready','archive','dlq'):(self.directory/name).mkdir(parents=True,exist_ok=True)

    def enqueue(self, entries, *, page_id, task_id, checkpoint,lease=None):
        if not entries or len(entries)>200:raise ValueError('Page must contain 1-200 entries')
        ready=list((self.directory/'ready').glob('*.json'))
        if len(ready)>=10000 or sum(p.stat().st_size for p in ready)>=500*1024*1024:
            raise RuntimeError('QUEUE_BACKPRESSURE')
        body={'schema_version':'ingest-page-v1','page_id':page_id,'task_id':task_id,
              'entries':entries,'checkpoint':checkpoint}
        if lease:body['lease']=lease
        encoded=encode(body);checksum=hashlib.sha256(encoded.encode()).hexdigest()
        target=self.directory/'ready'/(hashlib.sha256(page_id.encode()).hexdigest()+'.json')
        document=encode({'checksum':checksum,'body':body})
        if target.exists():
            if target.read_text(encoding='utf-8')!=document:raise ValueError('Immutable page conflict')
            return target
        temporary=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('w',encoding='utf-8') as stream:
                stream.write(document);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
        return target

    def commit(self, path, raw,*,recovery=False):
        path=Path(path)
        if path.resolve().parent!=(self.directory/'ready').resolve():raise ValueError('Invalid spool path')
        document=json.loads(path.read_text(encoding='utf-8'));body=document['body']
        checksum=hashlib.sha256(encode(body).encode()).hexdigest()
        if checksum!=document['checksum'] or body['schema_version']!='ingest-page-v1':raise ValueError('Invalid spool checksum/schema')
        receipts=[]
        with raw.transaction():
            previous=raw.db.execute('SELECT checksum,payload FROM ingest_page_receipts WHERE page_id=?',(body['page_id'],)).fetchone()
            if previous:
                if previous[0]!=checksum:raise ValueError('Committed page conflict')
                receipts=json.loads(previous[1])
            else:
                if body.get('lease'):
                    fence=body['lease'];active=raw.db.execute('SELECT token,expires_at FROM acquisition_leases WHERE platform=?',(fence['platform'],)).fetchone()
                    valid=active and active[0]==fence['token'] and parse_utc(active[1])>parse_utc(utcnow())
                    if not valid and recovery and not (active and parse_utc(active[1])>parse_utc(utcnow())):
                        run_ids={entry['run_id'] for entry in body['entries']}
                        row=raw.db.execute('SELECT status,payload FROM acquisition_runs WHERE run_id=?',(next(iter(run_ids)),)).fetchone() if len(run_ids)==1 else None
                        state=json.loads(row[1]) if row else {}
                        cutoff=state.get('lease_expired_at') or state.get('finished_at')
                        valid=bool(row and row[0] in {'PARTIAL','FAILED','CANCELLED'} and cutoff and all(parse_utc(e['observed_at'])<=parse_utc(cutoff) for e in body['entries']))
                    if not valid:raise RuntimeError('INGEST_LEASE_LOST')
                mapped={}
                # Resolve provisional producer references before writing parent/children.
                for entry in body['entries']:
                    node=ContentNode(**entry['node'])
                    known={r[0] for alias in raw.aliases(node) for r in raw.db.execute('SELECT node_id FROM node_aliases WHERE alias=?',(alias,))}
                    if len(known)>1:raise ValueError('Conflicting aliases')
                    if node.node_id:mapped[node.node_id]=next(iter(known),node.node_id)
                for index,entry in enumerate(body['entries']):
                    payload=dict(entry['node'])
                    for key in ('node_id','root_post_id','parent_node_id'):
                        if payload.get(key) in mapped:payload[key]=mapped[payload[key]]
                    node=ContentNode(**payload)
                    observation_id='ingest:'+hashlib.sha256(encode([body['page_id'],index,entry['source_id']]).encode()).hexdigest()
                    receipts.append(raw.ingest(node,entry['source_id'],entry['run_id'],observation_id=observation_id,
                        observed_at=entry['observed_at'],lineage=entry.get('lineage')))
                raw.db.execute('INSERT INTO conversation_checkpoints VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                    (body['task_id'],encode(body['checkpoint']),utcnow()))
                raw.db.execute('INSERT INTO ingest_page_receipts VALUES (?,?,?,?,?)',
                    (body['page_id'],checksum,body['task_id'],encode(receipts),utcnow()))
        # Move only after COMMIT. A crash here replays the receipt, not raw writes.
        os.replace(path,self.directory/'archive'/path.name)
        return receipts

    def drain(self, database, limit=100, paths=None,*,recovery=False):
        raw=ConversationStore(database);results=[]
        try:
            for path in (paths if paths is not None else sorted((self.directory/'ready').glob('*.json'))[:limit]):
                for attempt in range(5):
                    try:
                        results.extend(self.commit(path,raw,recovery=recovery));break
                    except sqlite3.OperationalError as error:
                        if not any(code in str(error).lower() for code in ('busy','locked')) or attempt==4:raise
                        time.sleep(.05*(2**attempt))
                    except FileNotFoundError:break  # Another storage worker already ACKed it.
                    except (ValueError,KeyError,TypeError):
                        os.replace(path,self.directory/'dlq'/path.name)
                        raise ValueError('INGEST_VALIDATION_FAILED') from None
            return results
        finally:raw.close()
