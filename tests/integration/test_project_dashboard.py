"""Project selections on the current workspace, with isolated raw data."""
import os,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from engine.dashboard import SearchService,make_handler
from src.storage.conversations import ConversationStore
from src.domain.conversation import ContentNode
from src.browser.profiles import PROJECT_ROOT,prepare_browser_path
@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in Chromium')
class ProjectDashboardTests(unittest.TestCase):
    def test_select_project_search_library_crawl_and_schedule(self):
        from playwright.sync_api import sync_playwright,expect
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';raw=ConversationStore(db)
            for i in (12345,12346):raw.ingest(ContentNode('POST',platform_item_id=str(i),canonical_url=f'https://www.facebook.com/groups/1280258833374137/posts/{i}',raw_text='Đợi hoàn tiền ba ngày'),'fb_group_1280258833374137','fixture')
            raw.close();service=SearchService(db,PROJECT_ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,PROJECT_ROOT/'config',service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True);page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}')
                    expect(page.locator('#filter-project option[value="vinwonders_vu_yen"]')).to_have_count(1)
                    page.locator('#tab-LIBRARY').click();expect(page.locator('#applied-scope')).to_contain_text('2 nội dung')
                    page.locator('#filter-project').select_option('vinwonders_vu_yen');page.locator('#filter-form button[type=submit]').click()
                    expect(page.locator('#saved-rows tr')).to_have_count(2);expect(page.locator('#saved-rows')).to_contain_text('theo group, chưa xác nhận')
                    page.locator('#tab-CRAWL').click();page.locator('#crawl-project').select_option('vinwonders_vu_yen')
                    page.locator('[data-section=sources]').click();expect(page.locator('#source-list .run-card')).to_have_count(14)
                    expect(page.locator('#schedule-project option[value="vinwonders_vu_yen"]')).to_have_count(1)
                    page.locator('#tab-SEARCH').click();expect(page.locator('#search-panel')).to_contain_text('SerpApi');browser.close()
            finally:server.shutdown();server.server_close();thread.join();service.close()
