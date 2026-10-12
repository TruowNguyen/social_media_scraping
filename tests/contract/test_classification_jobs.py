from pathlib import Path
import tempfile
import unittest
from engine.classification_input import build_item
from engine.classification_jobs import ClassificationJobs,process_jobs
from src.analysis.taxonomy import load_snapshot
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore

ROOT=Path(__file__).resolve().parents[2]
NOW='2026-10-09T00:00:00Z'


def review_response(request):
    return {'schema_version':'classification-result-v2','batch_id':request['batch_id'],'results':[
        {'item_id':i['item_id'],'revision_id':i['revision_id'],'relevance':'REVIEW','project_matches':i['project_candidates'],
         'issues':[],'confidence':None,'needs_review':True,'review_reason':'Need human review','drop_reason':None} for i in request['items']]}


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.raw=ConversationStore(Path(self.tmp.name)/'raw.db')
        self.snapshot=load_snapshot(ROOT/'specs/taxonomy/v1')
        self.source=self.snapshot['profiles']['vincons']['source_ids'][0]
        self.jobs=ClassificationJobs(self.raw)
        self.items=[]
        for native in ('111','222'):
            node=self.raw.ingest(ContentNode('POST',platform_item_id=native,canonical_url='https://www.facebook.com/groups/123/posts/'+native,raw_text='VinCons kẹt cổng'),self.source,'run')['node_id']
            self.items.append(build_item(self.raw,node,self.source,self.snapshot))

    def tearDown(self): self.raw.close();self.tmp.cleanup()

    def test_idempotent_enqueue_validated_results_persist(self):
        self.assertEqual(self.jobs.enqueue(self.items,self.snapshot,'model'),2)
        self.assertEqual(self.jobs.enqueue(self.items,self.snapshot,'model'),0)
        result=process_jobs(self.jobs,self.snapshot,'model',review_response,NOW,max_input_units=200000)
        self.assertEqual(len(result['outcomes'][0]['accepted']),2)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],2)
        self.assertEqual(process_jobs(self.jobs,self.snapshot,'model',review_response,NOW)['status'],'NO_PENDING_JOBS')

    def test_partial_keeps_valid_result_only_retries_missing(self):
        self.jobs.enqueue(self.items,self.snapshot,'model')
        def partial(request):
            result=review_response(request);result['results']=result['results'][:1];return result
        process_jobs(self.jobs,self.snapshot,'model',partial,NOW,max_input_units=200000)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],1)
        pending=self.jobs.claim(self.snapshot,'model','2026-10-09T00:00:31Z')
        self.assertEqual(len(pending),1)

    def test_invalid_json_and_failure_do_not_delete_raw(self):
        self.jobs.enqueue(self.items,self.snapshot,'model')
        process_jobs(self.jobs,self.snapshot,'model',lambda request:'not json',NOW,max_input_units=200000)
        self.assertEqual(self.raw.db.execute('SELECT count(*) FROM node_analyses').fetchone()[0],0)
        self.assertEqual(len(self.raw.list_nodes()),2)
        def broken(request): raise RuntimeError('sensitive provider text')
        process_jobs(self.jobs,self.snapshot,'model',broken,NOW,max_input_units=200000)
        self.assertNotIn('sensitive',str([dict(r) for r in self.raw.db.execute('SELECT error_code FROM classification_jobs')]))

    def test_edited_target_marks_job_stale(self):
        self.jobs.enqueue(self.items,self.snapshot,'model')
        self.raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url='https://www.facebook.com/groups/123/posts/111',raw_text='Edited VinCons'),self.source,'run2')
        self.assertEqual(len(self.jobs.claim(self.snapshot,'model',NOW)),1)
        self.assertEqual(self.raw.db.execute("SELECT count(*) FROM classification_jobs WHERE status='STALE'").fetchone()[0],1)

    def test_expired_lease_reclaims_after_crash_with_new_token(self):
        self.jobs.enqueue(self.items[:1],self.snapshot,'model')
        first=self.jobs.claim(self.snapshot,'model',NOW,lease_seconds=1)
        second=self.jobs.claim(self.snapshot,'model','2026-10-09T00:00:02Z')
        self.assertEqual(first[0]['job_id'],second[0]['job_id'])
        self.assertNotEqual(first[0]['lease_token'],second[0]['lease_token'])

    def test_attempt_limit_and_oversized_are_explicit(self):
        self.jobs.enqueue(self.items[:1],self.snapshot,'model')
        process_jobs(self.jobs,self.snapshot,'model',review_response,NOW,max_input_units=1)
        self.assertEqual(self.raw.db.execute('SELECT status FROM classification_jobs').fetchone()[0],'OVERSIZED')

    def test_terminal_provider_failure_has_no_scheduled_retry(self):
        self.jobs.enqueue(self.items[:1],self.snapshot,'model')
        jobs=self.jobs.claim(self.snapshot,'model',NOW)
        self.jobs.release(jobs,'PROVIDER_AUTH_DENIED',NOW,retryable=False)
        row=self.raw.db.execute('SELECT status,next_attempt_at FROM classification_jobs').fetchone()
        self.assertEqual(row['status'],'FAILED');self.assertIsNone(row['next_attempt_at'])
