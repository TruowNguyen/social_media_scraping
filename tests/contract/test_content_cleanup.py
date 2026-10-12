from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from engine.content_cleanup import purge_recruitment
from engine.acquisition import AcquisitionEngine
from engine.registry import Registry
from src.browser.profiles import PROJECT_ROOT
from src.acquisition.prefilter import apply_prefilter
from src.acquisition.models import Candidate
from src.storage.acquisition import AcquisitionStore


def candidate(text, identifier='456'):
    url = f'https://www.facebook.com/groups/123/posts/{identifier}'
    return Candidate('facebook', url, url, 'group', 'run', 'BROWSER', caption=text, platform_item_id=identifier)


class RecruitmentCleanupTests(unittest.TestCase):
    def test_recruitment_salary_promise_is_not_a_wage_complaint(self):
        ad = candidate('Góc tìm đồng đội cty vincons. Thợ xây 16-22tr. Cam kết không chậm lương, ăn ở cty lo.')
        self.assertEqual(apply_prefilter(ad), 'DROP')
        self.assertEqual(ad.drop_reason, 'RECRUITMENT')
        complaint = candidate('Tìm đồng đội, cam kết không chậm lương nhưng thực tế nợ lương hai tháng.')
        self.assertEqual(apply_prefilter(complaint), 'REVIEW')
        self.assertEqual(apply_prefilter(candidate('Mình cần tìm phòng trọ gần vin Mỹ Lâm')), 'DROP')

    def test_missed_search_snippet_recruitment_and_group_name(self):
        for title, snippet in [
            ('Ms Thương', 'VINCONS đang tiếp nhận thông tin nhân sự cơ điện. Phụ cấp ăn trưa: 60k/ngày.'),
            ('Cơ hội mới', 'Việc làm hấp dẫn đang chờ bạn! VINCONS tìm kiếm những ứng viên năng nổ.'),
            ('VINCONS GÂY CHOÁNG KHI TUYỂN DỤNG KHỦNG', 'Tuyển dụng công nhân trên toàn quốc.'),
            ('CƠ HỘI ĐÃ TRỞ LẠI', 'VINCONS tuyển dụng khối văn phòng. Vị trí tuyển dụng: thủ kho.'),
            ('Vincons Làng Vân', 'Đã tuyển số lượng lớn công nhân. Bao ăn ở, thanh toán lương ngày 15&30.'),
        ]:
            with self.subTest(title=title):
                ad = candidate(None)
                ad.title, ad.search_snippet = title, snippet
                self.assertEqual(apply_prefilter(ad), 'DROP')
                self.assertEqual(ad.drop_reason, 'RECRUITMENT')
        for title, snippet in [
            ('Vincons Cần Giờ', 'Tổ Sơn Bả ▻ TUYỂN DỤNG CÔNG NHÂN CƠ HỮU VINCONS. Làm ngày chủ nhật.'),
            ('Cổng đóng', 'Other posts: VINCONS tiếp nhận thông tin nhân sự, bao ăn ở.'),
            ('Phản ánh', 'Tuyển công nhân nhưng nợ lương, bao ăn ở chỉ là lời hứa.'),
            ('Cảnh báo lừa đảo tuyển dụng Vincons', 'Nhận hồ sơ ứng tuyển rồi thu tiền.'),
        ]:
            ad = candidate(None)
            ad.title, ad.search_snippet = title, snippet
            self.assertNotEqual(apply_prefilter(ad), 'DROP', title)

    def test_new_wordings_and_complaints(self):
        for text in ['VINCONS TI\u1ebeP T\u1ee4C B\u1ed4 SUNG C\u00d4NG NH\u00c2N X\u00c2Y D\u1ef0NG',
                     'Li\u00ean t\u1ee5c b\u1ed5 sung nh\u00e2n s\u1ef1, \u0111\u0103ng k\u00fd s\u1edbm',
                     'Mu\u1ed1n xin v\u00e0o l\u00e0m c\u00f4ng nh\u00e2n, cho em h\u1ecfi nh\u00e0 tuy\u1ec3n d\u1ee5ng c\u00f3 tuy\u1ec3n kh\u00f4ng',
                     'Tuy\u1ec3n 4-5 th\u1ee3 l\u01b0\u01a1ng 19-26tr',
                     'C\u00f4ng nh\u00e2n l\u01b0\u01a1ng 20tr #tuyendung']:
            self.assertEqual(apply_prefilter(candidate(text)), 'DROP', text)
        for text in ['Ph\u1ea3n \u00e1nh tuy\u1ec3n c\u00f4ng nh\u00e2n nh\u01b0ng n\u1ee3 l\u01b0\u01a1ng',
                     'C\u1ea3nh b\u00e1o l\u1eeba \u0111\u1ea3o tuy\u1ec3n d\u1ee5ng',
                     'Trao \u0111\u1ed5i ca l\u00e0m', 'H\u1ecfi v\u1ec1 ch\u1ebf \u0111\u1ed9 tuy\u1ec3n d\u1ee5ng']:
            self.assertEqual(apply_prefilter(candidate(text)), 'REVIEW', text)
        container = candidate('TUY\u1ec2N D\u1ee4NG C\u00d4NG NH\u00c2N')
        container.candidate_kind = 'SOURCE_CONTAINER'
        self.assertEqual(apply_prefilter(container), 'REVIEW')
        ad = candidate('B\u1ed5 sung c\u00f4ng nh\u00e2n')
        ad.search_snippet = 'Other posts: Ph\u1ea3n \u00e1nh c\u1ed5ng k\u1eb9t xe'
        self.assertEqual(apply_prefilter(ad), 'DROP')

    def test_purge_is_atomic_idempotent_and_prevents_metadata_resurrection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AcquisitionStore(Path(directory) / 'test.sqlite3')
            ad = candidate('B\u1ed5 sung c\u00f4ng nh\u00e2n')
            rid, _ = store.save_candidate(ad)
            store.observation(replace(ad, candidate_id='obs2', crawl_run_id='run2'), record_id=rid)
            # Existing notes from the older rule may contain the excluded text.
            store.db.execute('INSERT INTO content_reviews VALUES (?,?)', (rid, '{"status":"RELEVANT","note":"old"}'))
            store.db.execute('INSERT INTO content_review_history(record_id,payload) VALUES (?,?)', (rid, '{"note":"old"}'))
            store.db.commit()
            queued = candidate('Tuy\u1ec3n 4-5 th\u1ee3', '789')
            queued.title = queued.caption
            store.enqueue(queued, 'SOURCE_NOT_READY')
            keep = candidate('Ph\u1ea3n \u00e1nh n\u1ee3 l\u01b0\u01a1ng', '999')
            store.save_candidate(keep)
            self.assertEqual(purge_recruitment(store)['records_removed'], 1)
            self.assertEqual(len(store.export_records()), 2)
            result = purge_recruitment(store, apply=True)
            self.assertEqual((result['records_removed'], result['queue_removed']), (1, 1))
            for table in ['content_reviews', 'content_review_history', 'queue']:
                self.assertEqual(store.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
            self.assertEqual(len(store.export_records()), 1)
            self.assertEqual(purge_recruitment(store, apply=True)['records_removed'], 0)
            rediscovered = replace(ad, caption=None, candidate_id='obs3', crawl_run_id='run3')
            engine = AcquisitionEngine(Registry(PROJECT_ROOT/'config'), store)
            counters = {'prefilter_drop': 0}
            self.assertFalse(engine.filter(rediscovered, counters))
            self.assertEqual(counters['prefilter_drop'], 1)
            with self.assertRaises(ValueError): store.save_candidate(replace(ad, caption=None))
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM observations WHERE record_id=?', (rid,)).fetchone()[0], 0)
            store.close()
