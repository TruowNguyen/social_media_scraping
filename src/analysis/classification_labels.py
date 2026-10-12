"""Vietnamese presentation reasons; original model evidence stays in storage."""
import re


def _vietnamese_reason(value):
    if isinstance(value,str) and re.search(r'[À-ỹĐđ]',value):return value.strip()
    return None

INTENT_LABELS = {
    'ADVERTISING': 'quảng cáo', 'SALES': 'bán hàng',
    'RECRUITMENT': 'tuyển dụng', 'RENTAL': 'cho thuê hoặc thuê',
    'BUY_SELL': 'mua bán', 'LOAN_DEBT': 'vay nợ',
    'GOODS_EXCHANGE': 'trao đổi hàng hóa',
}


def reason_vi(analysis=None, filter_decision=None):
    """Explain stored decisions without translating or inventing model evidence.

    Fixed Vietnamese labels also cover historical English prose/reason codes.
    This is a presentation of relevance/intents, not a new classification.
    """
    analysis = analysis or {}
    decision = filter_decision or {}
    relevance = analysis.get('relevance') or decision.get('prefilter_decision')
    if relevance == 'DROP':
        detail=_vietnamese_reason(analysis.get('drop_reason'))
        if detail:return detail
        intents = analysis.get('content_intents') or decision.get('content_intents') or []
        labels = list(dict.fromkeys(INTENT_LABELS[i] for i in intents if i in INTENT_LABELS))
        if not labels and decision.get('drop_reason') in INTENT_LABELS:
            labels = [INTENT_LABELS[decision['drop_reason']]]
        if labels:
            return 'Nội dung ' + ', '.join(labels) + ', được loại khỏi kết quả theo dõi.'
        return 'Nội dung được phân loại ngoài phạm vi vấn đề cần theo dõi.'
    if relevance == 'REVIEW':
        detail=_vietnamese_reason(analysis.get('review_reason'))
        if detail:return detail
        return 'Nội dung cần được xem xét thêm trước khi xác nhận là phản ánh phù hợp.'
    return None
