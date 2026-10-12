"""Saved-raw intent labels; issue relevance is evaluated independently downstream."""
import re
from src.acquisition.prefilter import (classify_payload,normalize,protected_content,
    DIRECT_INTENT,STAFFING_OFFER,APPLICANT_OFFER,JOB_SEEKING)

SALES=r'\b(?:ban ve|rao ban|can ban|can mua|thanh ly|chot don|dat hang|mua ngay|nhan (?:dat|book) ve|dai ly ve|gia ban|bang gia)\b'
ADVERTISING=r'\b(?:quang cao|khuyen mai|uu dai|khai truong|gioi thieu (?:dich vu|san pham)|ra mat (?:dich vu|san pham))\b'
CTA=r'\b(?:inbox|lien he|nhanh tay|dang ky ngay|trai nghiem ngay|kham pha ngay|mua ngay|dat ngay)\b'
INTENT_MAPPING={'SALES_MARKETING':'SALES','REAL_ESTATE_LISTING':'BUY_SELL'}
RULE_VERSION='saved-node-prefilter-v2-intents'
POLICY_VERSION='commercial-context-v3'


def policy_affected(item):
    """Version only inputs covered by the revised commercial/OCR policy."""
    texts=[item.get('target',{}).get('text') or '']
    texts.extend(e.get('text') or '' for e in item.get('image_evidence',[]) if e.get('role')=='TARGET')
    text=normalize(' '.join(texts))
    return bool(any(e.get('quality_status')!='ACCEPTABLE' for e in item.get('image_evidence',[]))
        or any(re.search(p,text) for p in DIRECT_INTENT.values())
        or re.search(STAFFING_OFFER+'|'+APPLICANT_OFFER+'|'+JOB_SEEKING,text)
        or re.search(SALES+'|'+ADVERTISING,text))


def filter_saved_payload(payload):
    decision=classify_payload(payload)
    text=normalize(payload.get('raw_text') or payload.get('caption') or '')
    labels=[]
    protected=protected_content(text)
    if re.search(ADVERTISING,text): labels.append('ADVERTISING')
    if re.search(SALES,text): labels.append('SALES')
    for intent,pattern in DIRECT_INTENT.items():
        if re.search(pattern,text):
            label=INTENT_MAPPING.get(intent,intent)
            if label not in labels:labels.append(label)
    if re.search(STAFFING_OFFER+'|'+APPLICANT_OFFER+'|'+JOB_SEEKING,text) and 'RECRUITMENT' not in labels:
        labels.append('RECRUITMENT')
    if decision.drop_reason:
        label=INTENT_MAPPING.get(decision.drop_reason,decision.drop_reason)
        if label not in labels: labels.append(label)
    if protected:
        # Protection is conservative; only the LLM/reviewer confirms a complaint.
        decision.prefilter_decision='REVIEW';decision.drop_reason=None;decision.rule_id=None
    elif 'ADVERTISING' in labels and re.search(CTA,text) and decision.prefilter_decision!='DROP':
        decision.prefilter_decision='DROP';decision.rule_id='CLEAR_ADVERTISING_CTA';decision.drop_reason='ADVERTISING'
    return {'prefilter_decision':decision.prefilter_decision,'rule_id':decision.rule_id,
        'drop_reason':decision.drop_reason,'content_intents':labels or ['UNKNOWN']}
