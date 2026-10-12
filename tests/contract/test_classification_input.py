from pathlib import Path
import tempfile
import unittest
from engine.classification_input import build_item,prepare_saved,build_batches,job_key
from src.analysis.taxonomy import load_snapshot
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore


ROOT=Path(__file__).resolve().parents[2]


class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.raw=ConversationStore(Path(self.tmp.name)/'raw.sqlite3')
        self.snapshot=load_snapshot(ROOT/'specs/taxonomy/v1')
        self.source=self.snapshot['profiles']['vinwonders_vu_yen']['source_ids'][0]
        self.url='https://www.facebook.com/groups/123/posts/111'

    def tearDown(self):
        self.raw.close();self.tmp.cleanup()

    def thread(self,parent_text='Bán vé VinWonders Vũ Yên giá rẻ, inbox mua vé',child_text='Chờ 40 phút vẫn chưa vào được cổng.'):
        root=self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=self.url,raw_text=parent_text),self.source,'run')['node_id']
        child=self.raw.ingest(ContentNode('COMMENT',platform_item_id='222',root_post_id=root,parent_node_id=root,raw_text=child_text),self.source,'run')['node_id']
        return root,child

    def test_parent_ad_never_gates_complaint_child_and_raw_remains(self):
        root,child=self.thread()
        result=prepare_saved(self.raw,self.snapshot,self.source)
        self.assertIn(child,[i['item_id'] for i in result['items']])
        self.assertEqual(len(self.raw.list_nodes()),2)
        item=build_item(self.raw,child,self.source,self.snapshot)
        self.assertEqual(item['project_candidates'][0]['basis'],'PARENT_CONTEXT')
        self.assertEqual(item['context'][0]['item_id'],root)

    def test_source_context_does_not_invent_explicit_project(self):
        _,child=self.thread(parent_text='Hôm nay thế nào?')
        item=build_item(self.raw,child,self.source,self.snapshot)
        self.assertEqual(item['project_candidates'][0]['basis'],'GROUP_CONTEXT')
        self.assertEqual(item['project_candidates'][0]['evidence_ids'],[])

    def test_context_edit_changes_idempotent_binding(self):
        root,child=self.thread()
        first=job_key(build_item(self.raw,child,self.source,self.snapshot),self.snapshot,'model')
        self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=self.url,raw_text='VinWonders Vũ Yên hôm nay đông'),self.source,'run2')
        second=job_key(build_item(self.raw,child,self.source,self.snapshot),self.snapshot,'model')
        self.assertNotEqual(first,second)

    def test_policy_version_invalidates_only_affected_inputs(self):
        import hashlib,json
        from engine.classification_input import PROMPT_VERSION,RULE_VERSION
        _,child=self.thread()
        item=build_item(self.raw,child,self.source,self.snapshot)
        def legacy_key(value):
            binding=dict(item=value,taxonomy=self.snapshot,prompt_version=PROMPT_VERSION,rule_version=RULE_VERSION,model='model')
            return hashlib.sha256(json.dumps(binding,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(job_key(item,self.snapshot,'model'),legacy_key(item))
        commercial={**item,'target':dict(item['target'],text='Giới thiệu dịch vụ mới')}
        self.assertNotEqual(job_key(commercial,self.snapshot,'model'),legacy_key(commercial))

    def test_context_refinement_invalidates_only_the_ocr_exception_scope(self):
        from unittest.mock import patch
        _,child=self.thread()
        item=build_item(self.raw,child,self.source,self.snapshot)
        def previous_key(value):
            with patch('src.analysis.ocr_policy.context_commercial_policy_affected',return_value=False):
                return job_key(value,self.snapshot,'model')
        self.assertEqual(job_key(item,self.snapshot,'model'),previous_key(item))
        scoped={**item,'target':dict(item['target'],text='Cho xin bảng giá vé ạ'),
            'image_evidence':[{'role':'ROOT_POST','quality_status':'NEEDS_REVIEW','text':'ảnh cha'}]}
        self.assertNotEqual(job_key(scoped,self.snapshot,'model'),previous_key(scoped))

    def test_single_item_flush_and_oversized_never_truncates_raw(self):
        _,child=self.thread()
        item=build_item(self.raw,child,self.source,self.snapshot)
        batches=build_batches([item],self.snapshot,max_input_units=200000)
        self.assertEqual(len(batches['batches']),1)
        result=build_batches([item],self.snapshot,max_input_units=10)
        self.assertFalse(result['batches'])
        self.assertEqual(result['oversized'][0]['item_id'],child)
        self.assertEqual(self.raw.get(child)['raw_text'],item['target']['text'])

    def test_batch_output_reserve_splits_and_source_is_checked(self):
        _,child=self.thread()
        item=build_item(self.raw,child,self.source,self.snapshot)
        other={**item,'item_id':'another','target':{'text':'test','evidence_id':'another-target'}}
        result=build_batches([item,other],self.snapshot,max_input_units=200000,max_output_units=1800)
        self.assertEqual([len(r['items']) for r in result['batches']],[1,1])
        with self.assertRaises(ValueError): build_item(self.raw,child,'unrelated',self.snapshot)
