"""Raw-first reconciliation and Gemini worker; outbox/jobs persist across restarts."""
import argparse
import json
from pathlib import Path
import time
import sys
from functools import lru_cache
from engine.classification_input import prepare_saved,job_key
from engine.classification_jobs import ClassificationJobs,process_jobs
from src.analysis.taxonomy import load_snapshot,require_runtime_ready
from src.analysis.gemini_gateway import GeminiGateway
from src.analysis.classification_labels import reason_vi
from engine.classification_input import PROMPT_VERSION,RULE_VERSION
from src.acquisition.models import utcnow
from src.storage.conversations import ConversationStore,encode

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=ROOT/'sessions/acquisition/acquisition.sqlite3'
RUNTIME_TAXONOMY=ROOT/'config/taxonomy/v1'


def reconcile_saved(raw,snapshot,model,source_id=None):
    """Persist current filter decisions and jobs without making any API call."""
    require_runtime_ready(snapshot)
    queue=ClassificationJobs(raw)
    # Each saved decision and enqueue has its own short transaction. Hashing and
    # scanning the full history must not hold SQLite's single writer lock.
    # A crash before consumption is repaired by the next idempotent reconciliation.
    pending_events=raw.db.execute("SELECT event_id,node_id FROM conversation_outbox WHERE status='PENDING'").fetchall()
    prepared=prepare_saved(raw,snapshot,source_id)
    completed=queue.completed_item_ids(prepared['items'],snapshot)
    prepared['completed_reused']=sorted(completed)
    prepared['items']=[item for item in prepared['items'] if item['item_id'] not in completed]
    inserted=queue.enqueue(prepared['items'],snapshot,model)
    ids=set(prepared['completed_reused']+[item['item_id'] for item in prepared['items']]+[item['item_id'] for item in prepared['skipped']])
    with raw.transaction():
        # Consume only events present before preparation, never a concurrent
        # caption/context/OCR change that still needs its own reconciliation.
        raw.db.executemany("UPDATE conversation_outbox SET status='CONSUMED' WHERE event_id=? AND status='PENDING'",
            [(event[0],) for event in pending_events if event[1] in ids])
    return prepared,inserted


def classification_cycle(raw,snapshot,provider,source_id=None):
    prepared,inserted=reconcile_saved(raw,snapshot,provider.model,source_id)
    queue=ClassificationJobs(raw)
    before=len(provider.telemetry)
    processed=process_jobs(queue,snapshot,provider.model,provider)
    telemetry=provider.telemetry[before:]
    with raw.transaction():
        raw.db.execute('CREATE TABLE IF NOT EXISTS classification_api_calls(call_id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL,observed_at TEXT NOT NULL)')
        for event in telemetry:
            raw.db.execute('INSERT INTO classification_api_calls(payload,observed_at) VALUES (?,?)',(encode(event),utcnow()))
    provider.telemetry.clear()
    accepted=sum(len(o.get('accepted',[])) for o in processed.get('outcomes',[]))
    counts={row[0]:row[1] for row in raw.db.execute('SELECT status,count(*) FROM classification_jobs GROUP BY status')}
    return dict(status=processed['status'],jobs_inserted=inserted,accepted=accepted,job_counts=counts,
        completed_reused=len(prepared['completed_reused']),
        skipped=len(prepared['skipped']),api_calls=len(telemetry),provider_events=telemetry,
        errors=[o['error_code'] for o in processed.get('outcomes',[]) if 'error_code' in o],
        invalid_items=sum(len(o.get('rejected',{})) for o in processed.get('outcomes',[])))


@lru_cache(maxsize=16)
def _read_binding(encoded):
    # Return the canonical string too, so job cache entries share one large binding.
    return json.loads(encoded),encoded


@lru_cache(maxsize=2048)
def _read_job(payload,binding_text,prompt_version,rule_version):
    item=json.loads(payload);binding,_=_read_binding(binding_text)
    return item,job_key(item,binding['taxonomy'],binding['model'])


