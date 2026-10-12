from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from src.acquisition.models import Candidate, Window, Deadline, DiscoveryRequest, FetchResult, AdapterError
from src.acquisition.prefilter import apply_prefilter
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore
from src.storage.acquisition import AcquisitionStore
from src.storage.conversation_migration import migrate_legacy, rollback_to_copy
from engine.acquisition import AcquisitionEngine


def post(native='111', text='caption', **kwargs):
    return ContentNode('POST', platform_item_id=native, canonical_url='https://www.facebook.com/groups/123/posts/' + native,
        raw_text=text, **kwargs)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'db.sqlite3'
        self.store = ConversationStore(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def ingest(self, node, **kwargs):
        return self.store.ingest(node, 'group', 'run', **kwargs)

    def count(self, table):
        return self.store.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]

    def test_repeated_runs_keep_identity_add_observations_without_revisions(self):
        for i in range(3): self.ingest(post(), observation_id='obs' + str(i))
        self.assertEqual(self.count('content_nodes'), 1)
        self.assertEqual(self.count('content_revisions'), 1)
        self.assertEqual(self.count('conversation_observations'), 3)
        self.assertEqual(self.count('conversation_outbox'), 1)

    def test_same_text_and_author_never_merge_different_native_ids(self):
        for i in ('111', '222'): self.ingest(post(i, '', author_uid='same'))
        self.assertEqual(self.count('content_nodes'), 2)

    def test_comment_reply_links_and_old_parent_new_comment_window(self):
        parent = self.ingest(post(published_at='2026-09-20T01:00:00Z', publication_precision='INSTANT'))['node_id']
        comment = self.ingest(ContentNode('COMMENT', platform_item_id='c1', root_post_id=parent, parent_node_id=parent,
            raw_text='new complaint', published_at='2026-10-08T00:15:00Z', publication_precision='INSTANT',
            display_url='https://www.facebook.com/groups/123/posts/111', url_type='PARENT_FALLBACK'))['node_id']
        reply = self.ingest(ContentNode('REPLY', platform_item_id='r1', root_post_id=parent, parent_node_id=comment,
            canonical_url='https://web.facebook.com/groups/123/posts/111?comment_id=c1&reply_comment_id=r1&tracking=x', raw_text='reply'))['node_id']
        self.assertIn('reply_comment_id=r1', self.store.get(reply)['canonical_url'])
        self.assertNotIn('tracking', self.store.get(reply)['canonical_url'])
        window = Window(datetime(2026,10,7,17,tzinfo=timezone.utc), datetime(2026,10,8,17,tzinfo=timezone.utc))
        self.assertEqual([n['node_id'] for n in self.store.list_nodes(window=window)], [comment])

    def test_missing_time_and_parent_url_cannot_identify_comments(self):
        with self.assertRaises(ValueError): ContentNode('POST', published_at=None, publication_precision='INSTANT')
        with self.assertRaises(ValueError): ContentNode('COMMENT', canonical_url='https://www.facebook.com/groups/123/posts/111', relationship_status='UNRESOLVED')
        for _ in range(2): self.ingest(ContentNode('COMMENT', relationship_status='UNRESOLVED'))
        self.assertEqual(self.count('content_nodes'), 2)

    def test_reference_stub_can_be_filled_without_inventing_or_duplicating_parent(self):
        self.store.ensure_reference('known_root', 'POST', 'group', 'run')
        stub = self.store.get('known_root')
        self.assertIsNone(stub['raw_text'])
        self.assertEqual(stub['extraction_status'], 'REFERENCE_ONLY')
        saved = self.ingest(post(node_id='known_root', text='real caption'))
        self.assertFalse(saved['new'])
        self.assertEqual(self.count('content_nodes'), 1)
        self.assertEqual(self.store.get('known_root')['raw_text'], 'real caption')
        self.store.ensure_reference('known_child','COMMENT','group','run')
        self.ingest(ContentNode('COMMENT', node_id='known_child', platform_item_id='child', root_post_id='known_root', parent_node_id='known_root', raw_text='real comment'))
        row = self.store.db.execute('SELECT root_post_id,parent_node_id FROM content_nodes WHERE node_id=?', ('known_child',)).fetchone()
        self.assertEqual(tuple(row), ('known_root','known_root'))

    def test_conflicting_native_url_and_cross_thread_are_rejected(self):
        parent = self.ingest(post())['node_id']
        with self.assertRaises(ValueError): self.ingest(ContentNode('POST', platform_item_id='other', canonical_url='https://www.facebook.com/groups/123/posts/111'))
        other = self.ingest(post('222'))['node_id']
        with self.assertRaises(ValueError): self.ingest(ContentNode('COMMENT', platform_item_id='c1', root_post_id=parent, parent_node_id=other))
        self.assertEqual(self.count('content_nodes'), 2)

    def test_edit_adds_revision_keeps_review_and_emits_context_invalidation(self):
        parent = self.ingest(post())['node_id']
        child = self.ingest(ContentNode('COMMENT', platform_item_id='c1', root_post_id=parent, parent_node_id=parent, raw_text='child'))['node_id']
        self.store.review(child, 'RELEVANT', 'note')
        self.ingest(post(text='edited caption'))
        self.assertEqual(self.count('content_revisions'), 3)
        self.assertEqual(self.count('conversation_outbox'), 4)
        self.assertEqual(json.loads(self.store.db.execute('SELECT payload FROM node_reviews WHERE node_id=?', (child,)).fetchone()[0])['note'], 'note')

    def test_metadata_only_observation_cannot_erase_full_text_or_known_time(self):
        saved = self.ingest(post(text='full text', extraction_status='COMPLETE', published_at='2026-10-08T00:00:00Z', publication_precision='INSTANT'))
        self.ingest(post(text=None))
        current = self.store.get(saved['node_id'])
        self.assertEqual(current['raw_text'], 'full text')
        self.assertEqual(current['publication_precision'], 'INSTANT')
        self.assertEqual(current['extraction_status'], 'COMPLETE')

    def test_raw_filter_drop_keeps_node_revision_review_and_observations(self):
        saved = self.ingest(post(text='Tuyển công nhân, nhận việc ngay'))
        self.store.review(saved['node_id'], 'IRRELEVANT', 'raw preserved')
        self.store.filter_saved(saved['node_id'], {'prefilter_decision': 'DROP', 'drop_reason': 'RECRUITMENT'}, 'rules1')
        for table in ('content_nodes', 'content_revisions', 'conversation_observations', 'node_reviews'):
            self.assertEqual(self.count(table), 1)
        self.store.close(); self.store = ConversationStore(self.path)
        self.assertIsNotNone(self.store.get(saved['node_id']))

    def test_failed_batch_rolls_back_raw_outbox_and_checkpoint(self):
        entries = [{'node':post(), 'source_id':'group','run_id':'run'},
            {'node': ContentNode('COMMENT', platform_item_id='c1', root_post_id='missing', parent_node_id='missing'), 'source_id':'group','run_id':'run'}]
        with self.assertRaises(ValueError): self.store.ingest_batch(entries, 'task', {'cursor': 'next'})
        for table in ('content_nodes', 'content_revisions', 'conversation_outbox', 'conversation_checkpoints'):
            self.assertEqual(self.count(table), 0)
        self.store.ingest_batch(entries[:1], 'task', {'cursor': 'next'})
        self.assertEqual(self.count('conversation_checkpoints'), 1)

    def test_nested_failed_ingest_rollback_even_when_error_is_caught(self):
        first = self.ingest(post(), observation_id='same')
        with self.store.transaction():
            with self.assertRaises(ValueError): self.ingest(post(text='changed'), observation_id='same')
        self.assertEqual(self.count('content_revisions'), 1)
        self.assertEqual(self.store.get(first['node_id'])['raw_text'], 'caption')

    def test_legacy_purge_cannot_delete_v2_raw(self):
        candidate = Candidate('facebook','https://www.facebook.com/groups/123/posts/111','https://www.facebook.com/groups/123/posts/111','group','run','BROWSER', platform_item_id='111',caption='Tuyển công nhân, nhận việc ngay')
        raw = self.store.ingest_candidate(candidate)
        legacy = AcquisitionStore(self.path)
        try:
            self.assertEqual(apply_prefilter(candidate), 'DROP')
            legacy.reject(candidate)
            self.assertIsNotNone(self.store.get(raw['node_id']))
        finally: legacy.close()

    def test_migration_backup_rerun_reviews_observations_and_restore_copy(self):
        legacy = AcquisitionStore(self.path)
        try:
            candidate = Candidate('facebook','https://www.facebook.com/groups/123/posts/111','https://www.facebook.com/groups/123/posts/111','group','legacy_run','BROWSER',platform_item_id='111',caption='Kẹt cổng quá',prefilter_decision='REVIEW')
            record_id, _ = legacy.save_candidate(candidate)
            legacy.review_content(record_id,'RELEVANT','note preserved')
            old = legacy.db.execute('SELECT payload FROM records').fetchone()[0]
        finally: legacy.close()
        result = migrate_legacy(self.path, Path(self.directory.name)/'backup.sqlite3')
        self.assertEqual(result['facebook_records_mapped'], 1)
        self.assertIsNotNone(self.store.get(record_id))
        self.assertEqual(self.store.db.execute('SELECT payload FROM records').fetchone()[0], old)
        self.assertIn('note preserved', self.store.db.execute('SELECT payload FROM node_reviews').fetchone()[0])
        count = self.count('conversation_observations')
        migrate_legacy(self.path, Path(self.directory.name)/'backup2.sqlite3')
        self.assertEqual(self.count('conversation_observations'), count)
        restored = Path(self.directory.name)/'restored.sqlite3'
        rollback_to_copy(Path(self.directory.name)/'backup.sqlite3', restored)
        db = sqlite3.connect(restored)
        try: self.assertEqual(db.execute('SELECT payload FROM records').fetchone()[0], old)
        finally: db.close()

    def test_raw_first_engine_fetches_ad_and_commits_before_filter(self):
        legacy = AcquisitionStore(self.path)
        engine = AcquisitionEngine(None, legacy, raw_store=self.store)
        candidate = Candidate('facebook','https://www.facebook.com/groups/123/posts/111','https://www.facebook.com/groups/123/posts/111','group','run','BROWSER',platform_item_id='111',caption='Tuyển công nhân, nhận việc ngay')
        class Adapter:
            def fetch_item(inner, value, context):
                self.assertTrue(context.raw_first)
                self.assertEqual(self.count('content_nodes'), 1)
                self.assertEqual(self.count('raw_filter_decisions'), 0)
                self.assertIsNone(value.prefilter_decision)
                return FetchResult(replace(value,raw_text=value.caption,extraction_status='FETCHED'))
        counters = {k:0 for k in ('new','existing','persisted','fetch_success','fetch_failed','prefilter_drop','prefilter_pass','prefilter_review','out_of_window')}
        window = Window(datetime(2026,10,7,17,tzinfo=timezone.utc),datetime(2026,10,8,17,tzinfo=timezone.utc))
        request = DiscoveryRequest({'source_id':'group','source_type':'FACEBOOK_GROUP'},'run',window,Deadline(),'RECENT_SOURCE_ITEMS')
        try:
            engine.process_candidate(candidate,request,{},Adapter(),counters)
            self.assertEqual(counters['prefilter_drop'],1)
            self.assertEqual(self.count('content_nodes'),1)
            self.assertEqual(legacy.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
        finally: legacy.close()

    def test_failed_fetch_keeps_discovery_and_reports_error(self):
        legacy = AcquisitionStore(self.path)
        engine = AcquisitionEngine(None,legacy,raw_store=self.store)
        class Adapter:
            def fetch_item(inner,*args): raise AdapterError('AUTH_REQUIRED','LOGIN_REQUIRED')
        candidate = Candidate('facebook','https://www.facebook.com/groups/123/posts/111','https://www.facebook.com/groups/123/posts/111','group','run','BROWSER',platform_item_id='111',caption='caption')
        counters = {k:0 for k in ('new','existing','persisted','fetch_success','fetch_failed')}
        request = DiscoveryRequest({'source_id':'group','source_type':'FACEBOOK_GROUP'},'run',Window(datetime(2026,10,7,17,tzinfo=timezone.utc),datetime(2026,10,8,17,tzinfo=timezone.utc)),Deadline(),'RECENT_SOURCE_ITEMS')
        try:
            with self.assertRaises(AdapterError): engine.process_raw_candidate(candidate,request,Adapter(),counters)
            self.assertEqual(self.count('content_nodes'),1)
            self.assertEqual(counters['fetch_failed'],1)
        finally: legacy.close()


if __name__ == '__main__': unittest.main()
