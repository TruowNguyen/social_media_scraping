"""Build request-bound target/context evidence from committed conversation nodes."""
import hashlib
import json
import re
import uuid
from src.acquisition.prefilter import classify_payload
from src.analysis.classification_contract import ContractError, taxonomy_profiles, validate_request
from src.analysis.content_intents import filter_saved_payload,RULE_VERSION,POLICY_VERSION,policy_affected

PROMPT_VERSION = 'conversation-classification-v2.2-intents'


def evidence_payload(item):
    """Classification evidence, independent of raw storage revision counters.

    Keep identities, text, roles, project/query scope and OCR evidence/quality.
    Raw revisions also track availability and extraction metadata which are not
    model evidence. Never modify the persisted input or its provenance.
    """
    result={k:v for k,v in item.items() if k!='revision_id'}
    for key in ('context','image_evidence'):
        if key in result:
            result[key]=[{k:v for k,v in entry.items() if k!='revision_id'} for entry in result[key]]
    return result


def input_is_current(raw,item,snapshot,*,nodes=None,images=None,cache=None):
    key=(item['item_id'],item['source_id'])
    try:
        if cache is not None and key in cache:current=cache[key]
        else:
            current=evidence_payload(build_item(raw,*key,snapshot,nodes=nodes,images=images))
            if cache is not None:cache[key]=current
    except ValueError:return False
    return current==evidence_payload(item)


