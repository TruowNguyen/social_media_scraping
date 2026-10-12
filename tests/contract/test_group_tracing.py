from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from engine.group_tracing import trace_thread
from src.acquisition.models import AdapterError,Window
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore


class TracingSchemaTests(unittest.TestCase):
    def test_access_failure_is_stored_without_claiming_deletion_or_available_content(self):
        source={'source_id':'group','source_type':'FACEBOOK_GROUP','platform':'facebook','platform_group_ref':'123','url':'https://www.facebook.com/groups/123'}
        class Registry:
            sources={'group':source}
            def readiness(self,source): return []
        class Adapter:
            def fetch_item(self,candidate,context): raise AdapterError('SOURCE_UNAVAILABLE','CONTENT_UNAVAILABLE')
        @contextmanager
        def factory(*args): yield Adapter()
        with tempfile.TemporaryDirectory() as directory:
            raw=ConversationStore(Path(directory)/'raw.db')
            try:
                now=datetime.now(timezone.utc)
                result=trace_thread(Registry(),raw,'group','https://www.facebook.com/groups/123/posts/111',Window(now-timedelta(days=1),now),factory=factory)
                self.assertEqual(result['error_code'],'CONTENT_UNAVAILABLE')
                node=raw.list_nodes()[0]
                self.assertEqual(node['availability_status'],'UNAVAILABLE')
                self.assertEqual(node['extraction_status'],'FAILED')
                self.assertIsNone(node['raw_text'])
                self.assertIn('CONTENT_UNAVAILABLE',node['missing_fields'])
            finally: raw.close()

    def test_access_failure_keeps_previously_collected_caption(self):
        source={'source_id':'group','source_type':'FACEBOOK_GROUP','platform':'facebook','platform_group_ref':'123','url':'https://www.facebook.com/groups/123'}
        class Registry:
            sources={'group':source}
            def readiness(self,source): return []
        class Adapter:
            def fetch_item(self,candidate,context): raise AdapterError('SOURCE_UNAVAILABLE','CONTENT_UNAVAILABLE')
        @contextmanager
        def factory(*args): yield Adapter()
        with tempfile.TemporaryDirectory() as directory:
            raw=ConversationStore(Path(directory)/'raw.db')
            try:
                url='https://www.facebook.com/groups/123/posts/111'
                raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=url,raw_text='Existing caption',extraction_status='COMPLETE'),'group','previous')
                now=datetime.now(timezone.utc)
                trace_thread(Registry(),raw,'group',url,Window(now-timedelta(days=1),now),factory=factory)
                node=raw.list_nodes()[0]
                self.assertEqual(node['raw_text'],'Existing caption')
                self.assertEqual(node['availability_status'],'UNAVAILABLE')
            finally: raw.close()
