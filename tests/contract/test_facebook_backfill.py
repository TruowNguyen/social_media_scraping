import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine.facebook_backfill import run
from engine.conversation_schedule import CrawlTasks
from engine.registry import Registry
from src.storage.conversations import ConversationStore
from src.domain.conversation import ContentNode
from src.browser.profiles import PROJECT_ROOT


class BackfillTests(unittest.TestCase):
    def test_pending_sweep_fetches_unattempted_inventory_without_rediscovery(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);raw=ConversationStore(base/'db.sqlite3')
            sid='fb_group_139108668844789';url='https://www.facebook.com/groups/139108668844789/posts/111'
            node=raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=url),sid,'fixture')['node_id']
            CrawlTasks(raw).add_post(sid,node,url);raw.close()
            registry=Registry(PROJECT_ROOT/'config');registry.sources={sid:registry.sources[sid]}
            with patch('engine.facebook_backfill.Registry',return_value=registry),patch('engine.facebook_backfill.inventory_source') as discover,patch('engine.facebook_backfill.trace_thread',return_value={'status':'PARTIAL'}) as fetch:
                report=run(base/'db.sqlite3',PROJECT_ROOT/'config',base/'report.json',pending_only=True)
                discover.assert_not_called();fetch.assert_called_once()
                self.assertEqual(report['source_outcomes'][0]['known_posts_not_scanned'],0)
                self.assertFalse(report['full_window_coverage_verified'])
                run(base/'db.sqlite3',PROJECT_ROOT/'config',base/'report2.json',pending_only=True)
                fetch.assert_called_once()
