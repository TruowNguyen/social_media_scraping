"""Explicit permalink pilot on v2 raw storage; durable partial coverage."""
from contextlib import contextmanager
import uuid
from engine.acquisition import adapter_job
from src.acquisition.facebook_threads import scan_comments
from src.acquisition.identity import identify, source_references
from src.acquisition.models import Candidate, Deadline, FetchContext, AdapterError, utcnow
from src.analysis.content_intents import filter_saved_payload, RULE_VERSION
from src.storage.conversations import encode
from src.domain.conversation import ContentNode


def trace_thread(registry, raw, source_id, post_url, window, seconds=120, factory=adapter_job, ocr_budget=None):
    source = registry.sources[source_id]
    if source['source_type'] != 'FACEBOOK_GROUP' or registry.readiness(source):
        raise ValueError('Verified enabled Facebook group required')
    target = identify(post_url)
    if target.platform != 'facebook' or target.kind != 'CONTENT_ITEM' or not target.item_id or target.origin not in source_references(source):
        raise ValueError('Known post must belong to the verified group')
    if not 0 < seconds <= 1200:
        raise ValueError('Invalid thread time budget')
    run_id = 'trace_' + uuid.uuid4().hex
    task_id = 'thread:' + source_id + ':' + target.item_id
    report = dict(run_id=run_id,source_id=source_id,post_native_id=target.item_id,
        requested_window={'start':window.start.isoformat(),'end':window.end.isoformat()},started_at=utcnow(),status='RUNNING',
        comments_supported=True,full_window_coverage_verified=False)
    with raw.transaction():
        raw.db.execute('CREATE TABLE IF NOT EXISTS thread_runs(run_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        raw.db.execute('INSERT INTO thread_runs VALUES (?,?)',(run_id,encode(report)))
    candidate=Candidate('facebook',target.url,target.url,source_id,run_id,'BROWSER_THREAD',platform_item_id=target.item_id)
    root=raw.ingest_candidate(candidate,'discovery')['node_id']
    deadline=Deadline(seconds)
    try:
        with factory(source,deadline,None) as adapter:
            candidate=adapter.fetch_item(candidate,FetchContext(source,window,deadline,raw_first=True)).candidate
            raw.ingest_candidate(candidate,'fetch')
            reserve=min(30,deadline.remaining()*.35) if candidate.media_refs else 0
            comment_deadline=Deadline(max(.1,deadline.remaining()-reserve),deadline)
            try:
                report['coverage']=scan_comments(adapter.page,raw,candidate,root,comment_deadline)
            except AdapterError as error:
                if error.code!='TIME_BUDGET':raise
                report['coverage']={'status':'PARTIAL','stop_reason':'COMMENT_TIME_BUDGET','full_thread_verified':False}
            from engine.image_enrichment import enrich_post
            try:report['ocr']=enrich_post(raw,root,adapter.page,deadline,ocr_budget)
            except Exception:report['ocr']={'status':'FAILED','errors':['OCR_ENRICHMENT_FAILED']}
            report['status']='PARTIAL'
    except AdapterError as error:
        raw.ingest(ContentNode('POST',platform_item_id=target.item_id,canonical_url=target.url,
            extraction_status='FAILED',missing_fields=[error.code],
            availability_status='UNAVAILABLE' if error.code in {'CONTENT_UNAVAILABLE','HTTP_404','SOURCE_NOT_FOUND'} else 'UNKNOWN'),
            source_id,run_id,lineage={'discovered_via':'BROWSER_THREAD','error_code':error.code})
        report.update(status=error.status,error_code=error.code,coverage={'status':'PARTIAL','stop_reason':error.code})
    except Exception:
        report.update(status='EXTRACTION_FAILED',error_code='THREAD_PARSER_FAILED',coverage={'status':'PARTIAL','stop_reason':'THREAD_PARSER_FAILED'})
    # Independent saved-raw filtering: parent intent never decides the children.
    nodes=[n for n in raw.list_nodes(source_id) if n['root_post_id']==root]
    for node in nodes:
        from engine.image_enrichment import filter_node
        decision=filter_node(raw,node)
        raw.filter_saved(node['node_id'],decision,RULE_VERSION)
    report.update(finished_at=utcnow(),stored_thread_nodes=len(nodes),
        nodes_confirmed_in_window=sum(window.status(n['published_at'],n['publication_precision'])=='IN_WINDOW' for n in nodes),
        nodes_unresolved_time=sum(window.status(n['published_at'],n['publication_precision'])=='UNKNOWN' for n in nodes))
    with raw.transaction():
        raw.db.execute('UPDATE thread_runs SET payload=? WHERE run_id=?',(encode(report),run_id))
        raw.db.execute('INSERT INTO conversation_checkpoints VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
            (task_id,encode({'rescan_anchor':target.url,'run_id':run_id,'coverage':report.get('coverage')}),utcnow()))
    return report
