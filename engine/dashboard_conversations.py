"""Dashboard raw-first Facebook bridge; bounded threads, durable source outcomes."""
import json
from pathlib import Path
from engine.conversation_schedule import CrawlTasks
from engine.conversation_worker import execute_task
from src.acquisition.models import Deadline, utcnow
from src.storage.conversations import ConversationStore, encode
from src.acquisition.projects import project_fields, selected_match


def observation_runs(report):
    """Child acquisition IDs belong to this crawl, never to an entire source history."""
    return list(dict.fromkeys(run_id for job in report.get('jobs', [])
        for run_id in [job.get('inventory', {}).get('run_id'), *[t.get('run_id') for t in job.get('threads', [])]] if run_id))


def warnings(report):
    return list(dict.fromkeys(code for job in report.get('jobs', [])
        for code in [job.get('error_code'), job.get('inventory', {}).get('error_code'),
                     *[t.get('error_code') for t in job.get('threads', [])]] if code))


def observed_nodes(raw, report):
    ids = observation_runs(report)
    if not ids: return []
    # Bound SQL variables even for large/resumed runs.
    nodes = {}
    for offset in range(0, len(ids), 400):
        batch = ids[offset:offset+400]
        for row in raw.db.execute('SELECT DISTINCT n.node_id,n.payload FROM content_nodes n JOIN conversation_observations o ON o.node_id=n.node_id WHERE o.run_id IN ('+','.join('?' for _ in batch)+')', batch):
            nodes[row[0]] = {**json.loads(row[1]), 'node_id':row[0]}
    return list(nodes.values())


def crawl(registry, database, source_ids, window, run_id, executor=execute_task,schedule_context=None,progress_callback=None):
    raw = ConversationStore(database)
    try:
        tasks = CrawlTasks(raw)
        raw.db.execute('CREATE TABLE IF NOT EXISTS dashboard_raw_runs(run_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        report = dict(crawl_run_id=run_id, status='RUNNING', started_at=utcnow(),
                      window_start=window.start.isoformat(), window_end=window.end.isoformat(),
                      pipeline='RAW_V2_THREADS', record_schema_version='conversation-record-v2',
                      node_types=['POST','COMMENT','REPLY'], storage_order='RAW_THEN_FILTER_CLASSIFY',
                      source_ids=source_ids, resume_enabled=True,schedule_context=schedule_context,
                      jobs=[], full_window_coverage_verified=False)
        with raw.transaction():
            saved = raw.db.execute('SELECT payload FROM dashboard_raw_runs WHERE run_id=?',(run_id,)).fetchone()
            if saved: report=json.loads(saved[0])
            report.update(status='RUNNING',finished_at=None)
            raw.db.execute('INSERT OR IGNORE INTO dashboard_raw_runs VALUES (?,?)', (run_id, encode(report)))
            for sid in source_ids:
                task = dict(schema_version='conversation-crawl-task-v2', pipeline='RAW_V2_THREADS',
                            record_schema_version='conversation-record-v2', node_types=['POST','COMMENT','REPLY'],
                            source_id=sid, window_start=window.start.isoformat(), window_end=window.end.isoformat(),
                            inventory_only=False, final_tick=bool(schedule_context and schedule_context.get('final_tick')),
                            schedule_id='dashboard-v2')
                raw.db.execute('INSERT OR IGNORE INTO conversation_tasks(task_id,source_id,payload,status,scheduled_for) VALUES (?,?,?,?,?)',
                    (run_id+':'+sid, sid, encode(task), 'PENDING', utcnow()))
        budget = Deadline(1200)
        from engine.image_enrichment import OCRBudget
        ocr_budget=OCRBudget()
        outcomes = {j['source_id']:j for j in report['jobs']}
        def publish(phase, sid=None, outcome=None):
            if outcome is not None: outcomes[sid] = outcome
            nodes = observed_nodes(raw, {'jobs':list(outcomes.values())})
            report.update(jobs=list(outcomes.values()), updated_at=utcnow(), current_phase=phase,
                progress=dict(total_sources=len(source_ids), completed_sources=sum(j.get('status') not in {'PENDING','RUNNING'} and (j.get('finished_at') is not None or j.get('source_id')!=report.get('current_source')) for j in outcomes.values()),
                    observed_nodes=len(nodes), confirmed_window_nodes=sum(window.status(n['published_at'],n['publication_precision'])=='IN_WINDOW' for n in nodes),
                    unknown_time_nodes=sum(window.status(n['published_at'],n['publication_precision'])=='UNKNOWN' for n in nodes),
                    posts=sum(n['node_type']=='POST' for n in nodes),comments=sum(n['node_type']=='COMMENT' for n in nodes),replies=sum(n['node_type']=='REPLY' for n in nodes)))
            with raw.transaction():
                raw.db.execute('UPDATE dashboard_raw_runs SET payload=? WHERE run_id=?', (encode(report),run_id))
            if progress_callback: progress_callback(report)
        for index,sid in enumerate(source_ids):
            if budget.remaining() < 1:
                outcomes[sid]=dict(source_id=sid, status='PENDING', error_code='RUN_TIME_BUDGET')
                continue
            task = tasks.claim(utcnow(), lease_seconds=1300, task_id=run_id+':'+sid)
            if not task:
                continue
            report.update(current_source=sid,updated_at=utcnow(),status='RUNNING')
            publish('INVENTORY', sid)
            try:
                source=registry.sources.get(sid)
                if source is None or registry.readiness(source):
                    outcome=dict(source_id=sid,status='SKIPPED',error_code='SOURCE_NOT_READY')
                else:
                    options={'seconds':min(120, budget.remaining()/(len(source_ids)-index)),'max_threads':20}
                    if executor is execute_task:
                        options.update(ocr_budget=ocr_budget, progress=lambda phase,outcome:publish(phase,sid,outcome))
                    outcome = executor(registry, raw, task, **options)
            except Exception as error:
                outcome = dict(outcomes.get(sid,{}),source_id=sid, status='EXTRACTION_FAILED',
                    error_code='SOURCE_WORKER_FAILED',error_type=type(error).__name__)
            tasks.finish(task, outcome, utcnow())
            outcome['finished_at']=utcnow()
            publish('SOURCE_FINISHED', sid, outcome)
        report.update(status='PARTIAL', jobs=list(outcomes.values()), finished_at=utcnow(),
            current_source=None, unresolved_time=report.get('progress',{}).get('unknown_time_nodes',0))
        if outcomes and not report.get('progress',{}).get('observed_nodes') and all(j.get('error_code') or j.get('inventory',{}).get('error_code') for j in outcomes.values()):
            report['status']='FAILED'
        publish('FINISHED')
        return report
    finally:
        raw.close()


