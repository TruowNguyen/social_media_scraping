"""Real Chromium, isolated raw SQLite and fake provider. No live acquisition."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from engine.dashboard import make_handler,SearchService
from src.browser.profiles import prepare_browser_path
from tests.contract.test_dashboard_workspace import fixture

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in Chromium')
class WorkspaceBrowserTests(unittest.TestCase):
    def test_facebook_progress_survives_slow_health_and_reconnect(self):
        from playwright.sync_api import sync_playwright,expect
        from engine.dashboard_workspace import Workspace
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';fixture(db,3)
            service=SearchService(db,ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,ROOT/'config',service=service))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            original=Workspace.health
            try:
                with patch('engine.classification_service.GeminiGateway') as gateway,patch('engine.dashboard.AcquisitionEngine') as acquisition:
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True)
                        for width in (1440,390):
                            job=dict(job_id='facebook-running',mode='CRAWL',status='RUNNING',rows=[],warnings=[],source_count=7,
                                window_start='2026-10-09T00:00:00Z',window_end='2026-10-10T00:00:00Z',
                                current_phase='COMMENTS',current_source_name='Hội công nhân VinCons',updated_at='2026-10-09T01:00:00Z',
                                progress=dict(total_sources=7,completed_sources=1,observed_nodes=3,posts=1,comments=2,replies=0,confirmed_window_nodes=2,unknown_time_nodes=1))
                            service.jobs={job['job_id']:job};service.running=True
                            entered=threading.Event();release=threading.Event()
                            def delayed(workspace,**options):entered.set();release.wait(12);return original(workspace,**options)
                            page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            with patch.object(Workspace,'health',delayed):
                                try:
                                    page.goto(f'http://127.0.0.1:{server.server_port}/?tab=CRAWL')
                                    self.assertTrue(entered.wait(2))
                                    expect(page.locator('#job-state')).to_contain_text('Đang đọc bài và bình luận',timeout=3000)
                                    expect(page.locator('#job-rows')).to_contain_text('2 bình luận')
                                    expect(page.locator('#crawl-form button[type=submit]')).to_be_disabled()
                                    job['progress']={**job['progress'],'comments':4,'observed_nodes':5}
                                    # The independent timer updates while health is still waiting.
                                    expect(page.locator('#job-rows')).to_contain_text('4 bình luận',timeout=7000)
                                finally:release.set()
                            expect(page.locator('#health-strip')).to_contain_text('Lịch Facebook:')
                            page.route('**/api/jobs/facebook-running',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"busy"}'))
                            page.locator('#job-refresh').click()
                            expect(page.locator('#job-state')).to_contain_text('Sẽ tự kết nối lại')
                            self.assertEqual(page.evaluate('state.job'),'facebook-running')
                            expect(page.locator('#job-rows')).to_contain_text('4 bình luận')
                            page.unroute('**/api/jobs/facebook-running');page.locator('#job-refresh').click()
                            expect(page.locator('#job-state')).to_contain_text('Đang đọc bài và bình luận')
                            page.route('**/api/health*',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"busy"}'))
                            page.evaluate('refreshHealth()');expect(page.locator('#health-strip')).to_contain_text('Lịch Facebook:')
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                            (ROOT/'reports').mkdir(exist_ok=True)
                            page.screenshot(path=str(ROOT/'reports'/f'facebook-direct-progress-{width}.png'),full_page=True)
                            job['status']='PARTIAL';page.locator('#job-refresh').click()
                            expect(page.locator('#job-state')).to_contain_text('Lượt đã kết thúc')
                            expect(page.locator('#crawl-form button[type=submit]')).to_be_enabled()
                            self.assertEqual(errors,[]);page.close()
                        gateway.assert_not_called();acquisition.assert_not_called();browser.close()
            finally:server.shutdown();server.server_close();service.running=False;service.close();thread.join()

    def test_missing_job_stops_polling_reconnects_and_preserves_saved_view(self):
        from playwright.sync_api import sync_playwright,expect
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';fixture(db,3)
            service=SearchService(db,ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,ROOT/'config',service=service))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch('engine.classification_service.GeminiGateway') as gateway,patch('engine.dashboard.AcquisitionEngine') as acquisition:
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True)
                        for width in (1440,390):
                            with self.subTest(width=width):
                                page=browser.new_page(viewport={'width':width,'height':1000})
                                requests=[];errors=[]
                                page.on('request',lambda req:requests.append(req.url))
                                page.on('pageerror',lambda error:errors.append(str(error)))
                                # A stale health response must not continually re-adopt a missing job.
                                with patch.object(service,'active',return_value=dict(job_id='expired',status='RUNNING')):
                                    page.goto(f'http://127.0.0.1:{server.server_port}/?tab=LIBRARY')
                                    expect(page.locator('#health-strip')).to_contain_text('Lịch Facebook:')
                                    expect(page.locator('#applied-scope')).to_contain_text('3 nội dung')
                                    before=sum('/api/views?' in url for url in requests)
                                    page.evaluate('checkNewData()')
                                    self.assertTrue(any(url.endswith('/api/views/version') for url in requests))
                                    self.assertEqual(sum('/api/views?' in url for url in requests),before)
                                    page.evaluate('pollJob()')
                                    self.assertIsNone(page.evaluate('state.job'))
                                    for _ in range(2):page.evaluate('refreshHealth().then(pollJob)')
                                    self.assertEqual(sum(url.endswith('/api/jobs/expired') for url in requests),1)
                                    expect(page.locator('#notice')).not_to_contain_text('Không tìm thấy')
                                # Reconnect to an actual active job, without triggering new acquisition.
                                active=dict(job_id='current-job',mode='SEARCH',status='RUNNING',rows=[],
                                    window_start='2026-10-01T00:00:00Z',window_end='2026-10-02T00:00:00Z')
                                service.jobs={'current-job':active};service.running=True
                                page.evaluate("state.job='old';pollJob()")
                                self.assertEqual(page.evaluate('state.job'),'current-job')
                                page.evaluate('pollJob()')
                                expect(page.locator('#search-result')).to_contain_text('Đang xử lý')
                                # Temporary failures retain the subscription for retry.
                                page.route('**/api/jobs/current-job',lambda route:route.fulfill(status=500,content_type='application/json',body='{"error":"Temporary read error"}'))
                                page.evaluate('pollJob()');self.assertEqual(page.evaluate('state.job'),'current-job')
                                page.unroute('**/api/jobs/current-job')
                                page.reload();expect(page.locator('#health-strip')).to_contain_text('Lịch Facebook:')
                                page.locator('#tab-SEARCH').click();page.locator('#keywords').fill('VinCons')
                                page.locator('#search-form button[type=submit]').click()
                                expect(page.locator('#search-result')).to_contain_text('Đang xử lý')
                                self.assertEqual(page.evaluate('state.job'),'current-job')
                                expect(page.locator('#keywords')).to_have_value('VinCons')
                                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                                self.assertEqual(errors,[])
                                service.jobs={};service.running=False;page.close()
                        gateway.assert_not_called();acquisition.assert_not_called();browser.close()
            finally:server.shutdown();server.server_close();service.close();thread.join()

    def test_platform_sources_multi_project_schedule_and_saved_state(self):
        import shutil
        from playwright.sync_api import sync_playwright,expect
        from engine.threads_registry import ThreadsRegistry
        from src.acquisition.threads import node_from_item
        from src.storage.conversations import ConversationStore
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';fixture(db,3)
            config=Path(folder)/'config';shutil.copytree(ROOT/'config',config)
            registry=ThreadsRegistry(config);data=registry.data
            data.update(enabled=True,verification={'search_recent':'SUPPORTED','public_replies':'SUPPORTED'})
            registry.write(data,data['version'])
            raw=ConversationStore(db)
            node=node_from_item({'url':'https://www.threads.com/@tester/post/ui_test','shortcode':'ui_test','username':'tester','text':'Chờ ở cổng VinWonders','timestamp':'2026-10-01T01:00:00Z'})
            raw.ingest(node,'threads_vwy_name','fixture');raw.close()
            service=SearchService(db,config,enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,config,service=service))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch('engine.classification_service.GeminiGateway') as gateway,patch('engine.dashboard.AcquisitionEngine') as acquisition:
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
                        page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/?tab=LIBRARY&platform=threads')
                        expect(page.locator('#health-strip')).to_contain_text('Lịch Threads:')
                        expect(page.locator('#applied-scope')).to_contain_text('1 nội dung')
                        expect(page.locator('#filter-source')).to_contain_text('Threads · VinCons')
                        page.locator('#saved-rows [data-open]').first.click()
                        expect(page.locator('.detail-source')).to_contain_text('Threads')
                        expect(page.locator('.detail-source')).to_contain_text('VinWonders Vũ Yên')
                        page.keyboard.press('Escape');page.locator('#tab-CRAWL').click()
                        page.locator('#crawl-platform').select_option('THREADS')
                        expect(page.locator('#threads-start-run')).to_be_enabled()
                        page.locator('#threads-project').select_option('vincons')
                        expect(page.locator('#threads-queries')).to_contain_text('VinCons')
                        page.locator('[data-section=schedule]').click()
                        page.locator('#threads-schedule-projects input[value=vincons]').check()
                        page.locator('#threads-schedule-form button[type=submit]').click()
                        expect(page.locator('#notice')).to_contain_text('Đã lưu cấu hình lịch')
                        saved=service.threads.schedule_status()
                        self.assertEqual(set(saved['project_ids']),{'vincons','vinwonders_vu_yen'});self.assertFalse(saved['enabled'])
                        page.reload();expect(page.locator('#crawl-platform')).to_have_value('THREADS')
                        expect(page.locator('#threads-project')).to_have_value('vincons')
                        page.locator('[data-section=sources]').click()
                        expect(page.locator('#threads-project-coverage')).to_contain_text('1 nội dung đã lưu')
                        expect(page.locator('#threads-project-coverage')).to_contain_text('Chưa chạy')
                        # Empty project selection fails locally and preserves the stored schedule.
                        page.locator('[data-section=schedule]').click()
                        for checkbox in page.locator('#threads-schedule-projects input').all():checkbox.uncheck()
                        page.locator('#threads-schedule-form button[type=submit]').click()
                        expect(page.locator('#notice')).to_contain_text('Chọn ít nhất một dự án')
                        self.assertEqual(service.threads.schedule_status()['version'],saved['version'])
                        page.reload();page.set_viewport_size({'width':390,'height':844})
                        for section in ('manual','schedule','sources','history'):
                            page.locator(f'[data-section={section}]').click()
                            expect(page.locator('#threads-'+section)).to_be_visible()
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                        # Navigation while initial health is unresolved must not
                        # let the old restore overwrite the newly selected filter.
                        from engine.dashboard_workspace import Workspace
                        entered=threading.Event();release=threading.Event();original=Workspace.health
                        def delayed_health(workspace,**options):
                            entered.set();release.wait(10);return original(workspace,**options)
                        page.set_viewport_size({'width':1440,'height':1000})
                        with patch.object(Workspace,'health',delayed_health):
                            try:
                                page.goto(f'http://127.0.0.1:{server.server_port}/?tab=CRAWL')
                                self.assertTrue(entered.wait(2))
                                page.locator('#tab-LIBRARY').click()
                                expect(page.locator('#filter-platform')).to_be_enabled(timeout=2000)
                                page.locator('#filter-platform').select_option('threads')
                                release.set()
                                page.locator('#filter-form button[type=submit]').click()
                                expect(page.locator('#applied-scope')).to_contain_text('1 nội dung',timeout=12000)
                                self.assertIn('platform=threads',page.url)
                            finally:release.set()
                        self.assertEqual(errors,[]);gateway.assert_not_called();acquisition.assert_not_called()
                        browser.close()
            finally:server.shutdown();server.server_close();service.close();thread.join()

    def test_clear_filters_refreshes_without_apply_and_keeps_drafts(self):
        from playwright.sync_api import sync_playwright, expect
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'db.sqlite3'
            fixture(db, 35)
            service = SearchService(db, ROOT / 'config', enable_scheduler=False)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db, ROOT / 'config', service=service))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch('engine.classification_service.GeminiGateway') as gateway, patch('engine.dashboard.AcquisitionEngine') as acquisition:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        errors = []
                        for tab, width in [('CLASSIFY', 1440), ('LIBRARY', 390)]:
                            with self.subTest(tab=tab):
                                page = browser.new_page(viewport={'width': width, 'height': 1000})
                                page.on('pageerror', lambda e: errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{server.server_port}/?tab={tab}&keyword=no_matching_text&page=2')
                                expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
                                expect(page.locator('#clear-filters')).to_be_enabled()
                                if width < 760:
                                    page.locator('#filter-toggle').click()
                                page.evaluate("localStorage.setItem('social-listening-review-drafts-v1', JSON.stringify({test:{note:'keep draft',status:'RELEVANT',updated:Date.now()}}))")
                                previous = page.evaluate('state.view.view_id')
                                page.locator('#clear-filters').click()
                                expect(page.locator('#applied-scope')).to_contain_text('35 nội dung', timeout=6000)
                                expect(page.locator('#notice')).to_contain_text('Đã xóa bộ lọc')
                                expect(page.locator('#filter-keyword')).to_have_value('')
                                expect(page.locator('#editing-state')).to_have_text('')
                                self.assertNotIn('keyword=', page.url)
                                self.assertEqual(page.evaluate('state.view.page'), 1)
                                self.assertNotEqual(page.evaluate('state.view.view_id'), previous)
                                self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('social-listening-review-drafts-v1')).test.note"), 'keep draft')
                                # A failed read must preserve the old table and report the failure.
                                page.locator('#filter-keyword').fill('no_matching_text')
                                page.locator('#filter-form button[type=submit]').click()
                                expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
                                page.route('**/api/views?*', lambda route: route.fulfill(status=500, content_type='application/json', body='{"error":"Read failed"}'))
                                page.locator('#clear-filters').click()
                                expect(page.locator('#notice')).to_contain_text('Chưa tải được bảng sau khi xóa bộ lọc')
                                expect(page.locator('#notice')).to_have_class('error')
                                expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
                                expect(page.locator('#saved-panel')).to_have_attribute('aria-busy', 'false')
                                page.unroute('**/api/views?*')
                                page.locator('#clear-filters').click()
                                expect(page.locator('#applied-scope')).to_contain_text('35 nội dung')
                                page.reload()
                                expect(page.locator('#applied-scope')).to_contain_text('35 nội dung')
                                page.close()
                        self.assertEqual(errors, [])
                        gateway.assert_not_called()
                        acquisition.assert_not_called()
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                service.close()
                thread.join()

    def test_drafts_context_conflict_snapshot_export_and_mobile(self):
        from playwright.sync_api import sync_playwright,expect
        prepare_browser_path()
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3';ids=fixture(db,35)
            service=SearchService(db,ROOT/'config',enable_scheduler=False)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,ROOT/'config',service=service))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch('engine.classification_service.GeminiGateway') as gateway,patch('engine.dashboard.AcquisitionEngine') as acquisition:
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(10000)
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        base=f'http://127.0.0.1:{server.server_port}';page.goto(base)
                        expect(page.locator('#tab-CLASSIFY')).to_have_attribute('aria-selected','true')
                        expect(page.locator('#saved-rows tr')).to_have_count(25)
                        expect(page.locator('#applied-scope')).to_contain_text('35 nội dung')
                        page.locator('#next-page').click();expect(page.locator('#saved-rows tr')).to_have_count(10)
                        page.goto(base+'?tab=LIBRARY&node='+ids[1])
                        expect(page.locator('#detail-dialog')).to_be_visible()
                        expect(page.locator('#detail-body')).to_contain_text('Bài gốc về cổng dự án')
                        page.locator('#review-note').fill('Ghi chú nháp cần giữ')
                        page.locator('#detail-close').click();page.locator('#filter-keyword').fill('không có kết quả')
                        page.locator('#filter-form button[type=submit]').click()
                        expect(page.locator('#applied-scope')).to_contain_text('0 nội dung')
                        page.reload();expect(page.locator('#draft-count')).to_contain_text('1 bản nháp')
                        page.locator('#clear-filters').click();page.locator('#filter-form button[type=submit]').click()
                        expect(page.locator('#applied-scope')).to_contain_text('35 nội dung')
                        page.locator('#drafts-open').click();page.locator(f'[data-draft-open="{ids[1]}"]').click();expect(page.locator('#review-note')).to_have_value('Ghi chú nháp cần giữ')
                        page.locator('#thread-details summary').click();page.locator('#thread-more').click();expect(page.locator('#thread-items .context-item')).to_have_count(25)
                        # Poll tick must retain the open detail and focused editor.
                        page.locator('#review-note').focus();page.evaluate('async()=>{for(let i=0;i<3;i++){await refreshHealth();await checkNewData();}}')
                        expect(page.locator('#review-note')).to_be_focused();expect(page.locator('#review-note')).to_have_value('Ghi chú nháp cần giữ')
                        page.route('**/api/reviews',lambda route:route.fulfill(status=500,content_type='application/json',body='{"error":"Lỗi lưu thử nghiệm"}'))
                        page.locator('#review-save').click();expect(page.locator('#review-state')).to_contain_text('Lỗi lưu thử nghiệm')
                        expect(page.locator('#review-note')).to_have_value('Ghi chú nháp cần giữ');page.unroute('**/api/reviews')
                        from src.storage.conversations import ConversationStore
                        raw=ConversationStore(db,initialize=False);raw.review(ids[1],'IRRELEVANT','Đánh giá từ phiên khác');raw.close()
                        page.locator('#review-save').click();expect(page.locator('#review-conflict')).to_be_visible()
                        expect(page.locator('#review-note')).to_have_value('Ghi chú nháp cần giữ')
                        page.locator('#rebase-draft').click();page.locator('#review-save').click()
                        expect(page.locator('#review-state')).to_contain_text('Đã lưu')
                        page.locator('#detail-close').click();page.locator('#refresh-view').click();page.locator('#page-size').select_option('100')
                        expect(page.locator('#saved-rows')).to_contain_text('Ghi chú nháp cần giữ')
                        snapshot=page.evaluate('state.view.view_id')
                        page.locator('#filter-keyword').fill('Thay đổi chưa áp dụng')
                        with page.expect_download() as download:page.locator('#export-view').click()
                        self.assertTrue(download.value.suggested_filename.endswith('.xlsx'))
                        self.assertIn(snapshot,page.evaluate('state.view.view_id'))
                        self.assertNotIn('Ghi chú nháp',page.url)
                        page.locator('#filter-start').fill('2026-10-11');page.locator('#filter-end').fill('2026-10-09')
                        page.locator('#filter-form button[type=submit]').click();expect(page.locator('#filter-end')).to_have_attribute('aria-invalid','true')
                        page.locator('#clear-filters').click();page.locator('#filter-form button[type=submit]').click()
                        expect(page.locator('#export-view')).to_be_enabled();page.evaluate('window.scrollTo(0,0)')
                        (ROOT/'reports').mkdir(exist_ok=True);page.screenshot(path=str(ROOT/'reports/workspace-desktop.png'))
                        page.set_viewport_size({'width':390,'height':844})
                        expect(page.locator('#mobile-list')).to_be_visible();expect(page.locator('#table-wrap')).not_to_be_visible()
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                        page.screenshot(path=str(ROOT/'reports/workspace-mobile.png'))
                        page.locator('#mobile-list [data-open]').first.click();expect(page.locator('#detail-dialog')).to_be_visible()
                        page.screenshot(path=str(ROOT/'reports/workspace-detail-mobile.png'));page.keyboard.press('Escape');expect(page.locator('#detail-dialog')).not_to_be_visible()
                        page.locator('#tab-CRAWL').click();page.locator('[data-section=schedule]').click()
                        expect(page.locator('#schedule-preview')).to_contain_text('05:00 → 05:45 → 06:30 → 07:15 → 08:00 → 08:30')
                        expect(page.locator('#schedule-preview')).to_contain_text('17:00 → 17:45 → 18:30')
                        raw=ConversationStore(db,initialize=False);raw.db.execute("UPDATE dashboard_views SET expires_at='2000-01-01T00:00:00Z' WHERE view_id=?",(snapshot,));raw.db.commit();raw.close()
                        page.goto(base+'?tab=LIBRARY&view_id='+snapshot+'&project_id=vincons&date_basis=observed_any')
                        expect(page.locator('#notice')).to_contain_text('hết hạn');expect(page.locator('#filter-project')).to_have_value('vincons');expect(page.locator('#export-view')).to_be_disabled()
                        # Explicit refresh keeps URL filters; it never silently exports a new unfiltered set.
                        page.locator('#refresh-view').click();expect(page.locator('#export-view')).to_be_enabled();expect(page.locator('#filter-project')).to_have_value('vincons')
                        self.assertEqual(errors,[]);gateway.assert_not_called();acquisition.assert_not_called();browser.close()
            finally:server.shutdown();server.server_close();service.close();thread.join()
