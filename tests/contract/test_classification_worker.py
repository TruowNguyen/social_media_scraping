from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from engine.classification_worker import classification_cycle,classification_rows,reconcile_saved
from src.analysis.taxonomy import load_snapshot
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore

ROOT=Path(__file__).resolve().parents[2]


class Provider:
    model='fixture-model'
    require_intents=True
    def __init__(self):self.telemetry=[];self.calls=0
    def __call__(self,request):
        self.calls+=1;self.telemetry.append({'batch_id':request['batch_id'],'status':'FIXTURE_RESPONSE'})
        return {'schema_version':'classification-result-v2','batch_id':request['batch_id'],'results':[
            {'item_id':i['item_id'],'revision_id':i['revision_id'],'relevance':'KEEP','project_matches':i['project_candidates'],
             'issues':[{'issue_id':'ENTRY_QUEUE','summary':'Chờ vào cổng lâu','location':None,
                'evidence':[{'evidence_id':i['target']['evidence_id'],'origin_item_id':i['item_id'],'quote':i['target']['text']}]}],
             'content_intents':['COMPLAINT'],'confidence':None,'needs_review':False,'review_reason':None,'drop_reason':None} for i in request['items']]}


class WorkerTests(unittest.TestCase):
    def test_reconciliation_releases_writer_and_preserves_concurrent_events(self):
        from unittest.mock import patch
        from engine.classification_input import prepare_saved
        other=ConversationStore(self.raw.path,initialize=False)
        def prepare(*args):
            self.assertFalse(self.raw.db.in_transaction)
            result=prepare_saved(*args)
            with other.transaction():
                node=other.get(self.child)
                other._event(self.child,node['revision_id'],'CONCURRENT_OCR', '2026-10-11T12:00:00Z')
            return result
        try:
            with patch('engine.classification_worker.prepare_saved',side_effect=prepare):
                reconcile_saved(self.raw,self.snapshot,'fixture-model')
            self.assertEqual(self.raw.db.execute("SELECT status FROM conversation_outbox WHERE kind='CONCURRENT_OCR'").fetchone()[0],'PENDING')
            reconcile_saved(self.raw,self.snapshot,'fixture-model')
            self.assertEqual(self.raw.db.execute("SELECT status FROM conversation_outbox WHERE kind='CONCURRENT_OCR'").fetchone()[0],'CONSUMED')
        finally:other.close()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.raw=ConversationStore(Path(self.tmp.name)/'raw.db')
        self.snapshot=load_snapshot(ROOT/'specs/taxonomy/v1')
        for d in [self.snapshot['catalog'],*self.snapshot['profiles'].values()]: d.update(status='APPROVED',runtime_enabled=True)
        self.source=self.snapshot['profiles']['vinwonders_vu_yen']['source_ids'][0]
        self.url='https://www.facebook.com/groups/123/posts/111'
        self.parent=self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=self.url,raw_text='Bán vé VinWonders Vũ Yên, inbox đặt vé'),self.source,'run')['node_id']
        self.child=self.raw.ingest(ContentNode('COMMENT',platform_item_id='222',root_post_id=self.parent,parent_node_id=self.parent,raw_text='Chờ 40 phút chưa vào được cổng'),self.source,'run')['node_id']

    def tearDown(self):self.raw.close();self.tmp.cleanup()

    def test_saved_raw_filter_batch_provider_validation_persist_and_reconcile(self):
        provider=Provider();result=classification_cycle(self.raw,self.snapshot,provider)
        self.assertEqual(result['accepted'],1);self.assertEqual(result['skipped'],1)
        self.assertEqual(len(self.raw.list_nodes()),2)
        self.assertEqual(self.raw.db.execute("SELECT count(*) FROM conversation_outbox WHERE status='PENDING'").fetchone()[0],0)
        rows={r['node_id']:r for r in classification_rows(self.raw,self.snapshot)}
        self.assertEqual(rows[self.parent]['processing_status'],'FILTER_DROP')
        self.assertEqual(rows[self.child]['analysis']['relevance'],'KEEP')
        self.assertEqual(rows[self.child]['analysis']['content_intents'],['COMPLAINT'])
        again=classification_cycle(self.raw,self.snapshot,provider)
        self.assertEqual(again['api_calls'],0);self.assertEqual(provider.calls,1)

    def test_parent_edit_invalidates_analysis_and_reprocesses_only_new_binding(self):
        provider=Provider();classification_cycle(self.raw,self.snapshot,provider)
        self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=self.url,raw_text='Bán vé VinWonders Vũ Yên giá rẻ, inbox ngay'),self.source,'run2')
        rows={r['node_id']:r for r in classification_rows(self.raw,self.snapshot)}
        self.assertIsNone(rows[self.child]['analysis'])
        self.assertEqual(rows[self.child]['processing_status'],'STALE')
        self.assertIn('Kết quả cũ',rows[self.child]['reason_vi'])
        self.assertEqual(classification_cycle(self.raw,self.snapshot,provider)['accepted'],1)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],2)

    def test_model_switch_preserves_valid_results_but_classifies_changed_input(self):
        original=Provider();classification_cycle(self.raw,self.snapshot,original)
        jobs_before=self.raw.db.execute('SELECT count(*) FROM classification_jobs').fetchone()[0]
        replacement=Provider();replacement.model='replacement-model'
        result=classification_cycle(self.raw,self.snapshot,replacement)
        self.assertEqual(result['completed_reused'],1)
        self.assertEqual(result['jobs_inserted'],0)
        self.assertEqual(replacement.calls,0)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM classification_jobs').fetchone()[0],jobs_before)
        row=next(r for r in classification_rows(self.raw,self.snapshot) if r['node_id']==self.child)
        self.assertEqual(row['model_id'],'fixture-model')
        self.assertEqual(row['processing_status'],'DONE')
        self.raw.ingest(ContentNode('COMMENT',platform_item_id='222',root_post_id=self.parent,
            parent_node_id=self.parent,raw_text='Chờ 50 phút chưa vào được cổng'),self.source,'edited')
        changed=classification_cycle(self.raw,self.snapshot,replacement)
        self.assertEqual(changed['completed_reused'],0)
        self.assertEqual(changed['accepted'],1)
        self.assertEqual(replacement.calls,1)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],2)

    def test_model_switch_requeues_failed_inputs_without_reusing_invalid_results(self):
        from src.analysis.gemini_gateway import ProviderError
        class Broken(Provider):
            def __call__(self,request):raise ProviderError('PROVIDER_HTTP_ERROR')
        classification_cycle(self.raw,self.snapshot,Broken())
        replacement=Provider();replacement.model='replacement-model'
        result=classification_cycle(self.raw,self.snapshot,replacement)
        self.assertEqual(result['completed_reused'],0)
        self.assertEqual(result['jobs_inserted'],1)
        self.assertEqual(result['accepted'],1)
        self.assertEqual(replacement.calls,1)

    def test_missing_live_intent_is_rejected_without_losing_raw(self):
        class Missing(Provider):
            def __call__(self,request):
                result=super().__call__(request)
                for r in result['results']:r.pop('content_intents')
                return result
        result=classification_cycle(self.raw,self.snapshot,Missing())
        self.assertEqual(result['accepted'],0);self.assertEqual(result['invalid_items'],1)
        self.assertEqual(len(self.raw.list_nodes()),2)

    def test_runtime_gate_blocks_draft_before_model_call(self):
        self.snapshot['catalog']['status']='DRAFT'
        provider=Provider()
        with self.assertRaises(ValueError):classification_cycle(self.raw,self.snapshot,provider)
        self.assertEqual(provider.calls,0)

    def test_missing_text_excluded_and_queue_only_reconciliation_is_idempotent(self):
        empty=self.raw.ingest(ContentNode('COMMENT',platform_item_id='333',root_post_id=self.parent,
            parent_node_id=self.parent,raw_text=None),self.source,'empty')['node_id']
        before={r['node_id']:r for r in classification_rows(self.raw,self.snapshot)}
        self.assertEqual(before[empty]['processing_status'],'MISSING_TEXT')
        self.assertEqual(before[self.child]['processing_status'],'UNCLASSIFIED')
        prepared,inserted=reconcile_saved(self.raw,self.snapshot,'fixture-model')
        self.assertEqual(inserted,1)
        self.assertEqual({i['reason'] for i in prepared['skipped']},{'FILTER_DROP','MISSING_TEXT'})
        self.assertEqual(reconcile_saved(self.raw,self.snapshot,'fixture-model')[1],0)
        after={r['node_id']:r for r in classification_rows(self.raw,self.snapshot)}
        self.assertEqual(after[self.child]['processing_status'],'PENDING')
        self.assertEqual(after[empty]['processing_status'],'MISSING_TEXT')
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],0)
