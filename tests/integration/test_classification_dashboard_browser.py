"""Raw-first crawl and fake-provider classification through the current UI."""
import os,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from engine.dashboard import make_handler,SearchService
from engine.classification_worker import classification_cycle,RUNTIME_TAXONOMY
from src.analysis.taxonomy import load_snapshot
from src.browser.profiles import prepare_browser_path
from src.storage.conversations import ConversationStore
from src.domain.conversation import ContentNode
from tests.contract.test_classification_worker import Provider
ROOT=Path(__file__).resolve().parents[2]
@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in Chromium')
class ClassificationBrowserTests(unittest.TestCase):
    def test_decision_reason_visible_on_desktop_and_mobile(self):
        from playwright.sync_api import expect
        def seed(db):
            raw=ConversationStore(db);snapshot=load_snapshot(RUNTIME_TAXONOMY)
            raw.ingest(ContentNode('POST',platform_item_id='777',canonical_url='https://www.facebook.com/groups/123/posts/777',
                raw_text='Tuyển công nhân VinCons, không phải trung gian'),snapshot['profiles']['vincons']['source_ids'][0],'fixture')
            classification_cycle(raw,snapshot,Provider());raw.close()
        def check(page):
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            for name,width in [('desktop',1440),('mobile',390)]:
                page.set_viewport_size({'width':width,'height':950})
                panel=page.locator('#saved-rows .decision-reason' if width>760 else '#mobile-list .decision-reason')
                expect(panel.locator('summary')).to_have_text('Lý do · Bộ lọc')
                panel.locator('summary').click()
                expect(panel.locator('p')).to_contain_text('tuyển dụng')
                page.screenshot(path=str(ROOT/'reports'/f'filter-policy-v3-after-{name}.png'),full_page=True)
            self.assertEqual(errors,[])
        self.run_fixture(check,seed)
    def run_fixture(self,check,seed=None):
        from playwright.sync_api import sync_playwright
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3'
            if seed:seed(db)
            service=SearchService(db,ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,ROOT/'config',service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True);page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}');check(page);browser.close()
            finally:server.shutdown();server.server_close();service.close();thread.join()
    def test_crawl_button_raw_v2_retains_comments_and_library_export(self):
        from playwright.sync_api import expect
        from engine.dashboard_conversations import crawl
        from tests.contract.test_dashboard_raw_v2 import ingest
        def executor(registry,raw,task,**kwargs):ingest(raw);return dict(source_id=task['source_id'],status='PARTIAL')
        def bridge(registry,db,sources,window,run_id,**kwargs):return crawl(registry,db,sources[:1],window,run_id,executor)
        def check(page):
            page.locator('#tab-CRAWL').click();page.locator('#crawl-start').fill('2026-10-09');page.locator('#crawl-end').fill('2026-10-09');page.locator('#crawl-form button[type=submit]').click()
            expect(page.locator('#job-scope')).to_contain_text('9/10/2026')
            # Await the real background job outcome, not one poll racing its commit.
            page.wait_for_function("async () => !state.job || (await (await fetch('/api/jobs/'+encodeURIComponent(state.job))).json()).status !== 'RUNNING'")
            page.evaluate('pollJob()');expect(page.locator('#job-rows')).to_contain_text('Bình luận')
            page.locator('#crawl-start').fill('2026-10-08');expect(page.locator('#job-scope')).to_contain_text('9/10/2026')
            page.locator('#tab-LIBRARY').click();expect(page.locator('#saved-rows tr')).to_have_count(3)
            page.locator('#advanced-filters summary').click();page.locator('[name=node_type]').select_option('COMMENT');page.locator('#filter-form button[type=submit]').click();expect(page.locator('#saved-rows tr')).to_have_count(1)
            with page.expect_download() as download:page.locator('#export-view').click()
            self.assertTrue(download.value.suggested_filename.endswith('.xlsx'))
        with patch('engine.dashboard_conversations.crawl',bridge),patch('engine.dashboard.AcquisitionEngine') as old:self.run_fixture(check);old.assert_not_called()
    def test_shared_raw_analysis_table_and_relevance_intent_filters(self):
        from playwright.sync_api import expect
        def seed(db):
            raw=ConversationStore(db);snapshot=load_snapshot(RUNTIME_TAXONOMY)
            raw.ingest(ContentNode('POST',platform_item_id='111',canonical_url='https://www.facebook.com/groups/123/posts/111',raw_text='VinCons chờ 40 phút chưa vào được cổng',published_at='2026-10-09T11:00:00Z',publication_precision='INSTANT'),snapshot['profiles']['vincons']['source_ids'][0],'fixture');classification_cycle(raw,snapshot,Provider());raw.close()
        def check(page):
            expect(page.locator('#saved-rows .result-cell')).to_contain_text('Giữ');expect(page.get_by_role('tab')).to_have_count(4)
            expect(page.locator('#table-wrap th').nth(1)).to_have_text('Nguồn')
            expect(page.locator('#table-wrap th').nth(2)).to_have_text('Nội dung')
            expect(page.locator('#saved-rows tr').first.locator('td')).to_have_count(11)
            expect(page.locator('#saved-rows .source-cell')).to_contain_text('Vincons')
            expect(page.locator('#saved-rows .content-cell')).to_contain_text('chờ 40 phút')
            issue_name=next(i['name'] for i in load_snapshot(RUNTIME_TAXONOMY)['catalog']['issues'] if i['issue_id']=='ENTRY_QUEUE')
            expect(page.locator('#saved-rows .taxonomy-cell')).to_contain_text(issue_name)
            expect(page.locator('#table-wrap th').nth(6)).to_have_text('Ý định nội dung')
            expect(page.locator('#filter-issue')).to_be_visible()
            expect(page.locator('#filter-source')).to_be_visible()
            expect(page.locator('#project-basis')).to_have_value('SOURCE')
            expect(page.locator('label').filter(has=page.locator('select[name="quality"]'))).not_to_be_visible()
            expect(page.locator('#quick-filters')).not_to_be_visible()
            page.locator('#filter-project').select_option('__unknown__');page.locator('#filter-form button[type=submit]').click()
            expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
            expect(page.locator('#filter-project')).to_have_value('__unknown__')
            page.locator('#filter-project').select_option('vincons');page.locator('#filter-form button[type=submit]').click()
            expect(page.locator('#applied-scope')).to_contain_text('1 nội dung')
            page.locator('#advanced-filters summary').click();page.locator('[name=relevance]').select_option('DROP');page.locator('#filter-form button[type=submit]').click();expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
            expect(page.locator('#filter-intent option')).to_have_count(11)
            page.locator('[name=relevance]').select_option('KEEP');page.locator('[name=intent]').select_option('');page.locator('#filter-form button[type=submit]').click();expect(page.locator('#applied-scope')).to_contain_text('1 nội dung')
            page.locator('[name=node_type]').select_option('COMMENT');page.locator('#filter-form button[type=submit]').click();expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
        self.run_fixture(check,seed)