def build_item(raw, node_id, source_id, snapshot, *, nodes=None, images=None):
    def get(nid):return nodes.get(nid) if nodes is not None else raw.get(nid)
    node=get(node_id)
    if not node: raise ValueError('Stored target required')
    if not raw.db.execute('SELECT 1 FROM node_sources WHERE node_id=? AND source_id=?',(node_id,source_id)).fetchone():
        raise ValueError('Source occurrence required')
    target={'text':node['raw_text'],'evidence_id':'target:'+node_id}
    from src.storage.image_evidence import bindings
    def image_bindings(nid):return images.get(nid,[]) if images is not None else bindings(raw,nid)
    image_evidence=[dict(e,item_id=node_id,revision_id=node['revision_id'],role='TARGET') for e in image_bindings(node_id)]
    context=[]
    for origin_id,role in ((node['root_post_id'],'ROOT_POST'),(node['parent_node_id'],'PARENT_COMMENT')):
        if not origin_id or origin_id==node_id or any(c['item_id']==origin_id for c in context): continue
        parent=get(origin_id)
        if not parent: continue
        parent_images=image_bindings(origin_id)
        image_evidence.extend(dict(e,item_id=origin_id,revision_id=parent['revision_id'],role=role) for e in parent_images)
        if parent['raw_text'] is None and not parent_images: continue
        context.append(dict(item_id=origin_id,revision_id=parent['revision_id'],role=role,
            text=parent['raw_text'] or '',evidence_id='context:'+origin_id))
    # A group establishes scope only. It never claims an explicit project mention.
    candidates=[]
    query_context=None
    if node['platform']=='THREADS':
        for row in raw.db.execute('SELECT payload FROM conversation_observations WHERE node_id=? AND source_id=? ORDER BY rowid DESC',(node_id,source_id)):
            obs=json.loads(row[0])
            if obs.get('project_scope_id') and obs.get('query_id'):
                query_context={'project_id':obs['project_scope_id'],'query_id':obs['query_id'],'query_version':obs.get('query_version',1)};break
    for project_id,profile in snapshot['profiles'].items():
        aliases={'vincons':['VinCons','Vin Cons'],'vinwonders_vu_yen':['VinWonders Vũ Yên','VinWonder Vũ Yên','Vin Wonders Vũ Yên','Vin Wonder Vũ Yên']}.get(project_id,[profile['name']])
        def mentions(text):
            return any(re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',text or '',re.I) for alias in aliases)
        explicit=[e['evidence_id'] for e in image_evidence if e['role']=='TARGET' and mentions(e['text'])]
        if mentions(target['text']):explicit.insert(0,target['evidence_id'])
        if explicit: basis,ids='CONTENT_EXPLICIT',explicit
        else:
            ids=[c['evidence_id'] for c in context if mentions(c['text'])]
            ids.extend(e['evidence_id'] for e in image_evidence if e['role']!='TARGET' and mentions(e['text']))
            basis='PARENT_CONTEXT' if ids else 'QUERY_CONTEXT' if query_context and query_context['project_id']==project_id else 'GROUP_CONTEXT' if node['platform']=='FACEBOOK' and source_id in profile['source_ids'] else 'UNRESOLVED'
        if basis!='UNRESOLVED': candidates.append(dict(project_id=project_id,basis=basis,evidence_ids=ids))
    if not candidates:
        candidates=[dict(project_id=p,basis='UNRESOLVED',evidence_ids=[]) for p in snapshot['profiles']]
    result=dict(item_id=node_id,revision_id=node['revision_id'],node_type=node['node_type'],source_id=source_id,
        target=target,context=context,project_candidates=candidates,context_truncated=False)
    if image_evidence:result['image_evidence']=image_evidence
    if node['platform']=='THREADS':
        result['platform']='THREADS'
        if query_context:result['query_context']=query_context
    return result


def prepare_saved(raw,snapshot,source_id=None,window=None):
    """Re-filter independently; returns eligible inputs plus explicit missing states."""
    result={'items':[],'skipped':[]}
    for node in raw.list_nodes(source_id,window=window):
        from engine.image_enrichment import filter_node
        from src.storage.image_evidence import bindings
        decision=filter_node(raw,node)
        raw.filter_saved(node['node_id'],decision,RULE_VERSION)
        reason='FILTER_DROP' if decision['prefilter_decision']=='DROP' else 'MISSING_TEXT' if not (node['raw_text'] or '').strip() and not bindings(raw,node['node_id']) else None
        if reason:
            result['skipped'].append({'item_id':node['node_id'],'revision_id':node['revision_id'],'reason':reason}); continue
        occurrences=[r[0] for r in raw.db.execute('SELECT source_id FROM node_sources WHERE node_id=? ORDER BY source_id',(node['node_id'],))]
        selected=source_id or occurrences[0]
        result['items'].append(build_item(raw,node['node_id'],selected,snapshot))
    return result


def make_request(items,snapshot):
    project_ids=sorted({c['project_id'] for item in items for c in item['project_candidates']})
    request=dict(schema_version='classification-request-v3' if any(i.get('platform')=='THREADS' for i in items) else 'classification-request-v2',batch_id='batch_'+uuid.uuid4().hex,
        taxonomy_version=snapshot['catalog']['taxonomy_version'],taxonomy_profiles=taxonomy_profiles(snapshot,project_ids),items=items)
    return validate_request(request,snapshot)


def job_key(item,snapshot,model):
    binding=dict(item=item,taxonomy=snapshot,prompt_version=PROMPT_VERSION,rule_version=RULE_VERSION,model=model)
    if policy_affected(item):binding['policy_version']=POLICY_VERSION
    from src.analysis.ocr_policy import context_commercial_policy_affected,CONTEXT_POLICY_VERSION
    if context_commercial_policy_affected(item):binding['policy_version']=CONTEXT_POLICY_VERSION
    return hashlib.sha256(json.dumps(binding,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def build_batches(items,snapshot,max_items=10,max_input_units=64000,output_units_per_item=1800,max_output_units=12000):
    """Conservative UTF-8 byte upper bound, not a claimed provider token count.

    Limits are pilot safety settings, not verified model capacity. Provider must
    validate capability separately. Oversized items remain stored and unclassified.
    """
    if not 0 < max_items <= 100 or min(max_input_units,output_units_per_item,max_output_units)<=0:
        raise ValueError('Positive batching limits required')
    batches=[]; oversized=[]; current=[]
    def fits(group):
        if len(group)>max_items or len(group)*output_units_per_item>max_output_units: return False
        try: request=make_request(group,snapshot)
        except ContractError: return False
        return len(json.dumps(request,ensure_ascii=False).encode())+4000 <= max_input_units
    for item in items:
        if not fits([item]):
            oversized.append({'item_id':item['item_id'],'revision_id':item['revision_id'],'reason':'OVERSIZED_INPUT_OR_OUTPUT'}); continue
        if current and not fits(current+[item]):
            batches.append(make_request(current,snapshot)); current=[]
        current.append(item)
    if current: batches.append(make_request(current,snapshot))
    return {'batches':batches,'oversized':oversized,'measurement':'UTF8_BYTE_UPPER_BOUND_UNVERIFIED_PROVIDER_CAPACITY'}
