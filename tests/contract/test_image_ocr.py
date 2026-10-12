from copy import deepcopy
from io import BytesIO
from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch
from engine.classification_input import build_item,make_request,prepare_saved,job_key
from engine.classification_jobs import ClassificationJobs
from engine.image_enrichment import enrich_post,OCRBudget,filter_node
from src.analysis.classification_contract import validate_response,ContractError
from src.analysis.taxonomy import load_snapshot
from src.domain.conversation import ContentNode
from src.media.image_ocr import recognize,allowed_image_url,CONFIG_VERSION
from src.storage.conversations import ConversationStore
from src.storage.image_evidence import initialize,save,read

ROOT=Path(__file__).resolve().parents[2]
REF={'media_type':'IMAGE','platform_media_id':'photo1','url':'https://scontent.example.fbcdn.net/p.jpg'}
HEALTH={'status':'AVAILABLE','engine_version':'test','traineddata_version':{'vie':'a','eng':'b'}}


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.raw=ConversationStore(Path(self.tmp.name)/'raw.db')
        self.snapshot=load_snapshot(ROOT/'specs/taxonomy/v1');self.source=self.snapshot['profiles']['vincons']['source_ids'][0]
        self.id=self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url='https://www.facebook.com/groups/123/posts/111',media_refs=[REF]),self.source,'seed')['node_id']
        initialize(self.raw)
    def tearDown(self):self.raw.close();self.tmp.cleanup()
    def evidence(self,text='VinCons chờ 40 phút chưa vào được cổng',quality='ACCEPTABLE'):
        return dict(type='ocr',schema_version='image-ocr-v1',status='AVAILABLE',text=text,quality_status=quality,config_version=CONFIG_VERSION,engine_version='test',traineddata_version=HEALTH['traineddata_version'],image_sha256=hashlib.sha256(b'fixture').hexdigest(),processed_at='2026-10-10T01:00:00Z')

    def test_image_only_classifier_input_and_verbatim_output(self):
        original=self.raw.get(self.id);save(self.raw,self.id,REF,self.evidence())
        item=build_item(self.raw,self.id,self.source,self.snapshot)
        self.assertIsNone(item['target']['text']);self.assertEqual(self.raw.get(self.id)['revision_id'],original['revision_id'])
        self.assertEqual(item['project_candidates'][0]['basis'],'CONTENT_EXPLICIT')
        self.assertIn(self.id,[i['item_id'] for i in prepare_saved(self.raw,self.snapshot)['items']])
        request=make_request([item],self.snapshot);image=item['image_evidence'][0]
        result=dict(item_id=self.id,revision_id=item['revision_id'],relevance='KEEP',project_matches=item['project_candidates'],issues=[dict(issue_id='ENTRY_QUEUE',summary='Chờ vào cổng lâu',location=None,evidence=[dict(evidence_id=image['evidence_id'],origin_item_id=self.id,quote=image['text'])])],content_intents=['COMPLAINT'],confidence=None,needs_review=False,review_reason=None,drop_reason=None)
        response=dict(schema_version='classification-result-v2',batch_id=request['batch_id'],results=[result])
        self.assertTrue(validate_response(response,request,self.snapshot)['complete'])
        response['results'][0]['issues'][0]['evidence'][0]['quote']='Invented text'
        with self.assertRaises(ContractError):validate_response(response,request,self.snapshot)

    def test_ocr_revision_invalidates_target_and_parent_jobs_without_changing_caption(self):
        child=self.raw.ingest(ContentNode('COMMENT',platform_item_id='222',root_post_id=self.id,parent_node_id=self.id,raw_text='Chờ ở cổng'),self.source,'seed')['node_id']
        before=build_item(self.raw,child,self.source,self.snapshot)
        save(self.raw,self.id,REF,self.evidence());after=build_item(self.raw,child,self.source,self.snapshot)
        queue=ClassificationJobs(self.raw)
        self.assertFalse(queue._current(before));self.assertTrue(queue._current(after))
        self.assertNotEqual(job_key(before,self.snapshot,'model'),job_key(after,self.snapshot,'model'))
        first=read(self.raw,self.id)[0]['evidence_id'];save(self.raw,self.id,REF,self.evidence())
        self.assertEqual(read(self.raw,self.id)[0]['evidence_id'],first)
        save(self.raw,self.id,REF,self.evidence('VinCons chờ 50 phút'))
        self.assertFalse(queue._current(after))

    def test_commercial_ocr_requires_review_and_raw_is_retained(self):
        save(self.raw,self.id,REF,self.evidence('Tuyển dụng công nhân VinCons, liên hệ 0901234567'))
        self.assertEqual(filter_node(self.raw,self.raw.get(self.id))['prefilter_decision'],'REVIEW')
        self.assertEqual(len(self.raw.list_nodes()),1)

    def test_uncertain_parent_ocr_does_not_gate_independent_commercial_target(self):
        save(self.raw,self.id,REF,self.evidence('VinCons',quality='NEEDS_REVIEW'))
        child=self.raw.ingest(ContentNode('COMMENT',platform_item_id='444',root_post_id=self.id,
            parent_node_id=self.id,raw_text='Giới thiệu dịch vụ mới tại VinCons'),self.source,'seed')['node_id']
        item=build_item(self.raw,child,self.source,self.snapshot)
        request=make_request([item],self.snapshot)
        result=dict(item_id=child,revision_id=item['revision_id'],relevance='DROP',project_matches=[],
            issues=[],content_intents=['ADVERTISING'],confidence=None,needs_review=False,
            review_reason=None,drop_reason='Quảng cáo dịch vụ, không có phản ánh.')
        response=dict(schema_version='classification-result-v2',batch_id=request['batch_id'],results=[result])
        self.assertTrue(validate_response(response,request,self.snapshot)['complete'])
        # The exception cannot be used to cite uncertain context as project proof.
        result['project_matches']=[dict(project_id='vincons',basis='PARENT_CONTEXT',
            evidence_ids=[item['image_evidence'][0]['evidence_id']])]
        with self.assertRaises(ContractError):validate_response(response,request,self.snapshot)
        result['project_matches']=[]
        item['target']['text']='Tôi cũng bị vậy'
        with self.assertRaises(ContractError):validate_response(response,request,self.snapshot)

    def test_uncertain_target_ocr_still_forbids_commercial_drop(self):
        save(self.raw,self.id,REF,self.evidence('Giới thiệu dịch vụ mới VinCons',quality='UNKNOWN'))
        item=build_item(self.raw,self.id,self.source,self.snapshot)
        request=make_request([item],self.snapshot)
        result=dict(item_id=self.id,revision_id=item['revision_id'],relevance='DROP',project_matches=[],
            issues=[],content_intents=['ADVERTISING'],confidence=None,needs_review=False,
            review_reason=None,drop_reason='Quảng cáo dịch vụ.')
        response=dict(schema_version='classification-result-v2',batch_id=request['batch_id'],results=[result])
        with self.assertRaises(ContractError):validate_response(response,request,self.snapshot)

    def test_price_question_is_not_an_independent_commercial_ocr_exception(self):
        from src.analysis.ocr_policy import independent_commercial_target,uncertain_ocr_requires_review
        from src.analysis.gemini_gateway import validation_constraints
        save(self.raw,self.id,REF,self.evidence('VinCons',quality='NEEDS_REVIEW'))
        child=self.raw.ingest(ContentNode('COMMENT',platform_item_id='445',root_post_id=self.id,
            parent_node_id=self.id,raw_text='Cho xin bảng giá vé ạ'),self.source,'seed')['node_id']
        item=build_item(self.raw,child,self.source,self.snapshot)
        self.assertFalse(independent_commercial_target(item))
        self.assertTrue(uncertain_ocr_requires_review(item))
        self.assertIn(child,validation_constraints(make_request([item],self.snapshot))['uncertain_ocr_item_ids'])

    def test_saved_target_ocr_complaint_is_not_hidden_by_sales_caption(self):
        self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url='https://www.facebook.com/groups/123/posts/111',
            media_refs=[REF],raw_text='Bán vé VinCons, inbox đặt vé'),self.source,'new')
        save(self.raw,self.id,REF,self.evidence('Tôi chờ 40 phút không vào được cổng'))
        decision=filter_node(self.raw,self.raw.get(self.id))
        self.assertEqual(decision['prefilter_decision'],'REVIEW')
        self.assertIn('SALES',decision['content_intents'])
        save(self.raw,self.id,REF,self.evidence('Giới thiệu dịch vụ mới',quality='UNKNOWN'))
        self.assertEqual(filter_node(self.raw,self.raw.get(self.id))['prefilter_decision'],'REVIEW')

    def test_hash_cache_budget_and_caption_drop_skip_download(self):
        from src.acquisition.models import Deadline
        with patch('engine.image_enrichment.probe',return_value=HEALTH):
            fetch=unittest.mock.Mock(return_value=b'fixture');recognizer=unittest.mock.Mock(return_value=self.evidence())
            self.assertEqual(enrich_post(self.raw,self.id,None,Deadline(20),fetcher=fetch,recognizer=recognizer)['processed_images'],1)
            enrich_post(self.raw,self.id,None,Deadline(20),fetcher=fetch,recognizer=recognizer)
            self.assertEqual(recognizer.call_count,1)
            enrich_post(self.raw,self.id,None,Deadline(20),OCRBudget(0),fetcher=fetch,recognizer=recognizer)
            self.assertEqual(fetch.call_count,2)
            self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url='https://www.facebook.com/groups/123/posts/111',media_refs=[REF],raw_text='Tuyển dụng công nhân VinCons, liên hệ 0901234567'),self.source,'new')
            self.assertEqual(enrich_post(self.raw,self.id,None,Deadline(20),fetcher=fetch)['status'],'SKIPPED_CAPTION_DROP')
            self.assertEqual(fetch.call_count,2)

    def test_media_host_and_failed_refresh_keep_success(self):
        from src.acquisition.models import Deadline
        for url in ('https://localhost/img','http://scontent.fbcdn.net/img','https://x.fbcdn.net.evil/img','https://user:pass@x.fbcdn.net/img'):
            self.assertFalse(allowed_image_url(url))
        self.assertTrue(allowed_image_url(REF['url']))
        save(self.raw,self.id,REF,self.evidence());before=read(self.raw,self.id)
        with patch('engine.image_enrichment.probe',return_value=HEALTH):
            enrich_post(self.raw,self.id,None,Deadline(20),fetcher=unittest.mock.Mock(side_effect=ValueError('IMAGE_URL_UNAVAILABLE')))
        self.assertEqual(read(self.raw,self.id),before)

    def test_selected_job_claim_does_not_process_other_nodes(self):
        save(self.raw,self.id,REF,self.evidence())
        other=self.raw.ingest(ContentNode('POST',platform_item_id='333',canonical_url='https://www.facebook.com/groups/123/posts/333',raw_text='VinCons chờ ở cổng'),self.source,'seed')['node_id']
        queue=ClassificationJobs(self.raw)
        queue.enqueue([build_item(self.raw,other,self.source,self.snapshot),build_item(self.raw,self.id,self.source,self.snapshot)],self.snapshot,'model')
        jobs=queue.claim(self.snapshot,'model','2026-10-10T01:00:00Z',node_ids=[self.id])
        self.assertEqual([j['item']['item_id'] for j in jobs],[self.id])
        self.assertEqual(self.raw.db.execute('SELECT status FROM classification_jobs WHERE node_id=?',(other,)).fetchone()[0],'PENDING')

    @unittest.skipUnless(os.environ.get('OCR_ENGINE_TESTS')=='1','Opt-in actual local OCR engine')
    def test_real_vietnamese_engine_and_invalid_image(self):
        from PIL import Image,ImageDraw,ImageFont
        image=Image.new('RGB',(1400,300),'white');draw=ImageDraw.Draw(image)
        text='VinCons\nChờ 40 phút chưa vào được cổng'
        draw.multiline_text((35,35),text,fill='black',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48),spacing=20)
        data=BytesIO();image.save(data,format='PNG');result=recognize(data.getvalue())
        self.assertEqual(result['status'],'AVAILABLE');self.assertIn('40',result['text']);self.assertIn('VinCons',result['text']);self.assertTrue(result['words'])
        self.assertEqual(recognize(b'invalid')['error_code'],'IMAGE_DECODE_FAILED')


if __name__=='__main__':unittest.main()
