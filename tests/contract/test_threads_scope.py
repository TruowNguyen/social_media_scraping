"""Entity scoping protects recall while limiting unrelated deep scans."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timezone
from engine.threads_registry import ThreadsRegistry
from engine.threads_worker import crawl
from engine.classification_input import build_item
from src.acquisition.projects import load_projects
from src.acquisition.models import Window
from src.acquisition.threads import node_from_item
from src.analysis.taxonomy import load_snapshot
from src.analysis.threads_scope import evaluate_scope
from src.storage.conversations import ConversationStore

ROOT=Path(__file__).resolve().parents[2]

def item(code,text,media=None):
    return dict(url='https://www.threads.com/@fixture/post/'+code,shortcode=code,
                text=text,username='fixture',timestamp='2026-10-01T01:00:00Z',media_refs=media or [])

class Adapter:
    def __init__(self,items):self.items=items;self.fetched=[]
    def discover(self,request):yield {'items':self.items,'query_verified':True,'parser_version':'fixture'}
    def fetch_item(self,candidate,context):
        self.fetched.append(candidate['url'])
        return {'root':candidate,'replies':[item(candidate['shortcode']+'reply','Chờ 30 phút chưa vào được.')],
                'error_code':'DOM_PARENT_MAPPING_UNVERIFIED'}

class ThreadsScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'raw.sqlite3'
        self.projects=load_projects(ROOT/'config')
        self.config=copy.deepcopy(ThreadsRegistry(ROOT/'config').data)
        self.query=next(q for q in self.config['queries'] if q['query_id']=='threads_vincons_name')
        self.window=Window(datetime(2026,10,1,tzinfo=timezone.utc),datetime(2026,10,2,tzinfo=timezone.utc))
    def tearDown(self):self.tmp.cleanup()
    def run_crawl(self,adapter,run='r1',queries=None):
        return crawl(self.db,self.config,queries or [self.query],self.window,run,
                     adapter=adapter,projects=self.projects)
    def test_alias_boundaries_no_false_vincent_match_and_not_issue_filter(self):
        for text in ['VinCons hôm nay trời đẹp','VIN CONS tan ca','#VinCons','vincons: kẹt cổng']:
            self.assertEqual(evaluate_scope(item('a',text),'vincons',self.projects)['status'],'MATCHED')
        for text in ['Vincent Van Gogh','notvincons','vinconsxyz','Goodwill donations']:
            v=evaluate_scope(item('a',text),'vincons',self.projects)
            self.assertEqual(v['status'],'NO_TARGET_EVIDENCE');self.assertFalse(v['conversation_eligible'])
    def test_project_alias_registry_is_used_and_query_is_not_evidence(self):
        self.projects['vincons']['aliases']=['Công trường A42']
        self.assertEqual(evaluate_scope(item('a','Công trường A42 chờ vào cổng'),'vincons',self.projects)['status'],'MATCHED')
        self.assertEqual(evaluate_scope({**item('b','Vincent'), 'query':'Công trường A42'},'vincons',self.projects)['status'],'NO_TARGET_EVIDENCE')
    def test_missing_caption_images_and_ocr_remain_eligible(self):
        for row in [item('a',None),item('a','Hôm nay kẹt quá',[{'kind':'IMAGE','url':'https://example.invalid/a.jpg'}])]:
            self.assertEqual(evaluate_scope(row,'vincons',self.projects)['status'],'MISSING_EVIDENCE')
        self.assertEqual(evaluate_scope(item('a','Ảnh công trường'),'vincons',self.projects,
            evidence=[{'text':'VinCons chờ vào cổng'}])['status'],'MATCHED')
    def test_unrelated_raw_committed_before_deferral_and_not_deleted_on_rerun(self):
        adapter=Adapter([item('bad','Vincent Van Gogh'),item('good','Vin Cons kẹt cổng')])
        report=self.run_crawl(adapter)
        self.assertEqual(len(adapter.fetched),1)
        self.assertEqual(report['counters']['conversation_deferred_no_target_evidence'],1)
        self.assertTrue(report['jobs'][0]['query_verified'])
        self.assertFalse(report['full_window_coverage_verified'])
        raw=ConversationStore(self.db)
        try:
            bad=node_from_item(adapter.items[0]);self.assertEqual(raw.get(bad.node_id)['raw_text'],'Vincent Van Gogh')
            raw.review(bad.node_id,'NEEDS_REVIEW','Giữ raw để đối chiếu')
            self.assertEqual(raw.db.execute('SELECT count(*) FROM raw_filter_decisions').fetchone()[0],0)
            obs=json.loads(raw.db.execute('SELECT payload FROM conversation_observations WHERE node_id=?',(bad.node_id,)).fetchone()[0])
            self.assertEqual(obs['entity_scope']['status'],'NO_TARGET_EVIDENCE')
        finally:raw.close()
        rerun=self.run_crawl(adapter,'r2')
        self.assertEqual(rerun['counters']['unique_new_post'],0)
        raw=ConversationStore(self.db)
        try:self.assertEqual(raw.db.execute('SELECT count(*) FROM node_reviews').fetchone()[0],1)
        finally:raw.close()
    def test_known_unrelated_root_not_rescanned_but_old_relevant_root_is(self):
        raw=ConversationStore(self.db)
        try:
            for row in [item('bad','Vincent Van Gogh'),item('old','VinCons hôm nay trời đẹp')]:
                raw.ingest(node_from_item({**row,'timestamp':'2025-01-01T00:00:00Z'}),self.query['query_id'],'oldrun')
        finally:raw.close()
        adapter=Adapter([]);report=self.run_crawl(adapter)
        self.assertEqual(adapter.fetched,['https://threads.com/@fixture/post/old'])
        self.assertEqual(report['counters']['rescan_deferred_no_target_evidence'],1)
        self.assertGreater(report['counters']['out_of_window'],0)
    def test_missing_evidence_scan_budget_retains_all_raw(self):
        self.config['limits']['unverified_conversations_per_query']=1
        adapter=Adapter([item('a',None),item('b',None),item('c','VinCons tan ca')])
        report=self.run_crawl(adapter)
        self.assertEqual(len(adapter.fetched),2)
        self.assertEqual(report['counters']['conversation_deferred_missing_evidence'],1)
        self.assertIn('UNVERIFIED_CONVERSATION_LIMIT',report['jobs'][0]['gaps'])
        raw=ConversationStore(self.db)
        try:self.assertIsNotNone(raw.get(node_from_item(adapter.items[1]).node_id))
        finally:raw.close()
    def test_known_child_target_mention_can_reopen_neutral_root(self):
        raw=ConversationStore(self.db)
        try:
            root=node_from_item(item('root','Hôm nay có chuyện này'));raw.ingest(root,self.query['query_id'],'old')
            raw.ingest(node_from_item(item('child','VinCons kẹt cổng'),root=root.node_id,node_type='REPLY',relationship='UNRESOLVED'),self.query['query_id'],'old')
        finally:raw.close()
        adapter=Adapter([]);self.run_crawl(adapter)
        self.assertEqual(len(adapter.fetched),1)
    def test_clear_commercial_skips_deep_scan_but_complaint_is_preserved(self):
        adapter=Adapter([item('sale','VinCons tuyển dụng công nhân. Liên hệ 0901234567'),
                         item('complaint','VinCons tuyển dụng nhiều mà tan ca kẹt cổng, chờ cả tiếng.')])
        report=self.run_crawl(adapter)
        self.assertEqual(len(adapter.fetched),1)
        self.assertTrue(adapter.fetched[0].endswith('/complaint'))
        self.assertEqual(report['counters']['conversation_deferred_commercial'],1)
    def test_cross_query_conversation_fetched_once_with_all_observations(self):
        adapter=Adapter([item('root','VinCons kẹt cổng')]);query={**self.query,'query_id':'threads_vincons_gate','value':'VinCons kẹt cổng'}
        report=self.run_crawl(adapter,queries=[self.query,query]);self.assertEqual(len(adapter.fetched),1)
        self.assertEqual(report['counters']['conversation_reused_in_run'],1)
        raw=ConversationStore(self.db)
        try:self.assertEqual(raw.db.execute("SELECT count(*) FROM node_sources WHERE node_id=?",(node_from_item(adapter.items[0]).node_id,)).fetchone()[0],2)
        finally:raw.close()
    def test_spaced_alias_is_explicit_classifier_evidence_not_query_proof(self):
        raw=ConversationStore(self.db);snapshot=load_snapshot(ROOT/'config/taxonomy/v1')
        try:
            for text,basis in [('Vin Cons kẹt cổng','CONTENT_EXPLICIT'),('Vincent Van Gogh','QUERY_CONTEXT')]:
                node=node_from_item(item('a' if basis=='CONTENT_EXPLICIT' else 'b',text))
                raw.ingest(node,self.query['query_id'],'r',lineage={'query_id':self.query['query_id'],'project_scope_id':'vincons'})
                value=build_item(raw,node.node_id,self.query['query_id'],snapshot)
                self.assertEqual(value['project_candidates'][0]['basis'],basis)
        finally:raw.close()

if __name__=='__main__':unittest.main()
