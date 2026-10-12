import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from engine.content_library import library
from src.storage.acquisition import AcquisitionStore
from src.acquisition.models import Candidate
from src.acquisition.prefilter import apply_prefilter


class LibraryTests(unittest.TestCase):
    def test_http_review_requires_local_origin_and_persists(self):
        from engine.dashboard import make_handler, SearchService
        from src.browser.profiles import PROJECT_ROOT
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite3'
            store = AcquisitionStore(path)
            url = 'https://www.facebook.com/groups/123/posts/456'
            rid, _ = store.save_candidate(Candidate('facebook', url, url, 'group', 'run1', 'BROWSER'))
            store.close()
            service = SearchService(path, PROJECT_ROOT / 'config')
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(path, PROJECT_ROOT / 'config', service))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            body = json.dumps(dict(record_id=rid, status='NEEDS_REVIEW', note='Verify source')).encode()
            try:
                bad = Request(base+'/api/library/review', body, {'Content-Type': 'application/json', 'Origin': 'https://example.com'})
                with self.assertRaises(HTTPError) as exc: urlopen(bad)
                self.assertEqual(exc.exception.code, 403)
                good = Request(base+'/api/library/review', body, {'Content-Type': 'application/json', 'Origin': base})
                with urlopen(good) as response: self.assertEqual(json.load(response)['status'], 'NEEDS_REVIEW')
                with urlopen(base+'/api/library?review=NEEDS_REVIEW') as response:
                    self.assertEqual(json.load(response)['rows'][0]['review']['note'], 'Verify source')
                self.assertIsNone(service.active())
            finally:
                server.shutdown(); server.server_close(); thread.join(); service.close()

    def test_retention_review_filters_and_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite3'
            c = Candidate('facebook', 'https://www.facebook.com/groups/123/posts/456',
                          'https://www.facebook.com/groups/123/posts/456', 'group', 'run1',
                          'FACEBOOK_GROUP_BROWSER', platform_item_id='456', caption='Traffic congestion',
                          collected_at='2026-10-08T18:00:00Z')
            store = AcquisitionStore(path)
            rid, _ = store.save_candidate(c)
            store.review_content(rid, 'RELEVANT', 'Investigate')
            store.save_candidate(replace(c, crawl_run_id='run2', candidate_id='obs2'))
            store.close()
            result = library(path)
            self.assertEqual(result['total'], 1)
            self.assertEqual(result['rows'][0]['observation_count'], 2)
            self.assertEqual(result['rows'][0]['review']['note'], 'Investigate')
            self.assertEqual(library(path, {'run_id': 'run1'})['total'], 1)
            self.assertEqual(library(path, {'review': 'UNREVIEWED'})['total'], 0)
            self.assertEqual(library(path, {'start_date': '2026-10-09', 'end_date': '2026-10-09'})['total'], 1)
            self.assertEqual(library(path, {'start_date': '2026-10-09', 'date_basis': 'published_at'})['total'], 0)
            store = AcquisitionStore(path)
            for status, note in [('INVALID', ''), ('RELEVANT', 'a'*2001)]:
                with self.assertRaises(ValueError): store.review_content(rid, status, note)
            with self.assertRaises(ValueError): store.review_content('missing', 'RELEVANT', '')
            dropped = replace(c, caption='Tuy\u1ec3n g\u1ea5p 20 c\u00f4ng nh\u00e2n', crawl_run_id='run3')
            apply_prefilter(dropped)
            self.assertEqual(dropped.prefilter_decision, 'DROP')
            store.reject(dropped)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM content_reviews').fetchone()[0], 0)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM content_review_history').fetchone()[0], 0)
            store.close()
            self.assertEqual(library(path)['total'], 0)

    def test_readonly_missing_database_and_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.sqlite3'
            self.assertEqual(library(path)['total'], 0)
            self.assertFalse(path.exists())
            store = AcquisitionStore(path)
            for number in range(21):
                url = f'https://www.facebook.com/groups/123/posts/{number}'
                store.save_candidate(Candidate('facebook', url, url, 'group', 'run', 'BROWSER', platform_item_id=str(number)))
            store.close()
            self.assertEqual(len(library(path)['rows']), 20)
            self.assertEqual(len(library(path, {'page': 2})['rows']), 1)
            with self.assertRaises(ValueError): library(path, {'page': 0})


if __name__ == '__main__': unittest.main()
