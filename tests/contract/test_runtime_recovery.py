import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import json
import threading
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from engine.dashboard import SearchService, make_handler
from src.browser.profiles import PROJECT_ROOT
from engine.runtime_recovery import RuntimeRecovery
from engine.runtime_supervisor import Supervisor
from src.acquisition.models import parse_utc
from src.storage.conversations import ConversationStore, encode


def configs():
    slots=[dict(start='05:00',end='08:30'),dict(start='17:00',end='18:30')]
    return {'FACEBOOK':dict(enabled=True,daily_slots=slots,project_ids=[''],source_ids=['s1']),
            'THREADS':dict(enabled=True,daily_slots=slots,project_ids=['p1'],scope='POSTS_AND_REPLIES',
                queries=[dict(query_id='q1',project_id='p1',version=1)])}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name);self.db=self.root/'raw.db'
        self.service=SimpleNamespace(conversation_db=self.db,config_dir=self.root,
            running=False,schedule={},start=Mock(),schedule_tick=Mock(),
            threads=SimpleNamespace(cancels={},tick=Mock(return_value=None),start=Mock(return_value={'run_id':'t1'})))
        self.recovery=RuntimeRecovery(self.service)
        self.raw=ConversationStore(self.db)
        self.raw.db.executescript('CREATE TABLE dashboard_raw_runs(run_id TEXT PRIMARY KEY,payload TEXT); CREATE TABLE acquisition_runs(run_id TEXT PRIMARY KEY,payload TEXT);')
        self.configs=configs()

    def tearDown(self):
        self.raw.close();self.tmp.cleanup()

    def observe(self, now, configs=None):
        for platform,config in (configs or self.configs).items():
            self.recovery.observe(self.raw,platform,config,parse_utc(now) if isinstance(now,str) else now)

    def test_first_install_only_current_day_closed_slots_not_every_tick(self):
        now=parse_utc('2026-10-13T03:00:00Z')
        self.observe(now)
        self.recovery.plan(self.raw,self.configs,now)
        rows=self.recovery.status(self.raw)['recent']
        self.assertEqual(len(rows),2)
        self.assertEqual({r['window_start'] for r in rows},{'2026-10-12T22:00:00+00:00'})
        self.assertEqual({r['window_end'] for r in rows},{'2026-10-13T01:30:00+00:00'})
        self.observe(now);self.recovery.plan(self.raw,self.configs,now)
        self.assertEqual(len(self.recovery.status(self.raw)['recent']),2)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM runtime_schedule_history').fetchone()[0],2)

    def test_three_day_downtime_is_planned_after_restart(self):
        self.observe('2026-10-10T02:00:00Z')
        self.raw.close();self.raw=ConversationStore(self.db,initialize=False)
        now=parse_utc('2026-10-13T03:00:00Z');self.observe(now)
        self.recovery.plan(self.raw,self.configs,now)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM runtime_catchup').fetchone()[0],14)
        self.assertTrue(all(not r['full_window_coverage_verified'] for r in self.recovery.status(self.raw)['recent']))

    def test_existing_full_slot_attempt_is_reused_but_failed_run_is_not(self):
        now=parse_utc('2026-10-13T03:00:00Z');self.observe(now)
        report=dict(status='PARTIAL',window_start='2026-10-12T22:00:00Z',window_end='2026-10-13T01:30:00Z',
            jobs=[dict(source_id='s1',status='PARTIAL',inventory={'status':'SUCCESS'})])
        with self.raw.transaction():self.raw.db.execute('INSERT INTO dashboard_raw_runs VALUES (?,?)',('normal',encode(report)))
        self.recovery.plan(self.raw,self.configs,now)
        statuses={r['platform']:r['status'] for r in self.recovery.status(self.raw)['recent']}
        self.assertEqual(statuses,{'FACEBOOK':'ATTEMPTED','THREADS':'PENDING'})

    def test_disabled_then_enabled_does_not_fabricate_disabled_day_schedule(self):
        self.observe('2026-10-10T02:00:00Z')
        disabled=copy.deepcopy(self.configs)
        for c in disabled.values():c['enabled']=False
        self.observe('2026-10-10T12:00:00Z',disabled)
        self.observe('2026-10-12T20:00:00Z')
        now=parse_utc('2026-10-13T03:00:00Z')
        self.recovery.plan(self.raw,self.configs,now)
        rows=self.recovery.status(self.raw)['recent']
        self.assertEqual(len(rows),6)
        self.assertFalse(any('2026-10-11T' in r['window_end'] for r in rows))

    def test_expire_old_pending_without_deleting_it(self):
        self.observe('2026-10-01T02:00:00Z')
        self.recovery.plan(self.raw,self.configs,parse_utc('2026-10-01T12:00:00Z'))
        self.recovery.plan(self.raw,self.configs,parse_utc('2026-10-13T03:00:00Z'))
        self.assertEqual(self.raw.db.execute("SELECT count(*) FROM runtime_catchup WHERE status='EXPIRED'").fetchone()[0],4)

    def test_mid_slot_change_is_visible_without_guessing_old_settings(self):
        self.observe('2026-10-13T00:00:00Z')  # 07:00, initial assumption covers today.
        changed=copy.deepcopy(self.configs);changed['FACEBOOK']['source_ids']=['s2']
        self.observe('2026-10-13T00:15:00Z',changed)
        self.recovery.plan(self.raw,changed,parse_utc('2026-10-13T03:00:00Z'))
        rows=self.recovery.status(self.raw)['recent']
        self.assertEqual(sum(r['status']=='SKIPPED_PARTIAL_HISTORY' for r in rows),2)
        self.assertEqual(sum(r['platform']=='THREADS' and r['status']=='PENDING' for r in rows),1)

    def test_busy_crawler_does_not_block_other_platform_or_classifier(self):
        self.service.running=True
        with patch.object(self.recovery,'configs',return_value=self.configs):
            self.recovery.tick('2026-10-13T03:00:00Z')
        self.service.start.assert_not_called();self.service.threads.start.assert_called_once()
        self.assertEqual(self.service.threads.start.call_args.args[0]['scope'],'POSTS_AND_REPLIES')

    def test_resume_crash_before_dispatch_uses_stable_facebook_run_id(self):
        with patch.object(self.recovery,'configs',return_value=self.configs):
            self.recovery.tick('2026-10-13T03:00:00Z')
            first=self.service.start.call_args.kwargs['resume_report']['crawl_run_id']
            self.recovery.tick('2026-10-13T03:01:00Z')
            second=self.service.start.call_args.kwargs['resume_report']['crawl_run_id']
        self.assertEqual(first,second)

    def test_source_change_skips_old_snapshot_instead_of_crawling_new_scope(self):
        self.observe('2026-10-10T02:00:00Z')
        changed=copy.deepcopy(self.configs);changed['FACEBOOK']['source_ids']=['s2']
        self.service.threads.cancels={'busy':True}
        with patch.object(self.recovery,'configs',return_value=changed):
            result=self.recovery.tick('2026-10-11T03:00:00Z')
        self.assertGreaterEqual(result['counts']['SKIPPED_CONFIG_CHANGED'],2)
        self.service.start.assert_not_called()

    def test_collecting_threads_run_is_not_retried_and_login_is_blocked(self):
        item=dict(catchup_id='key',platform='THREADS',status='RUNNING',run_id='t1',attempts=1,
            window_start='2026-10-12T22:00:00Z',window_end='2026-10-13T01:30:00Z')
        self.recovery._save(self.raw,'key',item)
        with self.raw.transaction():self.raw.db.execute('INSERT INTO acquisition_runs VALUES (?,?)',('t1',encode({'status':'COLLECTING'})))
        self.recovery.reconcile(self.raw)
        self.assertEqual(self.recovery.status(self.raw)['recent'][0]['status'],'RUNNING')
        with self.raw.transaction():self.raw.db.execute('UPDATE acquisition_runs SET payload=?',
            (encode({'status':'BLOCKED','jobs':[{'status':'BLOCKED','error_code':'LOGIN_REQUIRED'}]}),))
        self.recovery.reconcile(self.raw)
        self.assertEqual(self.recovery.status(self.raw)['recent'][0]['status'],'BLOCKED')


