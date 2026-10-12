"""Threads producer: collect -> durable pages -> storage ACK. No filtering here."""
from contextlib import nullcontext
from pathlib import Path
from collections import Counter
import hashlib
import json
import threading
from src.acquisition.models import Deadline,AdapterError,utcnow
from src.acquisition.browser import browser_job
from src.acquisition.threads import ThreadsAPIAdapter,ThreadsBrowserAdapter,node_from_item,node_key
from src.config.env import env_str
from src.storage.conversations import ConversationStore,encode
from src.storage.ingest import IngestQueue


def crawl(database,config,queries,window,run_id,scope='POSTS_AND_REPLIES',*,progress=None,cancel=None,adapter=None,lease=None):
    budget=Deadline(config['limits']['seconds_per_run']);cancel=cancel or threading.Event()
    spool=IngestQueue(Path(database).parent/'ingest'/Path(database).stem)
    raw=ConversationStore(database)
    try:raw.db.execute('CREATE TABLE IF NOT EXISTS threads_inventory(node_id TEXT PRIMARY KEY,last_scanned_at TEXT NOT NULL)')
    finally:raw.close()
    report=dict(run_id=run_id,platform='THREADS',provider=config['provider'],scope=scope,status='COLLECTING',
        window_start=window.start.isoformat() if window else None,window_end=window.end.isoformat() if window else None,started_at=utcnow(),
        task_kind='ACQUISITION' if window else 'INVENTORY_REFRESH',
        config_version=config['version'],query_snapshot=queries,storage_order='RAW_THEN_FILTER_CLASSIFY',
        jobs=[],counters={},coverage_limited=True,coverage_scope=['OBSERVED_SEARCH_RESULTS','KNOWN_CONVERSATIONS'],
        full_window_coverage_verified=False)
    counts=Counter();sequence=0;observed_nodes=set();created_nodes=set();request_budget={'used':0,'limit':100}
    def publish():
        report.update(counters=dict(counts),updated_at=utcnow())
        if progress:progress(report)
    def commit(nodes,query,kind):
        nonlocal sequence
        if not nodes:return
        sequence+=1;stamp=utcnow();page_id=run_id+':'+query['query_id']+':'+str(sequence)
        lineage={'query_id':query['query_id'],'query_version':query['version'],'query_type':query['type'],
            'search_keyword':query['value'],'project_scope_id':query['project_id'],'discovered_via':kind,
            'provider_method':config['provider'],'window_start':report['window_start'],'window_end':report['window_end']}
        entries=[dict(node=n.payload(),source_id=query['query_id'],run_id=run_id,observed_at=stamp,lineage=lineage) for n in nodes]
        path=spool.enqueue(entries,page_id=page_id,task_id=run_id+':'+query['query_id'],checkpoint={'page_id':page_id,'stage':kind},lease=lease)
        report['status']='DRAINING';publish()
        receipts=spool.drain(database,paths=[path])
        for node,result in zip(nodes,receipts[-len(nodes):]):
            counts['unique_new_'+node.node_type.lower()]+=int(result['new'])
            if result['new']:created_nodes.add(result['node_id'])
            counts['new_revisions']+=int(result['changed'] and not result['new'])
            counts['existing_nodes_seen']+=int(not result['new'])
            if result['node_id'] not in observed_nodes:
                observed_nodes.add(result['node_id']);counts['committed_nodes']+=1
                counts[window.status(node.published_at,node.publication_precision).lower() if window else 'inventory_observed']+=1
        report['status']='COLLECTING';publish()
    for query in queries:
        if cancel.is_set() or budget.remaining()<1:break
        outcome=dict(query_id=query['query_id'],status='RUNNING',observed=0,gaps=[]);report['jobs'].append(outcome);publish()
        deadline=Deadline(min(config['limits']['seconds_per_query'],budget.remaining()))
        try:
            manager=browser_job('threads',deadline) if config['provider']=='THREADS_BROWSER' and adapter is None else nullcontext(None)
            with manager as page:
                provider=adapter or (ThreadsBrowserAdapter(page,deadline) if page else ThreadsAPIAdapter(env_str('THREADS_ACCESS_TOKEN'),deadline,request_budget=request_budget))
                candidates={}
                for result in provider.discover({'query':query['value'],'max_pages':config['limits']['pages_per_query'],
                         'max_candidates':config['limits']['candidates_per_query']}):
                    if cancel.is_set():break
                    remaining=config['limits']['candidates_per_query']-len(candidates)
                    fresh=result['items'][:remaining];candidates.update({node_key(item):item for item in fresh})
                    outcome['observed']+=len(fresh);counts['observed_candidates']+=len(fresh)
                    discovered=[]
                    for item in fresh:
                        node=node_from_item(item,node_type='REPLY' if item.get('is_reply') else 'POST',
                            relationship='UNRESOLVED' if item.get('is_reply') or config['provider']=='THREADS_BROWSER' else 'RESOLVED')
                        discovered.append(node)
                    commit(discovered,query,'KEYWORD_SEARCH')
                    if len(candidates)>=config['limits']['candidates_per_query']:
                        outcome['gaps'].append('CANDIDATE_LIMIT');break
                # Rescan oldest known roots, independent of root publication date.
                raw=ConversationStore(database,initialize=False)
                try:
                    roots=[n for n in raw.list_nodes(query['query_id'],node_type='POST') if n['platform']=='THREADS']
                    last_scan=dict(raw.db.execute('SELECT node_id,last_scanned_at FROM threads_inventory'))
                    roots.sort(key=lambda n:(last_scan.get(n['node_id'],''),n['first_seen_at'],n['node_id']))
                    counts['rescan_deferred']+=max(0,len(roots)-config['limits']['rescan_roots'])
                    for node in roots[:config['limits']['rescan_roots']]:
                        item={'id':node['platform_item_id'],'url':node['canonical_url'],'shortcode':node.get('platform_shortcode'),
                              'timestamp':node['published_at'],'text':node['raw_text'],'username':node['author_name']}
                        if item['url']:candidates.setdefault(node_key(item),item)
                finally:raw.close()
                if scope=='POSTS_AND_REPLIES':
                    for item in candidates.values():
                        if cancel.is_set():break
                        deadline.check()
                        raw=ConversationStore(database,initialize=False)
                        try:known=raw.get(node_key(item))
                        finally:raw.close()
                        if known and known['node_type']!='POST':
                            counts['search_reply_candidates_seen']+=1;continue
                        try:
                            detail=provider.fetch_item(item,{'scope':scope,'max_replies':config['limits']['replies_per_conversation'],
                                'max_pages':config['limits']['pages_per_query']})
                            root=node_from_item(detail['root'],relationship='UNRESOLVED' if config['provider']=='THREADS_BROWSER' else 'RESOLVED');nodes=[root];mapped={}
                            for reply in detail['replies']:mapped[str(reply.get('id'))]=node_key(reply)
                            pending=list(detail['replies'])
                            for _ in range(len(pending)+1):
                                if not pending:break
                                deferred=[]
                                for reply in pending:
                                    parent_native=(reply.get('replied_to') or {}).get('id')
                                    if parent_native and str(parent_native)==str(detail['root'].get('id')):
                                        parent=root.node_id;kind='COMMENT';relation='RESOLVED'
                                    elif parent_native and str(parent_native) in mapped:
                                        parent=mapped[str(parent_native)];kind='REPLY';relation='RESOLVED'
                                        if not any(n.node_id==parent for n in nodes):deferred.append(reply);continue
                                    else:parent=None;kind='REPLY';relation='UNRESOLVED'
                                    nodes.append(node_from_item(reply,root=root.node_id,parent=parent,relationship=relation,node_type=kind))
                                if len(deferred)==len(pending):
                                    for reply in deferred:nodes.append(node_from_item(reply,root=root.node_id,relationship='UNRESOLVED',node_type='REPLY'))
                                    break
                                pending=deferred
                            commit(nodes,query,'CONVERSATION_RESCAN')
                            raw=ConversationStore(database,initialize=False)
                            try:
                                with raw.transaction():raw.db.execute('INSERT OR REPLACE INTO threads_inventory VALUES (?,?)',(root.node_id,utcnow()))
                            finally:raw.close()
                            counts['conversations_fetched']+=1
                            if detail.get('error_code'):outcome['gaps'].append(detail['error_code'])
                        except AdapterError as error:
                            outcome['gaps'].append(error.code)
                            if error.status in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED'}:raise
                outcome['status']='PARTIAL' if outcome['gaps'] or config['provider']=='THREADS_BROWSER' else 'SUCCEEDED'
        except AdapterError as error:
            outcome.update(status='PARTIAL' if outcome['observed'] else 'BLOCKED' if error.status in {'AUTH_REQUIRED','ACCESS_DENIED'} else 'FAILED',error_code=error.code)
        except TimeoutError:outcome.update(status='PARTIAL',error_code='TIME_BUDGET_REACHED')
        except Exception:outcome.update(status='FAILED',error_code='THREADS_WORKER_FAILED')
        outcome['gaps']=sorted(set(outcome['gaps']));publish()
    raw=ConversationStore(database,initialize=False)
    try:
        final_types=Counter(raw.get(i)['node_type'].lower() for i in created_nodes)
        for kind in ('post','comment','reply'):counts['unique_new_'+kind]=final_types[kind]
        report['final_node_types']=dict(Counter(raw.get(i)['node_type'] for i in observed_nodes))
    finally:raw.close()
    report.update(status='CANCELLED' if cancel.is_set() else 'PARTIAL' if counts['committed_nodes'] else 'BLOCKED' if any(j['status']=='BLOCKED' for j in report['jobs']) else 'FAILED' if any(j['status']=='FAILED' for j in report['jobs']) else 'SUCCEEDED',finished_at=utcnow())
    if config['provider']=='THREADS_API':report['provider_requests']=request_budget['used']
    if len(report['jobs'])<len(queries):report['deferred_queries']=len(queries)-len(report['jobs'])
    publish();return report
