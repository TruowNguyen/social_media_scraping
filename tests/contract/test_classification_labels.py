import unittest
from src.analysis.classification_labels import reason_vi


class VietnameseReasonTests(unittest.TestCase):
    def test_actual_vietnamese_model_reason_is_preserved(self):
        self.assertEqual(reason_vi({'relevance':'DROP','drop_reason':'Tin tuyển dụng, không có phản ánh.'}),
                         'Tin tuyển dụng, không có phản ánh.')
        self.assertEqual(reason_vi({'relevance':'REVIEW','review_reason':'Chưa xác định được dự án từ bình luận.'}),
                         'Chưa xác định được dự án từ bình luận.')

    def test_historical_english_reason_uses_confirmed_intents_without_mutation(self):
        analysis = {'relevance': 'DROP', 'content_intents': ['RECRUITMENT'],
                    'drop_reason': 'Pure recruitment post, no complaint.'}
        self.assertEqual(reason_vi(analysis), 'Nội dung tuyển dụng, được loại khỏi kết quả theo dõi.')
        self.assertEqual(analysis['drop_reason'], 'Pure recruitment post, no complaint.')

    def test_unknown_reason_is_not_presented_as_sales(self):
        text = reason_vi({'relevance': 'DROP', 'content_intents': ['UNKNOWN'],
                          'drop_reason': 'No relevant issue.'})
        self.assertEqual(text, 'Nội dung được phân loại ngoài phạm vi vấn đề cần theo dõi.')

    def test_filter_drop_and_review_have_vietnamese_reasons(self):
        self.assertIn('mua bán', reason_vi(filter_decision={
            'prefilter_decision': 'DROP', 'content_intents': ['BUY_SELL']}))
        self.assertIn('xem xét', reason_vi({'relevance': 'REVIEW', 'review_reason': 'Ambiguous context'}))
        self.assertIsNone(reason_vi({'relevance': 'KEEP'}))