class SupervisorTests(unittest.TestCase):
    def test_actual_child_exit_is_replaced_without_restarting_other_child(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);children=[]
            def launch(module):
                child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],
                    **({'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}))
                children.append(child)
                return child.pid
            supervisor=Supervisor(runtime=root/'runtime',root=root,inventory=lambda:[],launch=launch)
            try:
                supervisor.ensure_workers(0)
                dashboard=children[0].pid
                children[1].kill();children[1].wait(timeout=10)
                supervisor.ensure_workers(10)
                supervisor.ensure_workers(12)
                self.assertEqual(len(children),3)
                self.assertEqual(supervisor.workers['engine.dashboard']['pid'],dashboard)
                self.assertEqual(supervisor.workers['engine.classification_worker']['pid'],children[2].pid)
                self.assertIsNone(children[0].poll())
            finally:
                for child in children:
                    if child.poll() is None:child.kill()
                    child.wait(timeout=10)

    def test_existing_workers_are_adopted_without_launching_duplicates(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);launch=Mock()
            rows=[dict(ProcessId=10,CommandLine=str(root)+' python -m engine.dashboard'),
                  dict(ProcessId=11,CommandLine=str(root)+' python -m engine.classification_worker --serve')]
            supervisor=Supervisor(runtime=root/'runtime',root=root,inventory=lambda:rows,launch=launch)
            with patch('engine.runtime_supervisor._pid_alive',return_value=True):
                supervisor.ensure_workers(0);supervisor.ensure_workers(10)
            launch.assert_not_called()
            self.assertEqual({w['ownership'] for w in supervisor.workers.values()},{'ADOPTED'})

    def test_dead_worker_restarted_with_backoff_while_other_is_kept(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);launch=Mock(side_effect=[20,21,22])
            supervisor=Supervisor(runtime=root/'runtime',root=root,inventory=lambda:[],launch=launch)
            supervisor.ensure_workers(0)
            with patch('engine.runtime_supervisor._pid_alive',side_effect=lambda pid:pid!=21):
                supervisor.ensure_workers(10)
                self.assertEqual(launch.call_count,2)
                supervisor.ensure_workers(11)
                self.assertEqual(launch.call_count,2)
                supervisor.ensure_workers(12)
                self.assertEqual(launch.call_count,3)
            self.assertEqual(supervisor.workers['engine.dashboard']['pid'],20)
            self.assertEqual(supervisor.workers['engine.classification_worker']['pid'],22)

    def test_inconclusive_scan_does_not_start_any_worker(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);launch=Mock()
            supervisor=Supervisor(runtime=root/'runtime',root=root,inventory=Mock(side_effect=RuntimeError('scan')),launch=launch)
            state=supervisor.cycle(0)
            launch.assert_not_called();self.assertEqual(state['status'],'DEGRADED')


class RuntimeAPITests(unittest.TestCase):
    def test_status_is_lightweight_and_catchup_requires_same_origin(self):
        with TemporaryDirectory() as folder:
            db=Path(folder)/'raw.db'
            service=SearchService(db,PROJECT_ROOT/'config')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,PROJECT_ROOT/'config',service=service))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with patch('engine.classification_worker.classification_rows',side_effect=AssertionError('Full scan forbidden')):
                    status=json.load(urlopen(base+'/api/runtime/status',timeout=5))
                self.assertFalse(status['classifier_active'])
                self.assertEqual(status['catchup']['status'],'SUPERVISOR_NOT_CONNECTED')
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(base+'/api/runtime/catchup',data=b'{}',headers={'Origin':'https://elsewhere.invalid','Content-Type':'application/json'}))
                self.assertEqual(denied.exception.code,403)
                status=json.load(urlopen(Request(base+'/api/runtime/catchup',data=b'{}',headers={'Origin':base,'Content-Type':'application/json'}),timeout=5))
                self.assertEqual(status['counts'],{})
                self.assertFalse(service.running)
                self.assertEqual(service.runtime_status()['catchup']['lookback_days'],7)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3);service.close()


if __name__=='__main__':unittest.main()