def pending_run(database):
    """Resume only dashboard-owned runs and only when a durable lease is claimable."""
    if not Path(database).exists(): return None
    raw=ConversationStore(database,initialize=False)
    try:
        exists=raw.db.execute("SELECT 1 FROM sqlite_master WHERE name='dashboard_raw_runs'").fetchone()
        if not exists: return None
        for row in raw.db.execute('SELECT payload FROM dashboard_raw_runs ORDER BY rowid'):
            report=json.loads(row[0])
            if not report.get('resume_enabled'): continue
            for sid in report['source_ids']:
                task=raw.db.execute('SELECT status,attempts,lease_until FROM conversation_tasks WHERE task_id=?',(report['crawl_run_id']+':'+sid,)).fetchone()
                if task and task['status'] in {'PENDING','RUNNING'} and task['attempts']<3 and (not task['lease_until'] or task['lease_until']<=utcnow()):
                    return report
        return None
    finally: raw.close()


def results(database, window, sources, projects, project_id=None, source_ids=None, report=None):
    if not Path(database).exists():
        return []
    raw = ConversationStore(database,initialize=False)
    try:
        rows = []
        observed = {n['node_id'] for n in observed_nodes(raw,report)} if report is not None else None
        for node in raw.list_nodes(window=window):
            if observed is not None and node['node_id'] not in observed: continue
            ids = [r[0] for r in raw.db.execute('SELECT source_id FROM node_sources WHERE node_id=?', (node['node_id'],))]
            ids = [s for s in ids if source_ids is None or s in source_ids]
            if not ids:
                continue
            sid = ids[0]
            fields = project_fields(dict(raw_text=node['raw_text'], context_source_id=sid), projects)
            if not selected_match(fields, project_id):
                continue
            rows.append(dict(url=node['display_url'], platform=node['platform'].lower(), group=sources.get(sid,{}).get('name',sid),
                group_url=sources.get(sid,{}).get('url'), published_at=node['published_at'], verified_time=True,
                title=node['node_type']+' · '+((node['raw_text'] or '')[:180] or 'Chưa đọc được nội dung'),
                node_type=node['node_type'], node_id=node['node_id'], summary=None, issue=None, **fields))
        return sorted(rows, key=lambda r:r['published_at'], reverse=True)
    finally:
        raw.close()
