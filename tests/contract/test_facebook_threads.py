from pathlib import Path
import tempfile
import unittest
from src.acquisition.facebook_threads import normalize_comment, save_comment_batch
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore


URL='https://www.facebook.com/groups/123/posts/111'


class FacebookThreadTests(unittest.TestCase):
    def test_flat_rescan_does_not_demote_saved_reply_or_lose_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','r')['node_id']
                save_comment_batch(store,[self.row('222'),self.row('333',parent_native_id='222')],root,URL,'group','r1','task',{})
                save_comment_batch(store,[self.row('333'),self.row('444')],root,URL,'group','r2','task',{})
                rows={n['platform_item_id']:n for n in store.list_nodes()}
                self.assertEqual(rows['333']['node_type'],'REPLY')
                self.assertEqual(rows['333']['parent_node_id'],rows['222']['node_id'])
                self.assertIn('444',rows)
            finally:store.close()

    def test_explicit_parent_conflict_keeps_original_thread_and_rolls_back(self):
        from src.acquisition.models import AdapterError
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','r')['node_id']
                save_comment_batch(store,[self.row('222'),self.row('333',parent_native_id='222')],root,URL,'group','r1','task',{})
                with self.assertRaises(AdapterError) as caught:
                    save_comment_batch(store,[self.row('444'),self.row('333',parent_native_id='444')],root,URL,'group','r2','task',{})
                self.assertEqual(caught.exception.code,'COMMENT_PARENT_CONFLICT')
                self.assertNotIn('444',{n['platform_item_id'] for n in store.list_nodes()})
            finally:store.close()

    def row(self,identifier,**kwargs):
        return normalize_comment(dict(native_id=identifier,text='comment',parser='fixture',**kwargs),URL,'111')

    def test_comment_link_time_own_identity_and_tracking(self):
        row=normalize_comment({'url':URL+'?comment_id=222&reply_comment_id=333&tracking=x',
            'datetime':'2026-10-08T07:00:00+07:00','text':'reply'},URL,'111')
        self.assertEqual((row['native_id'],row['parent_native_id'],row['node_type']),('333','222','REPLY'))
        self.assertEqual(row['published_at'],'2026-10-08T00:00:00Z')
        self.assertEqual(row['publication_precision'],'INSTANT')

    def test_wrong_post_and_unknown_time_are_not_accepted_as_window_evidence(self):
        self.assertIsNone(normalize_comment({'url':'https://www.facebook.com/groups/123/posts/999?comment_id=222'},URL,'111'))
        row=self.row('222',time_raw='1 giờ trước')
        self.assertIsNone(row['published_at'])
        self.assertEqual(row['publication_precision'],'UNKNOWN')

    def test_reply_before_parent_is_saved_in_order_and_rerun_dedups(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','run')['node_id']
                rows=[self.row('333',parent_native_id='222'),self.row('222')]
                for run in ('run1','run2'): save_comment_batch(store,rows,root,URL,'group',run,'task',{'cursor':'rescan'})
                nodes=store.list_nodes()
                self.assertEqual(len(nodes),3)
                by_id={n['platform_item_id']:n for n in nodes}
                self.assertEqual(by_id['333']['parent_node_id'],by_id['222']['node_id'])
                self.assertEqual(by_id['333']['node_type'],'REPLY')
            finally: store.close()

    def test_missing_parent_reference_is_later_filled_using_native_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','run')['node_id']
                save_comment_batch(store,[self.row('333',parent_native_id='222')],root,URL,'group','r1','task',{})
                save_comment_batch(store,[self.row('222')],root,URL,'group','r2','task',{})
                nodes=store.list_nodes()
                self.assertEqual(len(nodes),3)
                self.assertEqual(next(n for n in nodes if n['platform_item_id']=='222')['raw_text'],'comment')
            finally: store.close()

    def test_parent_cycle_rolls_back_batch_without_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','run')['node_id']
                from src.acquisition.models import AdapterError
                with self.assertRaises(AdapterError): save_comment_batch(store,[self.row('222',parent_native_id='333'),self.row('333',parent_native_id='222')],root,URL,'group','run','task',{})
                self.assertEqual(len(store.list_nodes()),1)
                self.assertEqual(store.db.execute('SELECT count(*) FROM conversation_checkpoints').fetchone()[0],0)
            finally: store.close()