def classification_rows(raw,snapshot):
    queue=ClassificationJobs(raw,initialize=False)
    nodes=raw.list_nodes()
    by_id={n['node_id']:n for n in nodes}
    from src.storage.image_evidence import all_bindings,input_current
    images=all_bindings(raw,nodes)
    jobs_by_node={}
    tables={r[0] for r in raw.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for job in raw.db.execute('SELECT * FROM classification_jobs ORDER BY rowid DESC') if 'classification_jobs' in tables else []:
        jobs_by_node.setdefault(job['node_id'],[]).append(job)
    analyses={r[0]:json.loads(r[1]) for r in raw.db.execute('SELECT job_id,payload FROM node_analyses')} if 'node_analyses' in tables else {}
    validated={r[0]:r[1] for r in raw.db.execute('SELECT job_id,validated_at FROM node_analyses')} if 'node_analyses' in tables else {}
    sources_by_node={}
    for row in raw.db.execute('SELECT node_id,source_id FROM node_sources'):
        sources_by_node.setdefault(row[0],[]).append(row[1])
    filters_by_revision={(r[0],r[1]):json.loads(r[2]) for r in raw.db.execute('SELECT node_id,revision_id,payload FROM raw_filter_decisions ORDER BY rowid')}
    def is_current(item):
        return all(by_id.get(n['item_id'],{}).get('revision_id')==n['revision_id'] for n in [item,*item['context']]) and input_current(raw,item,by_id,images)
    rows=[]
    def valid(job):
        binding,text=_read_binding(job['binding'])
        if binding['taxonomy']!=snapshot:return False
        item,key=_read_job(job['payload'],text,PROMPT_VERSION,RULE_VERSION)
        return is_current(item) and job['job_id']==key
    for node in nodes:
        jobs=jobs_by_node.get(node['node_id'],[])
        current=next((job for job in jobs if valid(job)),None)
        analysis=None
        if current:
            analysis=analyses.get(current['job_id'])
        decision=filters_by_revision.get((node['node_id'],node['revision_id']),{})
        sources=sources_by_node.get(node['node_id'],[])
        status=current['status'] if current else (
            'FILTER_DROP' if decision.get('prefilter_decision')=='DROP' else
            'MISSING_TEXT' if not (node['raw_text'] or '').strip() and not images.get(node['node_id']) else
            'STALE' if jobs else 'UNCLASSIFIED')
        state_reason={
            'MISSING_TEXT':'Chưa có caption, nội dung bình luận hoặc chữ OCR để phân loại. Cần thu thập lại nội dung.',
            'STALE':'Nội dung, ngữ cảnh, OCR hoặc cấu hình đã thay đổi. Kết quả cũ vẫn được lưu; phiên bản hiện tại cần vào hàng chờ lại.',
            'UNCLASSIFIED':'Nội dung đã lưu nhưng chưa có job phân loại cho phiên bản hiện tại.',
            'PENDING':'Đã vào hàng chờ phân loại; chưa có kết quả model cho phiên bản hiện tại.',
            'RUNNING':'Worker đang phân loại phiên bản hiện tại.',
            'OVERSIZED':'Nội dung hoặc ngữ cảnh vượt giới hạn batch; chưa được gửi đến model.',
        }.get(status)
        if current and current['error_code']:
            state_reason={
                'PROVIDER_TEMPORARY_ERROR':'API phân loại gặp lỗi tạm thời hoặc giới hạn yêu cầu; dữ liệu vẫn được giữ.',
                'PROVIDER_HTTP_ERROR':'API phân loại trả lỗi HTTP; chưa nhận được kết quả hợp lệ.',
                'PROVIDER_AUTH_DENIED':'API phân loại từ chối xác thực. Cần kiểm tra cấu hình truy cập.',
                'COMPLAINT_INTENT_CANNOT_BE_DROPPED':'Model nhận diện phản ánh nhưng lại trả kết quả loại; hệ thống từ chối kết quả mâu thuẫn này.',
                'UNCERTAIN_OCR_REQUIRES_REVIEW':'Chữ OCR của nội dung hoặc bài cha chưa đủ tin cậy, nhưng model không đánh dấu cần xem xét. Kết quả bị từ chối; cần thử lại sau khi sửa hướng dẫn model.',
            }.get(current['error_code'],'Kết quả phân loại bị lỗi hoặc không đáp ứng schema; chưa được chấp nhận.')
        rows.append(dict(node_id=node['node_id'],platform=node['platform'].lower(),node_type=node['node_type'],root_post_id=node['root_post_id'],
            url=node['display_url'],raw_text=node['raw_text'],published_at=node['published_at'],publication_precision=node['publication_precision'],collected_at=node['last_seen_at'],
            ocr_text='\n'.join(e['text'] for e in images.get(node['node_id'],[])),
            source_ids=sources,analysis=analysis,processing_status=status,
            filter_decision=decision,reason_vi=reason_vi(analysis,decision) if analysis or status=='FILTER_DROP' else state_reason,error_code=current['error_code'] if current else None,
            job_id=current['job_id'] if current else None,model_id=_read_binding(current['binding'])[0]['model'] if current else None,
            classified_at=validated.get(current['job_id']) if current else None,taxonomy_version=snapshot['catalog'].get('version',snapshot['catalog'].get('taxonomy_version')),
            attempts=current['attempts'] if current else None,next_attempt_at=current['next_attempt_at'] if current else None))
    return rows


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--taxonomy-dir',type=Path,default=RUNTIME_TAXONOMY)
    parser.add_argument('--source-id')
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--poll-seconds',type=int,default=15)
    parser.add_argument('--results',action='store_true')
    parser.add_argument('--prepare-only',action='store_true',help='Reconcile saved data into the queue without calling the model')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args(argv)
    if args.prepare_only and (args.serve or args.results):parser.error('--prepare-only cannot combine with --serve or --results')
    if not 1<=args.poll_seconds<=60: parser.error('Poll seconds must be 1–60')
    snapshot=load_snapshot(args.taxonomy_dir);require_runtime_ready(snapshot)
    raw=ConversationStore(args.db)
    heartbeat=None
    try:
        if args.results: print(json.dumps({'rows':classification_rows(raw,snapshot)},ensure_ascii=False,indent=2));return 0
        if args.prepare_only:
            from collections import Counter
            from src.config.env import env_str
            prepared,inserted=reconcile_saved(raw,snapshot,env_str('GEMINI_MODEL'),args.source_id)
            result={'status':'PREPARED','jobs_inserted':inserted,'eligible_inputs':len(prepared['items']),
                    'completed_reused':len(prepared['completed_reused']),
                    'skipped':dict(Counter(i['reason'] for i in prepared['skipped'])),'api_calls':0}
            if args.report:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False));return 0
        from engine.worker_heartbeat import Heartbeat
        heartbeat=Heartbeat(args.db);heartbeat.__enter__()
        provider=GeminiGateway()
        while True:
            result=classification_cycle(raw,snapshot,provider,args.source_id)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if args.report:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            if not args.serve: break
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt: pass
    finally:
        if heartbeat:heartbeat.__exit__()
        raw.close()
    return 0


if __name__=='__main__': main()
