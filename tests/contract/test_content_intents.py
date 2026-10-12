import unittest
from src.analysis.content_intents import filter_saved_payload


class IntentTests(unittest.TestCase):
    def test_commercial_disclaimers_and_promises_are_not_complaints(self):
        for text in ('Tuyển công nhân VinCons, lương 12 triệu, không phải trung gian',
                     'Bán vé VinWonders, không phải xếp hàng, inbox đặt vé',
                     'Bán điện thoại iPhone 3 triệu, inbox', 'Inbox em mua vé'):
            with self.subTest(text=text):
                self.assertEqual(filter_saved_payload({'raw_text':text})['prefilter_decision'],'DROP')

    def test_real_complaint_survives_a_commercial_disclaimer(self):
        for text in ('Tuyển công nhân không phải trung gian nhưng công ty nợ lương tôi',
                     'Quảng cáo không phải xếp hàng nhưng tôi chờ lâu, không vào được cổng',
                     'Bán vé này có phải lừa đảo không?', 'Trao đổi ca làm'):
            with self.subTest(text=text):
                self.assertEqual(filter_saved_payload({'raw_text':text})['prefilter_decision'],'REVIEW')
        result=filter_saved_payload({'raw_text':'Tuyển công nhân nhưng công ty nợ lương tôi'})
        self.assertIn('RECRUITMENT',result['content_intents'])

    def test_advertising_and_sales_are_distinct_and_can_coexist(self):
        ads=filter_saved_payload({'raw_text':'Giới thiệu dịch vụ mới, ưu đãi khai trương. Trải nghiệm ngay!'})
        self.assertEqual(ads['prefilter_decision'],'DROP')
        self.assertIn('ADVERTISING',ads['content_intents']);self.assertNotIn('SALES',ads['content_intents'])
        sales=filter_saved_payload({'raw_text':'Bán vé VinWonders, inbox đặt vé giá 300k'})
        self.assertEqual(sales['prefilter_decision'],'DROP')
        self.assertIn('SALES',sales['content_intents'])
        both=filter_saved_payload({'raw_text':'Ưu đãi khai trương, bán vé giá rẻ, inbox đặt hàng'})
        self.assertIn('ADVERTISING',both['content_intents']);self.assertIn('SALES',both['content_intents'])

    def test_complaint_and_neutral_mentions_are_not_dropped_by_keyword(self):
        for text in ('Quảng cáo bán vé nhưng tôi chờ lâu, không vào được cổng',
                     'Bán vé tại VinCons, kẹt cổng quá, đứng mãi',
                     'Quảng cáo này có phải lừa đảo không?',
                     'Thông báo khai trương công viên hôm nay'):
            self.assertNotEqual(filter_saved_payload({'raw_text':text})['prefilter_decision'],'DROP')
