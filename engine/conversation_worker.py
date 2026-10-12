"""One durable source task: inventory first, fair old-thread rescan, saved raw filter."""
import uuid
from engine.acquisition import adapter_job
from engine.conversation_schedule import CrawlTasks
from engine.group_tracing import trace_thread
from src.acquisition.models import AdapterError, Deadline, DiscoveryRequest, Window, parse_utc, utcnow


def inventory_source(registry, raw, source_id, window, seconds=120, max_candidates=100, factory=adapter_job, listing_seconds=None, stall_limit=3):
    source = registry.sources[source_id]
    if source['source_type'] != 'FACEBOOK_GROUP' or registry.readiness(source):
        raise ValueError('Verified enabled Facebook group required')
    deadline = Deadline(seconds)
    run_id = 'inventory_' + uuid.uuid4().hex
    tasks = CrawlTasks(raw)
    with factory(source,deadline,None) as adapter:
        batch = adapter.discover(DiscoveryRequest(source,run_id,window,deadline,'RECENT_SOURCE_ITEMS',max_candidates,listing_seconds=listing_seconds,stall_limit=stall_limit))
        for candidate in batch.candidates:
            # Save all observed posts including old/pinned/ads, before any filtering.
            node_id = raw.ingest_candidate(candidate,'inventory')['node_id']
            tasks.add_post(source_id,node_id,candidate.canonical_url)
    return dict(run_id=run_id,status=batch.status,error_code=batch.error_code,
        observed_posts=len(batch.candidates),observed_order=batch.observed_order,
        coverage={'status':'PARTIAL','stop_reason':batch.stop_reason,'full_group_inventory_verified':False})


def execute_task(registry,raw,task,seconds=1200,max_threads=20,factory=adapter_job,ocr_budget=None):
    from datetime import timedelta
    if not 0 < seconds <= 1200 or not 0 < max_threads <= 200:
        raise ValueError('Invalid run limits')
    budget = Deadline(seconds)
    start,end = parse_utc(task['window_start']),parse_utc(task['window_end'])
    # Opening tick only discovers inventory; no empty acquisition window is invented.
    window = Window(start-timedelta(microseconds=1),end) if task['inventory_only'] else Window(start,end)
    result = dict(task_id=task['task_id'],source_id=task['source_id'],status='PARTIAL',threads=[],
        requested_window=None if task['inventory_only'] else {'start':start.isoformat(),'end':end.isoformat()},
        full_window_coverage_verified=False)
    tasks=CrawlTasks(raw)
    from engine.image_enrichment import OCRBudget
    ocr_budget=ocr_budget or OCRBudget()
    try:
        result['inventory']=inventory_source(registry,raw,task['source_id'],window,min(120,budget.remaining()),factory=factory)
    except AdapterError as error:
        result['inventory']={'status':error.status,'error_code':error.code}
    except Exception:
        result['inventory']={'status':'EXTRACTION_FAILED','error_code':'INVENTORY_FAILED'}
    if task['inventory_only']: return result
    # A failing discovery doesn't erase the inventory. Access blockers stop this source.
    inventory=result['inventory']
    if inventory['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED','SKIPPED'}:
        result['status']=inventory['status']; return result
    for post in tasks.fair_posts(task['source_id'],max_threads):
        if budget.remaining()<1: break
        outcome=trace_thread(registry,raw,task['source_id'],post['post_url'],window,min(120,budget.remaining()),factory,ocr_budget)
        tasks.scanned(task['source_id'],post['node_id'],outcome,utcnow())
        result['threads'].append(outcome)
        if outcome.get('error_code')=='PROFILE_IN_USE':
            result.update(status='SKIPPED',error_code='PROFILE_IN_USE')
            return result
        if outcome['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED','SKIPPED'}: break
    result['coverage']={'status':'PARTIAL','stop_reason':'BOUNDED_FAIR_INVENTORY_SWEEP',
        'inventory_posts':raw.db.execute('SELECT count(*) FROM thread_inventory WHERE source_id=?',(task['source_id'],)).fetchone()[0],
        'threads_attempted':len(result['threads'])}
    return result
