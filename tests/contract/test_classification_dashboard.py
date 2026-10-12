from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from engine.dashboard import make_handler

ROOT=Path(__file__).resolve().parents[2]


class DashboardClassificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(base/'legacy.db',ROOT/'config',service=object(),conversation_db=base/'raw.db'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,method,path,headers=None):
        import json
        c=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            c.request(method,path,body='{}' if method=='POST' else None,headers=headers or {})
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()

    def test_empty_shared_view_is_readable_without_legacy_migration(self):
        status,result=self.request('GET','/api/classifications')
        self.assertEqual(status,200);self.assertEqual(result['rows'],[]);self.assertFalse(result['running'])
        from src.analysis.taxonomy import load_snapshot
        from engine.classification_worker import RUNTIME_TAXONOMY
        snapshot=load_snapshot(RUNTIME_TAXONOMY)
        for issue in result['issues']:
            self.assertEqual(set(issue['project_ids']),{pid for pid,p in snapshot['profiles'].items() if issue['issue_id'] in p['issue_priorities']})

    def test_run_requires_same_origin_and_schedules_async_worker(self):
        status,_=self.request('POST','/api/classifications/run',{'Content-Type':'application/json','Origin':'https://untrusted.invalid'})
        self.assertEqual(status,403)
        with patch('engine.classification_service.ClassificationService.start',return_value={'running':True}) as start:
            status,result=self.request('POST','/api/classifications/run',{'Content-Type':'application/json','Origin':'http://127.0.0.1:'+str(self.server.server_port)})
            self.assertEqual(status,202);self.assertTrue(result['running']);start.assert_called_once()
