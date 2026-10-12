"""Current workspace keyboard navigation, filters and responsive list."""
import os,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from engine.dashboard import make_handler,SearchService
from src.browser.profiles import prepare_browser_path
from tests.contract.test_dashboard_workspace import fixture
ROOT=Path(__file__).resolve().parents[2]
@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in Chromium')
class DashboardUXTests(unittest.TestCase):
    def test_pagination_filters_reset_and_responsive_tables(self):
        from playwright.sync_api import sync_playwright,expect
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';fixture(db,35);service=SearchService(db,ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,ROOT/'config',service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True);page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}')
                    expect(page.locator('#saved-rows tr')).to_have_count(25)
                    page.locator('#next-page').click();expect(page.locator('#saved-rows tr')).to_have_count(10)
                    page.locator('#filter-keyword').fill('không khớp');expect(page.locator('#saved-rows tr')).to_have_count(10)
                    page.locator('#filter-form button[type=submit]').click();expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
                    page.locator('#clear-filters').click();page.locator('#filter-form button[type=submit]').click();expect(page.locator('#saved-rows tr')).to_have_count(25)
                    page.locator('#tab-CLASSIFY').focus();page.keyboard.press('ArrowRight');expect(page.locator('#tab-LIBRARY')).to_have_attribute('aria-selected','true')
                    page.set_viewport_size({'width':390,'height':844});expect(page.locator('#mobile-list')).to_be_visible()
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                    page.locator('#mobile-table').click();expect(page.locator('#table-wrap')).to_be_visible();browser.close()
            finally:server.shutdown();server.server_close();service.close();thread.join()
