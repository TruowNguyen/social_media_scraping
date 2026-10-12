"""Read-only Threads pilot and repeatable acquisition; no credentials in output."""
import argparse
import copy
import json
from pathlib import Path
from datetime import datetime,timedelta,timezone
import uuid
from engine.threads_registry import ThreadsRegistry
from engine.threads_worker import crawl
from src.acquisition.models import Deadline,Window,parse_utc,utcnow
from src.acquisition.browser import browser_job
from src.acquisition.threads import ThreadsBrowserAdapter,ThreadsAPIAdapter
from src.config.env import env_str
from src.storage.conversations import ConversationStore


def main(argv=None):
    parser=argparse.ArgumentParser(description='Threads project search and retained conversations')
    parser.add_argument('command',choices=('probe','run'))
    parser.add_argument('--config-dir',default='config');parser.add_argument('--database',default='sessions/acquisition/acquisition.sqlite3')
    parser.add_argument('--query-id',default='threads_vwy_name');parser.add_argument('--scope',choices=('POST_ONLY','POSTS_AND_REPLIES'),default='POSTS_AND_REPLIES')
    parser.add_argument('--start');parser.add_argument('--end');parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--max-candidates',type=int,default=20);parser.add_argument('--max-pages',type=int,default=3)
    parser.add_argument('--seconds',type=int,default=120);parser.add_argument('--report',default='reports/threads-live-pilot.json')
    args=parser.parse_args(argv);registry=ThreadsRegistry(args.config_dir)
    config=copy.deepcopy(registry.data);query=next(q for q in config['queries'] if q['query_id']==args.query_id)
    if not query['enabled'] or query['archived']:parser.error('Selected query is disabled')
    if not args.pilot and not config['enabled']:parser.error('Threads is not enabled; use --pilot for capability verification')
    if not 1<=args.max_candidates<=100 or not 1<=args.max_pages<=10 or not 10<=args.seconds<=300:parser.error('Invalid pilot budget')
    config['limits'].update(candidates_per_query=args.max_candidates,pages_per_query=args.max_pages,seconds_per_query=args.seconds,seconds_per_run=args.seconds)
    if args.command=='probe':
        deadline=Deadline(args.seconds)
        if config['provider']=='THREADS_BROWSER':
            with browser_job('threads',deadline) as page:report=ThreadsBrowserAdapter(page,deadline).probe_access({'query':query['value']})
        else:report=ThreadsAPIAdapter(env_str('THREADS_ACCESS_TOKEN'),deadline).probe_access({'query':query['value']})
        report.update(provider=config['provider'],query_id=query['query_id'],query=query['value'],checked_at=utcnow())
    else:
        end=parse_utc(args.end) if args.end else datetime.now(timezone.utc)
        start=parse_utc(args.start) if args.start else end-timedelta(days=14)
        run_id='threads_pilot_'+uuid.uuid4().hex
        report=crawl(args.database,config,[query],Window(start,end),run_id,args.scope)
        report.update(trigger='CLI',project_id=query['project_id'])
        raw=ConversationStore(args.database,initialize=False)
        try:
            ids=[r[0] for r in raw.db.execute('SELECT DISTINCT node_id FROM conversation_observations WHERE run_id=?',(run_id,))]
            report['output']=[{k:node.get(k) for k in ('node_id','node_type','platform','canonical_url','published_at','publication_precision','root_post_id','parent_node_id','relationship_status','missing_fields')}|
                {'text_chars':len(node['raw_text'] or '')} for node in (raw.get(i) for i in ids)]
            report['database']=str(Path(args.database).resolve())
            if raw.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='acquisition_runs'").fetchone():
                from src.storage.conversations import encode
                with raw.transaction():raw.db.execute('INSERT OR IGNORE INTO acquisition_runs VALUES (?,?,?,?,?)',(run_id,'CLI:'+run_id,report['status'],encode({k:v for k,v in report.items() if k!='output'}),utcnow()))
        finally:raw.close()
    report['pilot']=args.pilot;report['live_data']=True
    path=Path(args.report);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in report if k not in {'output','query_snapshot'}},ensure_ascii=False))


if __name__=='__main__':main()
