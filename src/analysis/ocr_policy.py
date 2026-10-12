"""Shared provider/validator policy for uncertain target versus context OCR."""
from src.analysis.content_intents import filter_saved_payload
from src.acquisition.prefilter import protected_content
import re

COMMERCIAL={'ADVERTISING','SALES','RECRUITMENT','RENTAL','BUY_SELL','LOAN_DEBT','GOODS_EXCHANGE'}
CONTEXT_POLICY_VERSION='independent-commercial-context-v3.1'


def context_commercial_policy_affected(item):
    """Scope the refinement to the previous context-only commercial OCR exception."""
    text=item.get('target',{}).get('text') or ''
    images=item.get('image_evidence',[])
    labels=filter_saved_payload({'raw_text':text})['content_intents']
    return bool(text.strip() and not protected_content(text) and COMMERCIAL.intersection(labels)
                and any(e['role']!='TARGET' and e['quality_status']!='ACCEPTABLE' for e in images)
                and not any(e['role']=='TARGET' and e['quality_status']!='ACCEPTABLE' for e in images))


def independent_commercial_target(item):
    text=item.get('target',{}).get('text') or ''
    decision=filter_saved_payload({'raw_text':text})
    from src.acquisition.prefilter import normalize
    question=bool(re.search(r'\b(?:bao nhieu|cho hoi|xin hoi|cho xin|duoc khong|duoc ko)\b',normalize(text)) or '?' in text)
    return bool(text.strip() and not protected_content(text) and not question
                and (decision['prefilter_decision']=='DROP' or 'ADVERTISING' in decision['content_intents']))


def uncertain_ocr_requires_review(item,result=None):
    uncertain=[e for e in item.get('image_evidence',[]) if e['quality_status']!='ACCEPTABLE']
    if not uncertain:return False
    if any(e['role']=='TARGET' for e in uncertain):return True
    # A commercial DROP supported by the target alone need not depend on parent OCR.
    if not independent_commercial_target(item):return True
    if result is None:return False
    if result['relevance']!='DROP' or not COMMERCIAL.intersection(result.get('content_intents',[])):
        return True
    ids={e['evidence_id'] for e in uncertain}
    used={eid for p in result['project_matches'] for eid in p['evidence_ids']}
    used.update(e['evidence_id'] for issue in result['issues'] for e in issue['evidence'])
    return bool(ids & used)
