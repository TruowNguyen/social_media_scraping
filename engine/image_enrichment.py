"""Enrich committed raw posts with bounded OCR, before independent classification."""
from src.config.env import env_bool
from src.media.image_ocr import recognize,fetch_image,probe,CONFIG_VERSION
from src.storage.image_evidence import initialize,read,save,ref_key,bindings
from src.analysis.content_intents import filter_saved_payload
from src.acquisition.models import utcnow


class OCRBudget:
    def __init__(self,limit=50):self.remaining=limit


def enrich_post(raw,node_id,page,deadline,budget=None,fetcher=fetch_image,recognizer=recognize):
    if not env_bool('FACEBOOK_OCR_ENABLED',True):return {'status':'DISABLED'}
    node=raw.get(node_id)
    if node['node_type']!='POST':return {'status':'NOT_SUPPORTED'}
    if filter_saved_payload({'raw_text':node['raw_text']})['prefilter_decision']=='DROP':return {'status':'SKIPPED_CAPTION_DROP'}
    refs=[r for r in node['media_refs'] if r.get('media_type')=='IMAGE']
    if not refs:return {'status':'NO_IMAGE_REFERENCES','observed_images':0}
    initialize(raw);budget=budget or OCRBudget()
    cached={e['media_ref_id']:e for e in read(raw,node_id)}
    health=probe();processed=0;errors=[]
    for ref in refs[:3]:
        if budget.remaining<=0 or deadline.remaining()<2:
            errors.append('BUDGET_EXHAUSTED');break
        budget.remaining-=1
        try:
            if health['status']!='AVAILABLE':result=dict(type='ocr',schema_version='image-ocr-v1',status='UNAVAILABLE',text=None,
                quality_status='UNKNOWN',error_code=health['error_code'],config_version=CONFIG_VERSION,processed_at=utcnow())
            else:
                data=fetcher(page,ref['url'],deadline)
                import hashlib
                old=cached.get(ref_key(ref))
                if old and old.get('image_sha256')==hashlib.sha256(data).hexdigest() and old.get('config_version')==CONFIG_VERSION and old.get('engine_version')==health.get('engine_version') and old.get('traineddata_version')==health.get('traineddata_version') and old['status'] in {'AVAILABLE','EMPTY'}:
                    processed+=1;continue
                result=recognizer(data,timeout=min(20,deadline.remaining()))
            if ref_key(ref) in cached and cached[ref_key(ref)]['status'] in {'AVAILABLE','EMPTY'} and result['status'] in {'FAILED','UNAVAILABLE'}:
                errors.append(result.get('error_code','OCR_REFRESH_FAILED'));continue
            save(raw,node_id,ref,result);processed+=1
            if result.get('error_code'):errors.append(result['error_code'])
        except Exception as error:
            # Exception text may contain signed URLs; persist only bounded known codes.
            code=str(error) if str(error) in {'IMAGE_HOST_NOT_ALLOWED','IMAGE_URL_UNAVAILABLE','IMAGE_TOO_LARGE','IMAGE_CONTENT_TYPE_INVALID','IMAGE_DECODE_FAILED','IMAGE_PIXEL_LIMIT','IMAGE_REDIRECT_LIMIT','IMAGE_DOWNLOAD_FAILED','IMAGE_DOWNLOAD_TIMEOUT'} else 'IMAGE_ENRICHMENT_FAILED'
            errors.append(code)
            # A failed refresh must not erase previous successful evidence.
            if ref_key(ref) not in cached:save(raw,node_id,ref,dict(type='ocr',schema_version='image-ocr-v1',status='FAILED',text=None,quality_status='UNKNOWN',error_code=code,config_version=CONFIG_VERSION,processed_at=utcnow()))
    return {'status':'PARTIAL' if errors or len(refs)>3 else 'COMPLETE','observed_images':len(refs),'processed_images':processed,'errors':errors}


def filter_node(raw,node):
    decision=filter_saved_payload({'raw_text':node['raw_text'],'missing_data_reasons':node['missing_fields']})
    evidence=bindings(raw,node['node_id'])
    if evidence:
        combined=filter_saved_payload({'raw_text':'\n'.join([node['raw_text'] or '',*[e['text'] for e in evidence]])})
        if combined['prefilter_decision']=='DROP' or any(e['quality_status']!='ACCEPTABLE' for e in evidence):
            return dict(combined,prefilter_decision='REVIEW',rule_id='OCR_REVIEW',drop_reason=None)
        return combined
    return decision
