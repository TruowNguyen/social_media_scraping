"""Durable Threads runs, an independent lease and daily slots. Reads never crawl."""
from datetime import datetime,timedelta,timezone,time
from pathlib import Path
import copy
import hashlib
import json
import threading
import uuid
from engine.threads_registry import ThreadsRegistry
from engine.threads_worker import crawl
from src.acquisition.projects import load_projects
from src.acquisition.models import Window,parse_utc,utcnow
from src.storage.conversations import ConversationStore,encode

VN=timezone(timedelta(hours=7))
TERMINAL={'SUCCEEDED','PARTIAL','FAILED','BLOCKED','CANCELLED'}


class ThreadsError(ValueError):
    def __init__(self,code,message,status=400,**details):
        super().__init__(message);self.code,self.status,self.details=code,status,details


def ticks(slots,interval):
    result=[]
    for slot in slots:
        a,b=(sum(int(v)*w for v,w in zip(slot[k].split(':'),(60,1))) for k in ('start','end'))
        values=list(range(a,b,interval))+[b]
        result.append([f'{v//60:02}:{v%60:02}' for v in values])
    return result


class ThreadsService:
    def __init__(self,database,config_dir,enable_scheduler=False,executor=crawl):
        self.database,self.config_dir=Path(database),Path(config_dir)
        self.executor=executor;self.stop=threading.Event();self.cancels={};self.lock=threading.Lock();self.workers=[]
        raw=ConversationStore(database)
        try:
            raw.db.executescript('''
              CREATE TABLE IF NOT EXISTS acquisition_runs(run_id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS acquisition_leases(platform TEXT PRIMARY KEY,token TEXT NOT NULL,run_id TEXT NOT NULL,expires_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS platform_schedules(platform TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
            ''')
            default=dict(schema_version='platform-schedule-v1',platform='THREADS',version=1,enabled=False,project_id='vinwonders_vu_yen',
                scope='POSTS_AND_REPLIES',interval_minutes=45,daily_slots=[{'start':'05:00','end':'08:30'},{'start':'17:00','end':'18:30'}],
                timezone='Asia/Ho_Chi_Minh',next_run_at=None,last_run_id=None,error=None)
            with raw.transaction():raw.db.execute('INSERT OR IGNORE INTO platform_schedules VALUES (?,?,?)',('THREADS',1,encode(default)))
        finally:raw.close()
        self._recover_queue()
        if enable_scheduler:
            self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        for event in list(self.cancels.values()):event.set()
        for worker in self.workers:
            if worker is not threading.current_thread():worker.join(timeout=2)

    def readiness(self,scope='POSTS_AND_REPLIES'):
        config=ThreadsRegistry(self.config_dir).data
        if not config:return 'THREADS_CONFIG_MISSING'
        if not config['enabled']:return 'THREADS_DISABLED'
        if config['verification'].get('search_recent')!='SUPPORTED':return 'SEARCH_UNVERIFIED'
        if scope=='POSTS_AND_REPLIES' and config['verification'].get('public_replies')!='SUPPORTED':return 'REPLIES_UNVERIFIED'
        return None

    def catalog(self):
        registry=ThreadsRegistry(self.config_dir);data=registry.data
        raw=ConversationStore(self.database,initialize=False)
        try:
            totals=dict(raw.db.execute('SELECT source_id,count(DISTINCT node_id) FROM node_sources GROUP BY source_id'))
            lease=raw.db.execute("SELECT run_id,expires_at FROM acquisition_leases WHERE platform='THREADS'").fetchone()
            active=self.get(lease[0]) if lease and parse_utc(lease[1])>datetime.now(timezone.utc) else None
            if active and active['status'] in TERMINAL:active=None
            latest_queries={};wanted={q['query_id'] for q in data['queries']} if data else set()
            for (payload,) in raw.db.execute('SELECT payload FROM acquisition_runs ORDER BY rowid DESC'):
                run=json.loads(payload)
                for query in run.get('query_snapshot',[]):latest_queries.setdefault(query['query_id'],run)
                if wanted<=latest_queries.keys():break
        finally:raw.close()
        queries=[]
        for query in data['queries'] if data else []:
            latest=latest_queries.get(query['query_id'])
            queries.append({**query,'saved_nodes':totals.get(query['query_id'],0),
                'last_run':{k:latest.get(k) for k in ('run_id','status','started_at','finished_at')} if latest else None})
        return {'platform':'THREADS','provider':data['provider'] if data else None,'ready':self.readiness() is None,
            'readiness_error':self.readiness(),'verification':data.get('verification') if data else {},
            'config_version':data['version'] if data else None,'queries':queries,
            'recovery_error':getattr(self,'recovery_error',None),
            'schedule':self.schedule_status(),'current_run':active}

    def get(self,run_id):
        raw=ConversationStore(self.database,initialize=False)
        try:
            row=raw.db.execute('SELECT payload FROM acquisition_runs WHERE run_id=?',(run_id,)).fetchone()
            return json.loads(row[0]) if row else None
        finally:raw.close()

    def history(self):
        raw=ConversationStore(self.database,initialize=False)
        try:return [json.loads(r[0]) for r in raw.db.execute('SELECT payload FROM acquisition_runs ORDER BY rowid DESC LIMIT 30')]
        finally:raw.close()

    def start(self,payload,window=None,trigger='MANUAL',inventory_only=False):
        config=copy.deepcopy(ThreadsRegistry(self.config_dir).data)
        scope=payload.get('scope','POSTS_AND_REPLIES')
        if scope not in {'POST_ONLY','POSTS_AND_REPLIES'}:raise ThreadsError('INVALID_SCOPE','Phạm vi thu thập không hợp lệ.')
        error=self.readiness(scope)
        if error:raise ThreadsError(error,'Threads chưa đủ điều kiện chạy. Kiểm tra kết nối và quyền đọc bình luận.',503)
        project=payload.get('project_id');selected=payload.get('query_ids')
        queries=[q for q in config['queries'] if q['project_id']==project and q['enabled'] and not q['archived']]
        if selected is not None:
            if not isinstance(selected,list) or len(set(selected))!=len(selected) or not set(selected)<={q['query_id'] for q in queries}:raise ThreadsError('INVALID_QUERY','Truy vấn không thuộc dự án hoặc đang tắt.')
            queries=[q for q in queries if q['query_id'] in selected]
        if not queries:raise ThreadsError('NO_ENABLED_QUERIES','Chọn dự án có ít nhất một truy vấn đang bật.')
        if window is None and not inventory_only:
            try:window=Window(parse_utc(payload['window_start']),parse_utc(payload['window_end']))
            except (KeyError,ValueError,TypeError):raise ThreadsError('INVALID_WINDOW','Khoảng thời gian thu thập không hợp lệ.') from None
        if window and window.end>datetime.now(timezone.utc)+timedelta(seconds=5):raise ThreadsError('FUTURE_WINDOW','Không chọn thời gian kết thúc trong tương lai.')
        key=payload.get('idempotency_key')
        if not isinstance(key,str) or not 1<=len(key)<=200:raise ThreadsError('MISSING_REQUEST_ID','Yêu cầu thiếu mã chống chạy trùng.')
        run_id='threads_'+uuid.uuid4().hex;token=uuid.uuid4().hex
        request_hash=hashlib.sha256(encode([project,selected,scope,window.start.isoformat() if window else None,window.end.isoformat() if window else None,inventory_only]).encode()).hexdigest()
        report=dict(run_id=run_id,platform='THREADS',provider=config['provider'],status='QUEUED',trigger=trigger,
            request_hash=request_hash,
            scope=scope,project_id=project,query_snapshot=queries,config_version=config['version'],
            window_start=window.start.isoformat() if window else None,window_end=window.end.isoformat() if window else None,
            task_kind='INVENTORY_REFRESH' if inventory_only else 'ACQUISITION',started_at=utcnow(),jobs=[],counters={},inventory_only=inventory_only)
        raw=ConversationStore(self.database)
        try:
            with raw.transaction():
                previous=raw.db.execute('SELECT payload FROM acquisition_runs WHERE idempotency_key=?',(key,)).fetchone()
                if previous:
                    previous=json.loads(previous[0])
                    if previous.get('request_hash',request_hash)!=request_hash:raise ThreadsError('REQUEST_ID_CONFLICT','Mã yêu cầu đã dùng cho một phạm vi khác. Tạo lượt mới.',409)
                    return previous
                lease=raw.db.execute('SELECT run_id,expires_at FROM acquisition_leases WHERE platform=?',('THREADS',)).fetchone()
                if lease and parse_utc(lease[1])>datetime.now(timezone.utc):raise ThreadsError('PLATFORM_BUSY','Threads đang có lượt thu thập. Mở lượt hiện tại để theo dõi.',409,run_id=lease[0])
                if lease:
                    previous=raw.db.execute('SELECT payload FROM acquisition_runs WHERE run_id=?',(lease[0],)).fetchone()
                    if previous:
                        stale=json.loads(previous[0]);stale.update(status='PARTIAL',error_code='WORKER_LEASE_EXPIRED',finished_at=utcnow(),lease_expired_at=lease[1])
                        raw.db.execute('UPDATE acquisition_runs SET status=?,payload=?,updated_at=? WHERE run_id=?',('PARTIAL',encode(stale),utcnow(),lease[0]))
                expiry=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
                raw.db.execute('INSERT OR REPLACE INTO acquisition_leases VALUES (?,?,?,?)',('THREADS',token,run_id,expiry))
                raw.db.execute('INSERT INTO acquisition_runs VALUES (?,?,?,?,?)',(run_id,key,'QUEUED',encode(report),utcnow()))
        finally:raw.close()
        cancelled=threading.Event();finished=threading.Event();self.cancels[run_id]=cancelled
        def update(value):
            current={**report,**value};raw=ConversationStore(self.database,initialize=False)
            try:
                with raw.transaction():
                    lease=raw.db.execute('SELECT token,expires_at FROM acquisition_leases WHERE platform=?',('THREADS',)).fetchone()
                    if not lease or lease[0]!=token or parse_utc(lease[1])<=datetime.now(timezone.utc):cancelled.set();raise RuntimeError('LEASE_LOST')
                    raw.db.execute('UPDATE acquisition_runs SET status=?,payload=?,updated_at=? WHERE run_id=?',(current['status'],encode(current),utcnow(),run_id))
            finally:raw.close()
        def heartbeat():
            while not finished.wait(10):
                raw=ConversationStore(self.database,initialize=False)
                try:
                    with raw.transaction():
                        count=raw.db.execute('UPDATE acquisition_leases SET expires_at=? WHERE platform=? AND token=? AND expires_at>?',
                            ((datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),'THREADS',token,datetime.now(timezone.utc).isoformat())).rowcount
                        if not count:cancelled.set();return
                finally:raw.close()
        def work():
            threading.Thread(target=heartbeat,daemon=True).start()
            try:
                update({'status':'PROBING'})
                result=self.executor(self.database,config,queries,window,run_id,'POST_ONLY' if inventory_only else scope,projects=load_projects(self.config_dir),progress=update,cancel=cancelled,
                    lease={'platform':'THREADS','token':token})
                update(result)
            except Exception:
                try:update({'status':'FAILED','error_code':'THREADS_WORKER_FAILED','finished_at':utcnow()})
                except Exception:pass
            finally:
                finished.set();self.cancels.pop(run_id,None);raw=ConversationStore(self.database,initialize=False)
                try:
                    with raw.transaction():raw.db.execute('DELETE FROM acquisition_leases WHERE platform=? AND token=?',('THREADS',token))
                finally:raw.close()
        worker=threading.Thread(target=work,daemon=True)
        self.workers=[w for w in self.workers if w.is_alive()]+[worker];worker.start();return report

    def cancel(self,run_id):
        if run_id not in self.cancels:raise ThreadsError('RUN_NOT_ACTIVE','Lượt này không còn đang chạy.',409)
        self.cancels[run_id].set();return {'run_id':run_id,'notice':'Đã yêu cầu dừng; hệ thống giữ phần dữ liệu đã lưu.'}

    def schedule_status(self):
        raw=ConversationStore(self.database,initialize=False)
        try:
            value=json.loads(raw.db.execute('SELECT payload FROM platform_schedules WHERE platform=?',('THREADS',)).fetchone()[0])
            value['project_ids']=value.get('project_ids') or [value['project_id']]
            planned=ticks(value['daily_slots'],value['interval_minutes']);now=datetime.now(VN)
            future=[datetime.combine(now.date()+timedelta(days=days),time.fromisoformat(t),VN) for days in (0,1) for slot in planned for t in slot]
            value['next_run_at']=min((t for t in future if t>now),default=None).isoformat() if value['enabled'] else None
            return {**value,'ticks':planned,'worker_alive':bool(getattr(self,'thread',None) and self.thread.is_alive())}
        finally:raw.close()

    def configure_schedule(self,payload):
        previous=self.schedule_status();value={k:v for k,v in previous.items() if k not in {'ticks','worker_alive'}}
        if payload.get('expected_version')!=value['version']:raise ThreadsError('SCHEDULE_CONFLICT','Lịch đã đổi. Nạp lại để tiếp tục.',409)
        allowed={'enabled','daily_slots','interval_minutes','project_id','project_ids','scope','expected_version'}
        if set(payload)-allowed:raise ThreadsError('INVALID_SCHEDULE','Cấu hình lịch có trường không được hỗ trợ.')
        if 'project_id' in payload and 'project_ids' in payload:raise ThreadsError('INVALID_SCHEDULE','Chỉ gửi một danh sách dự án của lịch.')
        value.update({k:v for k,v in payload.items() if k!='expected_version'})
        if 'project_id' in payload:value['project_ids']=[payload['project_id']]
        projects=value['project_ids']
        if not isinstance(projects,list) or not projects or any(not isinstance(p,str) or not p for p in projects) or len(set(projects))!=len(projects):
            raise ThreadsError('INVALID_SCHEDULE','Chọn ít nhất một dự án, không lặp dự án trong lịch.')
        value.update(schema_version='platform-schedule-v2',project_id=projects[0])
        from engine.dashboard import SearchService
        try:
            SearchService._validate_schedule({**value,'window_mode':'DAILY_SLOTS','interval_min_minutes':value['interval_minutes'],'interval_max_minutes':value['interval_minutes']})
        except (ValueError,KeyError,TypeError):raise ThreadsError('INVALID_SCHEDULE','Kiểm tra giờ hai ca và chu kỳ của lịch.') from None
        if type(value['enabled']) is not bool or value.get('scope') not in {'POST_ONLY','POSTS_AND_REPLIES'}:raise ThreadsError('INVALID_SCHEDULE','Trạng thái hoặc phạm vi lịch không hợp lệ.')
        config=ThreadsRegistry(self.config_dir).data
        if any(not any(q['project_id']==p and q['enabled'] and not q['archived'] for q in config['queries']) for p in projects):raise ThreadsError('NO_ENABLED_QUERIES','Mỗi dự án của lịch cần ít nhất một truy vấn đang bật.')
        if value['enabled'] and self.readiness(value['scope']):raise ThreadsError('THREADS_NOT_READY','Chưa thể bật lịch: Threads chưa đủ điều kiện thu thập.',503)
        value.update(version=value['version']+1,next_run_at=None,error=None)
        raw=ConversationStore(self.database,initialize=False)
        try:
            with raw.transaction():
                changed=raw.db.execute('UPDATE platform_schedules SET version=?,payload=? WHERE platform=? AND version=?',(value['version'],encode(value),'THREADS',previous['version'])).rowcount
                if not changed:raise ThreadsError('SCHEDULE_CONFLICT','Lịch đã đổi. Nạp lại để tiếp tục.',409)
        finally:raw.close()
        return self.schedule_status()

    def tick(self,now=None):
        now=now or datetime.now(timezone.utc);local=now.astimezone(VN);schedule=self.schedule_status()
        if not schedule['enabled']:return None
        for slot,slot_ticks in zip(schedule['daily_slots'],schedule['ticks']):
            start=datetime.combine(local.date(),time.fromisoformat(slot['start']),VN)
            end=datetime.combine(local.date(),time.fromisoformat(slot['end']),VN)
            if local<start:continue
            due=[datetime.combine(local.date(),time.fromisoformat(t),VN) for t in slot_ticks if datetime.combine(local.date(),time.fromisoformat(t),VN)<=local]
            if not due:return None
            moment=due[-1];inventory=moment==start
            window=Window(start.astimezone(timezone.utc),moment.astimezone(timezone.utc)) if not inventory else None
            for project in schedule['project_ids']:
                queries=[(q['query_id'],q['version']) for q in ThreadsRegistry(self.config_dir).data['queries'] if q['project_id']==project and q['enabled'] and not q['archived']]
                key=hashlib.sha256(encode(['THREADS',schedule['version'],queries,project,start.isoformat(),moment.isoformat(),'INVENTORY_REFRESH' if inventory else 'ACQUISITION']).encode()).hexdigest()
                raw=ConversationStore(self.database,initialize=False)
                try:
                    existing=raw.db.execute('SELECT status FROM acquisition_runs WHERE idempotency_key=?',(key,)).fetchone()
                    lease=raw.db.execute("SELECT expires_at FROM acquisition_leases WHERE platform='THREADS'").fetchone()
                finally:raw.close()
                if existing:continue
                if lease and parse_utc(lease[0])>datetime.now(timezone.utc):return None
                result=self.start({'project_id':project,'scope':schedule['scope'],'idempotency_key':key},window,'SCHEDULED',inventory)
                self._schedule_result(run_id=result['run_id']);return result
        return None

    def _loop(self):
        while not self.stop.wait(10):
            try:self.tick()
            except ThreadsError as error:self._schedule_result(error=error.code)
            except Exception:self._schedule_result(error='SCHEDULE_WORKER_FAILED')

    def _schedule_result(self,run_id=None,error=None):
        raw=ConversationStore(self.database,initialize=False)
        try:
            with raw.transaction():
                row=raw.db.execute("SELECT payload FROM platform_schedules WHERE platform='THREADS'").fetchone();value=json.loads(row[0])
                if run_id:value['last_run_id']=run_id
                value['error']=error
                raw.db.execute("UPDATE platform_schedules SET payload=? WHERE platform='THREADS'",(encode(value),))
        finally:raw.close()

    def _recover_queue(self):
        """Recover pre-expiry pages after a crash; never steal a live lease."""
        from src.storage.ingest import IngestQueue
        raw=ConversationStore(self.database,initialize=False)
        try:
            with raw.transaction():
                lease=raw.db.execute("SELECT run_id,expires_at FROM acquisition_leases WHERE platform='THREADS'").fetchone()
                if lease and parse_utc(lease[1])>parse_utc(utcnow()):return
                if lease:
                    row=raw.db.execute('SELECT payload FROM acquisition_runs WHERE run_id=?',(lease[0],)).fetchone()
                    if row:
                        state=json.loads(row[0]);state.update(status='PARTIAL',error_code='WORKER_LEASE_EXPIRED',lease_expired_at=lease[1],finished_at=utcnow())
                        raw.db.execute('UPDATE acquisition_runs SET status=?,payload=?,updated_at=? WHERE run_id=?',('PARTIAL',encode(state),utcnow(),lease[0]))
                    raw.db.execute("DELETE FROM acquisition_leases WHERE platform='THREADS'")
        finally:raw.close()
        queue=IngestQueue(self.database.parent/'ingest'/self.database.stem)
        for path in sorted((queue.directory/'ready').glob('*.json'))[:100]:
            try:
                body=json.loads(path.read_text(encoding='utf-8'))['body'];run_id=body['entries'][0]['run_id']
                queue.drain(self.database,paths=[path],recovery=True)
                raw=ConversationStore(self.database,initialize=False)
                try:
                    with raw.transaction():
                        row=raw.db.execute('SELECT payload FROM acquisition_runs WHERE run_id=?',(run_id,)).fetchone()
                        if row:
                            value=json.loads(row[0]);value['recovered_after_crash']=True
                            value['recovery_committed_nodes']=raw.db.execute('SELECT count(DISTINCT node_id) FROM conversation_observations WHERE run_id=?',(run_id,)).fetchone()[0]
                            raw.db.execute('UPDATE acquisition_runs SET payload=?,updated_at=? WHERE run_id=?',(encode(value),utcnow(),run_id))
                finally:raw.close()
            except (ValueError,KeyError,TypeError,RuntimeError):
                # Invalid/late pages stay quarantined or staged for inspection;
                # they cannot be accepted by a new producer's lease.
                self.recovery_error='UNCOMMITTED_QUEUE_PAGE'
