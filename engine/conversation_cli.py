"""V2 raw conversations, durable crawl tasks and offline classifier preparation."""
import argparse
import json
from pathlib import Path
from src.acquisition.models import Window, parse_utc
from src.storage.acquisition import AcquisitionStore
from src.storage.conversations import ConversationStore
from src.storage.conversation_migration import migrate_legacy, rollback_to_copy
from engine.acquisition import AcquisitionEngine
from engine.registry import Registry
from engine.group_tracing import trace_thread
from engine.conversation_schedule import CrawlTasks
from engine.conversation_worker import execute_task
from src.acquisition.models import utcnow
from datetime import date,datetime
import time
import sys
from engine.conversation_schedule import VN
from engine.classification_input import prepare_saved,build_batches
from engine.classification_jobs import ClassificationJobs
from src.analysis.taxonomy import load_snapshot


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='V2 raw conversations/task service; coverage and model readiness remain explicit.')
    parser.add_argument('--db', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    migration = commands.add_parser('migrate')
    migration.add_argument('--backup', type=Path, required=True)
    restore = commands.add_parser('restore-copy')
    restore.add_argument('--backup', type=Path, required=True)
    listing = commands.add_parser('list')
    listing.add_argument('--source-id')
    crawl = commands.add_parser('crawl-posts')
    crawl.add_argument('--source-id', required=True)
    crawl.add_argument('--config-dir', type=Path, default=ROOT / 'config')
    crawl.add_argument('--watchlist', default='vincons_acquisition_v1')
    crawl.add_argument('--start', required=True)
    crawl.add_argument('--end', required=True)
    crawl.add_argument('--max-candidates', type=int, default=10)
    thread = commands.add_parser('scan-thread', help='Scan comments on an approved group post, including old posts.')
    thread.add_argument('--source-id', required=True)
    thread.add_argument('--post-url', required=True)
    thread.add_argument('--config-dir', type=Path, default=ROOT / 'config')
    thread.add_argument('--start', required=True)
    thread.add_argument('--end', required=True)
    thread.add_argument('--seconds', type=int, default=120)
    thread.add_argument('--classify',action='store_true',help='Classify saved raw through configured Gemini after this crawl.')
    schedule = commands.add_parser('enqueue-days', help='Persist due ticks for an explicit date range; no browser call.')
    schedule.add_argument('--source-id', action='append', required=True)
    schedule.add_argument('--first-day', type=date.fromisoformat, required=True)
    schedule.add_argument('--last-day', type=date.fromisoformat, required=True)
    schedule.add_argument('--now', default=None)
    schedule.add_argument('--config-dir', type=Path, default=ROOT / 'config')
    worker = commands.add_parser('work-once', help='Execute one durable source task; partial coverage is explicit.')
    worker.add_argument('--config-dir', type=Path, default=ROOT / 'config')
    worker.add_argument('--seconds', type=int, default=1200)
    worker.add_argument('--max-threads', type=int, default=20)
    worker.add_argument('--classify',action='store_true')
    inputs=commands.add_parser('prepare-classification',help='Saved-raw filter, batch input and durable jobs; does not call the model.')
    inputs.add_argument('--source-id')
    inputs.add_argument('--taxonomy-dir',type=Path,default=ROOT/'specs/taxonomy/v1')
    inputs.add_argument('--model',required=True)
    inputs.add_argument('--output',type=Path,required=True)
    service=commands.add_parser('serve',help='Run the v2 daily task service in this terminal; Ctrl+C stops it.')
    service.add_argument('--source-id',action='append',required=True)
    service.add_argument('--first-day',type=date.fromisoformat,required=True)
    service.add_argument('--config-dir',type=Path,default=ROOT/'config')
    service.add_argument('--poll-seconds',type=int,default=10)
    service.add_argument('--classify',action='store_true',help='Dispatch and classify saved raw on every service cycle.')
    args = parser.parse_args(argv)
    provider=taxonomy=None
    if getattr(args,'classify',False):
        from src.analysis.gemini_gateway import GeminiGateway
        from engine.classification_worker import RUNTIME_TAXONOMY
        from src.analysis.taxonomy import require_runtime_ready
        taxonomy=load_snapshot(RUNTIME_TAXONOMY);require_runtime_ready(taxonomy)
        provider=GeminiGateway()
    if args.command == 'migrate':
        result = migrate_legacy(args.db, args.backup)
    elif args.command == 'restore-copy':
        result = {'restored_copy': rollback_to_copy(args.backup, args.db)}
    else:
        raw = ConversationStore(args.db)
        try:
            if args.command == 'serve':
                if not 1<=args.poll_seconds<=60: raise ValueError('Poll seconds must be 1–60')
                registry=Registry(args.config_dir)
                for source_id in args.source_id:
                    source=registry.sources.get(source_id,{})
                    if source.get('source_type')!='FACEBOOK_GROUP' or registry.readiness(source):
                        raise ValueError('Verified enabled Facebook group required')
                tasks=CrawlTasks(raw)
                try:
                    while True:
                        tasks.enqueue_days(args.source_id,args.first_day,datetime.now(VN).date(),utcnow())
                        task=tasks.claim(utcnow(),lease_seconds=1260)
                        if task:
                            outcome=execute_task(registry,raw,task)
                            tasks.finish(task,outcome,utcnow())
                            print(json.dumps({'task_id':task['task_id'],'status':outcome['status']},ensure_ascii=False),flush=True)
                        if provider:
                            from engine.classification_worker import classification_cycle
                            outcome=classification_cycle(raw,taxonomy,provider)
                            if outcome['api_calls']: print(json.dumps(outcome),flush=True)
                        if not task: time.sleep(args.poll_seconds)
                except KeyboardInterrupt:
                    result={'status':'SERVICE_STOPPED','pending_tasks_retained':True}
            elif args.command == 'list':
                nodes = raw.list_nodes(args.source_id)
                result = {'total': len(nodes), 'nodes': nodes}
            elif args.command == 'scan-thread':
                result = trace_thread(Registry(args.config_dir),raw,args.source_id,args.post_url,
                    Window(parse_utc(args.start),parse_utc(args.end)),args.seconds)
            elif args.command == 'enqueue-days':
                registry=Registry(args.config_dir)
                for source_id in args.source_id:
                    source=registry.sources.get(source_id,{})
                    if source.get('source_type')!='FACEBOOK_GROUP' or registry.readiness(source):
                        raise ValueError('Verified enabled Facebook group required')
                result={'tasks_inserted':CrawlTasks(raw).enqueue_days(args.source_id,args.first_day,args.last_day,args.now or utcnow())}
            elif args.command == 'work-once':
                tasks=CrawlTasks(raw)
                task=tasks.claim(utcnow(),lease_seconds=1260)
                result=execute_task(Registry(args.config_dir),raw,task,args.seconds,args.max_threads) if task else {'status':'NO_DUE_TASK'}
                if task: tasks.finish(task,result,utcnow())
            elif args.command == 'prepare-classification':
                snapshot=load_snapshot(args.taxonomy_dir)
                prepared=prepare_saved(raw,snapshot,args.source_id)
                batched=build_batches(prepared['items'],snapshot)
                count=ClassificationJobs(raw).enqueue(prepared['items'],snapshot,args.model)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps({**batched,'skipped':prepared['skipped']},ensure_ascii=False,indent=2),encoding='utf-8')
                result={'jobs_inserted':count,'batches':len(batched['batches']),'oversized':len(batched['oversized']),
                    'skipped':len(prepared['skipped']),'output':str(args.output),'model_called':False,
                    'taxonomy_runtime_enabled':all(d['runtime_enabled'] for d in [snapshot['catalog'],*snapshot['profiles'].values()])}
            else:
                legacy = AcquisitionStore(args.db)
                try:
                    registry = Registry(args.config_dir, legacy.draft_sources())
                    if registry.sources.get(args.source_id, {}).get('source_type') != 'FACEBOOK_GROUP':
                        raise ValueError('Facebook group source required')
                    result = AcquisitionEngine(registry, legacy, raw_store=raw).run(args.watchlist,
                        Window(parse_utc(args.start), parse_utc(args.end)), [args.source_id], args.max_candidates)
                    result.update(mode='RAW_FIRST_POSTS_P1', comments_supported=False, full_window_coverage_verified=False)
                finally:
                    legacy.close()
            if provider and args.command!='serve':
                from engine.classification_worker import classification_cycle
                result['classification']=classification_cycle(raw,taxonomy,provider)
        finally:
            raw.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
