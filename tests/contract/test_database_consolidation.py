import tempfile
import unittest
from pathlib import Path
from engine.database_consolidation import consolidate
from engine.registry import Registry
from src.browser.profiles import PROJECT_ROOT
from src.storage.acquisition import AcquisitionStore
from src.storage.conversations import ConversationStore
from src.acquisition.models import Candidate
from src.domain.conversation import ContentNode


class ConsolidationTests(unittest.TestCase):
    def test_union_preserves_raw_revision_reviews_and_legacy_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'raw.db'; target=base/'acquisition.db'
            url='https://www.facebook.com/groups/139108668844789/posts/111'
            sid='fb_group_139108668844789'
            raw=ConversationStore(source)
            node=raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url=url,raw_text='new content'),sid,'new')['node_id']
            raw.review(node,'RELEVANT','preserve note'); revision=raw.get(node)['revision_id'];raw.close()
            old=AcquisitionStore(target)
            old.save_candidate(Candidate('facebook',url,url,sid,'old','BROWSER',platform_item_id='111',raw_text='old content'))
            old.close()
            report=consolidate(source,target,base/'backups',Registry(PROJECT_ROOT/'config'))
            self.assertEqual(report['integrity'],'ok')
            raw=ConversationStore(target)
            self.assertEqual(raw.get(node)['raw_text'],'new content')
            self.assertEqual(raw.get(node)['revision_id'],revision)
            self.assertEqual(raw.db.execute('SELECT count(*) FROM records').fetchone()[0],1)
            self.assertIn('preserve note',raw.db.execute('SELECT payload FROM node_reviews').fetchone()[0])
            self.assertEqual(len(raw.list_nodes()),1);raw.close()
            self.assertTrue(source.exists())
