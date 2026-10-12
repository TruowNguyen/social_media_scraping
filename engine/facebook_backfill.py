"""Supervised Facebook group backfill, persisted progress and honest coverage."""
import argparse
import json
import uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from engine.registry import Registry
from engine.classification_worker import DEFAULT_DB
from engine.conversation_worker import inventory_source
from engine.conversation_schedule import CrawlTasks
from engine.group_tracing import trace_thread
from src.acquisition.models import Deadline,Window,utcnow,AdapterError,parse_utc
from src.storage.conversations import ConversationStore,encode


def run(database,config,report_path,days=14,source_seconds=180,run_seconds=3600,window=None,pending_only=False):
    now=datetime.now(timezone.utc);window=window or Window(now-timedelta(days=days),now)
    registry=Registry(config)
    sources=[sid for sid,s in registry.sources.items() if s['source_type']=='FACEBOOK_GROUP' and not registry.readiness(s)]
    raw=ConversationStore(database);tasks=CrawlTasks(raw);budget=Deadline(run_seconds)
    report=dict(run_id='backfill_'+uuid.uuid4().hex,pipeline='RAW_V2_THREADS',database=str(database),
        window_start=window.start.isoformat(),window_end=window.end.isoformat(),started_at=utcnow(),status='RUNNING',
        source_count=len(sources),source_outcomes=[],full_window_coverage_verified=False)
    raw.db.execute('CREATE TABLE IF NOT EXISTS facebook_backfill_runs(run_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    def save():
        with raw.transaction(): raw.db.execute('INSERT OR REPLACE INTO facebook_backfill_runs VALUES (?,?)',(report['run_id'],encode(report)))
        report_path.parent.mkdir(parents=True,exist_ok=True)
        temporary=report_path.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(report_path)
    save()
    try:
        for sid in sources:
            outcome=dict(source_id=sid,status='RUNNING',threads=[],full_window_coverage_verified=False)
            report['source_outcomes'].append(outcome);save()
            if budget.remaining()<1:
                outcome.update(status='NOT_ATTEMPTED',error_code='RUN_TIME_BUDGET');save();continue
            group_budget=Deadline(min(source_seconds,budget.remaining()))
            try:
                outcome['inventory']=dict(status='SUCCESS',observed_posts=0,mode='SAVED_PENDING_THREADS') if pending_only else inventory_source(registry,raw,sid,window,min(120,group_budget.remaining()),max_candidates=5000,listing_seconds=100,stall_limit=8)
                inventory=outcome['inventory']
                if inventory['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED','SKIPPED'}:
                    outcome.update(status=inventory['status'],error_code=inventory.get('error_code'));save();continue
                posts=tasks.fair_posts(sid,5000)
                if pending_only: posts=[p for p in posts if p['last_scanned_at'] is None]
                outcome['known_posts']=len(posts)
                for post in posts:
                    if group_budget.remaining()<1 or budget.remaining()<1:
                        outcome['stop_reason']='SOURCE_TIME_BUDGET';break
                    thread=trace_thread(registry,raw,sid,post['post_url'],window,min(60,group_budget.remaining(),budget.remaining()))
                    tasks.scanned(sid,post['node_id'],thread,utcnow());outcome['threads'].append(thread);save()
                    if thread['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED','SKIPPED'}:
                        outcome['stop_reason']=thread.get('error_code',thread['status']);break
                outcome['threads_attempted']=len(outcome['threads'])
                outcome['known_posts_not_scanned']=max(0,len(posts)-len(outcome['threads']))
                outcome['status']='PARTIAL'
            except AdapterError as error:
                outcome.update(status=error.status,error_code=error.code)
            except Exception:
                outcome.update(status='EXTRACTION_FAILED',error_code='BACKFILL_SOURCE_FAILED')
            save()
            print(json.dumps({'source_id':sid,'status':outcome['status'],'posts_observed':outcome.get('inventory',{}).get('observed_posts',0),
                'threads_attempted':len(outcome['threads']),'comments_observed':sum(t.get('coverage',{}).get('observed_comments_and_replies',0) for t in outcome['threads'])}),flush=True)
        nodes=raw.list_nodes();confirmed=raw.list_nodes(window=window)
        report.update(status='PARTIAL',finished_at=utcnow(),raw_counts={kind:sum(n['node_type']==kind for n in nodes) for kind in ('POST','COMMENT','REPLY')},
            confirmed_in_window={kind:sum(n['node_type']==kind for n in confirmed) for kind in ('POST','COMMENT','REPLY')},
            missing_publication_time=sum(n['publication_precision']!='INSTANT' for n in nodes))
        save();return report
    except BaseException:
        report.update(status='INTERRUPTED',finished_at=utcnow());save();raise
    finally: raw.close()


def main():
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'config')
    parser.add_argument('--report',type=Path,default=Path('reports/facebook-backfill-14-days.json'))
    parser.add_argument('--start');parser.add_argument('--end')
    parser.add_argument('--pending-only',action='store_true',help='Fetch saved inventory posts never attempted, without repeating discovery')
    args=parser.parse_args()
    if bool(args.start)!=bool(args.end): parser.error('--start and --end required together')
    window=Window(parse_utc(args.start),parse_utc(args.end)) if args.start else None
    report=run(args.db,args.config,args.report,window=window,pending_only=args.pending_only,source_seconds=1200 if args.pending_only else 180)
    print(json.dumps({k:report[k] for k in ('status','source_count','raw_counts','confirmed_in_window','full_window_coverage_verified')}),flush=True)


if __name__=='__main__':main()
