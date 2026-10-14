"""Durable closed-slot catch-up, driven by the local supervisor (no hidden reads)."""
from datetime import datetime, timedelta, time, timezone
import hashlib
import json
from src.acquisition.models import Window, parse_utc, utcnow
from src.storage.conversations import ConversationStore, encode
from engine.registry import Registry
from engine.threads_registry import ThreadsRegistry
from src.acquisition.projects import load_projects

VN = timezone(timedelta(hours=7))
DDL = '''
CREATE TABLE IF NOT EXISTS runtime_schedule_history(
 id INTEGER PRIMARY KEY,platform TEXT NOT NULL,fingerprint TEXT NOT NULL,
 effective_from TEXT NOT NULL,effective_until TEXT,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_catchup(
 catchup_id TEXT PRIMARY KEY,platform TEXT NOT NULL,status TEXT NOT NULL,
 payload TEXT NOT NULL,updated_at TEXT NOT NULL);
'''


class RuntimeRecovery:
    def __init__(self, service, days=7):
        if type(days) is not int or not 1 <= days <= 30:
            raise ValueError('Catch-up days must be 1–30')
        self.service, self.database, self.days = service, service.conversation_db, days
        raw = ConversationStore(self.database)
        try:
            raw.db.executescript(DDL)
        finally:
            raw.close()

    def configs(self):
        fb = self.service.schedule_status()
        registry = Registry(self.service.config_dir)
        project = load_projects(self.service.config_dir).get(fb.get('project_id'))
        ids = [sid for sid in registry.watchlists['vincons_acquisition_v1']['source_ids']
               if registry.sources[sid]['source_type'] == 'FACEBOOK_GROUP'
               and not registry.readiness(registry.sources[sid])
               and (not project or sid in project['source_ids'])]
        threads = self.service.threads.schedule_status()
        config = ThreadsRegistry(self.service.config_dir).data
        queries = [{k:q[k] for k in ('query_id','project_id','version')}
                   for q in config['queries'] if q['enabled'] and not q['archived']] if config else []
        return {
            'FACEBOOK': dict(enabled=fb['enabled'] and fb['window_mode']=='DAILY_SLOTS',
                daily_slots=fb['daily_slots'], project_ids=[fb.get('project_id') or ''], source_ids=ids),
            'THREADS': dict(enabled=threads['enabled'],daily_slots=threads['daily_slots'],
                project_ids=threads['project_ids'], queries=queries,scope=threads['scope']),
        }

    @staticmethod
    def observe(raw, platform, config, now):
        fingerprint = hashlib.sha256(encode(config).encode()).hexdigest()
        previous = raw.db.execute('SELECT * FROM runtime_schedule_history WHERE platform=? ORDER BY id DESC LIMIT 1',(platform,)).fetchone()
        if previous and previous['fingerprint']==fingerprint:
            return
        # First installation covers only the current local day, with an explicit
        # assumption. Never fabricate a schedule for earlier unobserved days.
        initial = previous is None
        start = datetime.combine(now.astimezone(VN).date(),time(),VN).astimezone(timezone.utc) if initial else now
        with raw.transaction():
            if previous:
                raw.db.execute('UPDATE runtime_schedule_history SET effective_until=? WHERE id=?',(now.isoformat(),previous['id']))
            raw.db.execute('INSERT INTO runtime_schedule_history(platform,fingerprint,effective_from,payload) VALUES (?,?,?,?)',
                (platform,fingerprint,start.isoformat(),encode({**config,'initial_current_day_assumption':initial})))

    @staticmethod
    def _attempted(raw, platform, project, start, end, snapshot):
        table = 'dashboard_raw_runs' if platform=='FACEBOOK' else 'acquisition_runs'
        if not raw.db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
            return False
        for (value,) in raw.db.execute('SELECT payload FROM '+table+' ORDER BY rowid DESC'):
            report=json.loads(value)
            if not report.get('window_start') or not report.get('window_end'):
                continue
            if parse_utc(report['window_start'])>start or parse_utc(report['window_end'])<end:
                continue
            if report.get('status') in {'RUNNING','QUEUED','PROBING'}:
                continue
            jobs=report.get('jobs',[])
            if platform=='FACEBOOK':
                attempted={j.get('source_id') for j in jobs if j.get('status')=='PARTIAL'
                           and j.get('inventory',{}).get('status') in {'SUCCESS','PARTIAL'}}
                if set(snapshot['source_ids']) and set(snapshot['source_ids'])<=attempted:
                    return True
            elif report.get('project_id')==project:
                wanted={q['query_id'] for q in snapshot['queries'] if q['project_id']==project}
                versions={(q['query_id'],q['version']) for q in report.get('query_snapshot',[])}
                expected={(q['query_id'],q['version']) for q in snapshot['queries'] if q['project_id']==project}
                attempted={j.get('query_id') for j in jobs if j.get('status') not in {'FAILED','SKIPPED','BLOCKED'} and not j.get('error_code')}
                if wanted and wanted<=attempted and expected<=versions:
                    return True
        return False

    def plan(self, raw, configs, now):
        cutoff=now-timedelta(days=self.days)
        with raw.transaction():
            for row in raw.db.execute("SELECT catchup_id,payload FROM runtime_catchup WHERE status='PENDING'").fetchall():
                if parse_utc(json.loads(row['payload'])['window_end'])<cutoff:
                    self._save(raw,row['catchup_id'],json.loads(row['payload']),status='EXPIRED',error_code='CATCHUP_LOOKBACK_EXCEEDED')
        for history in raw.db.execute('SELECT * FROM runtime_schedule_history ORDER BY id').fetchall():
            config=json.loads(history['payload'])
            if not config['enabled']:
                continue
            effective_start=parse_utc(history['effective_from'])
            effective_end=parse_utc(history['effective_until']) if history['effective_until'] else now
            first=max(effective_start,cutoff).astimezone(VN).date()
            last=min(effective_end,now).astimezone(VN).date()
            day=first
            while day<=last:
                for slot in config['daily_slots']:
                    start=datetime.combine(day,time.fromisoformat(slot['start']),VN).astimezone(timezone.utc)
                    end=datetime.combine(day,time.fromisoformat(slot['end']),VN).astimezone(timezone.utc)
                    if end>now or end<cutoff or end<=effective_start or start>=effective_end:
                        continue
                    for project in config['project_ids']:
                        key=hashlib.sha256(encode([history['platform'],history['fingerprint'],project,start.isoformat(),end.isoformat()]).encode()).hexdigest()
                        if raw.db.execute('SELECT 1 FROM runtime_catchup WHERE catchup_id=?',(key,)).fetchone():
                            continue
                        payload=dict(catchup_id=key,platform=history['platform'],project_id=project,
                            window_start=start.isoformat(),window_end=end.isoformat(),snapshot=config,
                            history_id=history['id'],attempts=0,full_window_coverage_verified=False)
                        # Never silently invent settings for the other half of a
                        # slot whose configuration changed while it was open.
                        status=('SKIPPED_PARTIAL_HISTORY' if start<effective_start or end>effective_end else
                            'ATTEMPTED' if self._attempted(raw,history['platform'],project,start,end,config) else 'PENDING')
                        self._save(raw,key,payload,status=status,covered_by_existing_run=status=='ATTEMPTED')
                day+=timedelta(days=1)

    @staticmethod
    def _save(raw, key, payload, **updates):
        value={**payload,**updates,'updated_at':utcnow()}
        with raw.transaction():
            raw.db.execute('INSERT INTO runtime_catchup VALUES (?,?,?,?,?) ON CONFLICT(catchup_id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at',
                (key,value['platform'],value['status'],encode(value),value['updated_at']))
        return value

    def reconcile(self, raw):
        for row in raw.db.execute("SELECT payload FROM runtime_catchup WHERE status='RUNNING'").fetchall():
            item=json.loads(row[0]);run_id=item.get('run_id')
            table='dashboard_raw_runs' if item['platform']=='FACEBOOK' else 'acquisition_runs'
            exists=raw.db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone()
            run=raw.db.execute('SELECT payload FROM '+table+' WHERE run_id=?',(run_id,)).fetchone() if run_id and exists else None
            if not run:
                # Stable request/run identity repairs a crash before dispatch.
                self._save(raw,item['catchup_id'],item,status='PENDING')
                continue
            report=json.loads(run[0])
            if report['status'] not in {'SUCCESS','SUCCEEDED','PARTIAL','FAILED','BLOCKED','CANCELLED'}:
                continue
            errors={j.get('error_code') or j.get('inventory',{}).get('error_code') for j in report.get('jobs',[])}-{None}
            errors.add(report.get('error_code'));errors.discard(None)
            blockers={'LOGIN_REQUIRED','CAPTCHA','PRIVATE_GROUP','HTTP_ACCESS_DENIED','CONTENT_UNAVAILABLE','PROVIDER_AUTH_DENIED'}
            good=any(j.get('status') not in {'FAILED','SKIPPED','ACCESS_DENIED','AUTH_REQUIRED','EXTRACTION_FAILED','SOURCE_UNAVAILABLE'} for j in report.get('jobs',[]))
            if 'PROFILE_IN_USE' in errors or (not good and not errors.intersection(blockers)):
                status='PENDING' if item['attempts']<3 else 'FAILED'
            elif errors.intersection(blockers):
                status='BLOCKED'
            else:
                status='ATTEMPTED'
            # Facebook's existing durable tasks resume the same run on profile busy.
            if item['platform']=='FACEBOOK' and 'PROFILE_IN_USE' in errors:
                status='RUNNING'
            self._save(raw,item['catchup_id'],item,status=status,errors=sorted(errors))

    def tick(self, now=None):
        now=parse_utc(now or utcnow());configs=self.configs()
        raw=ConversationStore(self.database,initialize=False)
        try:
            for platform,config in configs.items():
                self.observe(raw,platform,config,now)
            self.reconcile(raw)
            self.plan(raw,configs,now)
            for row in raw.db.execute("SELECT payload FROM runtime_catchup WHERE status='PENDING' ORDER BY json_extract(payload,'$.window_end') DESC").fetchall():
                item=json.loads(row[0]);platform=item['platform'];current=configs[platform]
                if not current['enabled']:
                    continue
                snapshot=item['snapshot']
                if platform=='FACEBOOK':
                    if self.service.running:
                        continue
                    if not set(snapshot['source_ids'])<=set(current['source_ids']) or item['project_id'] not in current['project_ids']:
                        self._save(raw,item['catchup_id'],item,status='SKIPPED_CONFIG_CHANGED');continue
                    due=self.service.schedule.get('next_run_at')
                    if due and parse_utc(due)<=now:
                        self.service.schedule_tick(now)
                        continue
                    identifier='dashboard_'+hashlib.sha256(('catchup:'+item['catchup_id']).encode()).hexdigest()[:32]
                    self._save(raw,item['catchup_id'],item,status='RUNNING',run_id=identifier,attempts=item['attempts']+1)
                    try:
                        self.service.start({'project_id':item['project_id'] or None},'CRAWL',
                            window_override=Window(parse_utc(item['window_start']),parse_utc(item['window_end'])),
                            resume_report=dict(crawl_run_id=identifier,source_ids=snapshot['source_ids']))
                    except Exception:
                        self._save(raw,item['catchup_id'],item,status='PENDING',error_code='DISPATCH_RETRY')
                        raise
                else:
                    if self.service.threads.cancels:
                        continue
                    if any(q not in current['queries'] for q in snapshot['queries'] if q['project_id']==item['project_id']) or item['project_id'] not in current['project_ids']:
                        self._save(raw,item['catchup_id'],item,status='SKIPPED_CONFIG_CHANGED');continue
                    # Normal due ticks get first chance; their lease serializes jobs.
                    if self.service.threads.tick(now):
                        continue
                    payload=dict(project_id=item['project_id'],scope=snapshot['scope'],
                        query_ids=[q['query_id'] for q in snapshot['queries'] if q['project_id']==item['project_id']],
                        idempotency_key='catchup:'+item['catchup_id']+':'+str(item['attempts']))
                    result=self.service.threads.start(payload,Window(parse_utc(item['window_start']),parse_utc(item['window_end'])),'CATCHUP')
                    self._save(raw,item['catchup_id'],item,status='RUNNING',run_id=result['run_id'],attempts=item['attempts']+1)
                # One start per platform per tick; other platform may proceed next tick.
                break
            return self.status(raw)
        finally:
            raw.close()

    def status(self, raw=None):
        own=raw is None
        raw=raw or ConversationStore(self.database,initialize=False)
        try:
            counts=dict(raw.db.execute('SELECT status,count(*) FROM runtime_catchup GROUP BY status'))
            rows=[json.loads(r[0]) for r in raw.db.execute('SELECT payload FROM runtime_catchup ORDER BY updated_at DESC LIMIT 20')]
            return dict(schema_version='runtime-recovery-v1',lookback_days=self.days,counts=counts,
                recent=[{k:r.get(k) for k in ('catchup_id','platform','project_id','window_start','window_end','status','run_id','attempts','errors','full_window_coverage_verified')} for r in rows])
        finally:
            if own:raw.close()
