import os
import unittest
from datetime import datetime,timedelta,timezone
from playwright.sync_api import sync_playwright
from src.browser.profiles import prepare_browser_path
from src.acquisition.browser_adapters import FB_REFERENCE_SCRIPT,candidate_from_row
from src.acquisition.models import Deadline,DiscoveryRequest,Window


@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Chromium opt-in')
class ListingReferenceTests(unittest.TestCase):
    def test_parent_reference_never_inherits_comment_caption_or_timestamp(self):
        prepare_browser_path()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                page.set_content('<main><div><a href="https://www.facebook.com/groups/123/posts/456/?comment_id=789">Comment date</a><time datetime="2026-10-09T01:00:00Z"></time><p>Comment text</p></div><a href="https://www.facebook.com/groups/123/posts/456/">Same root</a></main>')
                rows=page.locator('a[href]').evaluate_all(FB_REFERENCE_SCRIPT)
                self.assertEqual(len(rows),1)
                now=datetime.now(timezone.utc)
                request=DiscoveryRequest({'platform_group_ref':'123'},'test',Window(now-timedelta(days=14),now),Deadline(),'RECENT_SOURCE_ITEMS')
                request.source.update(source_id='source')
                candidate=candidate_from_row(rows[0],request,'facebook')
                self.assertEqual(candidate.platform_item_id,'456')
                self.assertIsNone(candidate.caption);self.assertIsNone(candidate.published_at)
                self.assertIn('FACEBOOK_POST_PERMALINK_REFERENCE',candidate.evidence_provenance)
            finally:browser.close()
