"""Strict local schemas and request-bound validation for LLM batch payloads."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator
from src.analysis.taxonomy import validate_catalog, validate_profile


class ContractError(ValueError):
    def __init__(self, code, path=''):
        self.code, self.path = code, path
        # Never include raw model/caption/key values in validation errors.
        super().__init__(code + (':' + path if path else ''))


def _json_types(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractError('NON_FINITE_NUMBER')
        return
    if type(value) is list:
        for child in value:
            _json_types(child)
        return
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise ContractError('NON_JSON_KEY')
        for child in value.values():
            _json_types(child)
        return
    raise ContractError('NON_JSON_TYPE')


def parse_json(payload):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ContractError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def constant(_value):
        raise ContractError('NON_FINITE_NUMBER')

    if isinstance(payload, str):
        try:
            payload = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ContractError('INVALID_JSON') from exc
    try:
        _json_types(payload)
    except RecursionError as exc:
        raise ContractError('JSON_TOO_DEEP') from exc
    return payload


@lru_cache(maxsize=4)
def _validator(name):
    if name not in {'classification-request-v2', 'classification-result-v2','classification-request-v3','classification-result-v3'}:
        raise ContractError('UNKNOWN_SCHEMA')
    schema = json.loads((Path(__file__).with_name('schemas') / (name + '.json')).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def get_schema(name):
    return deepcopy(_validator(name).schema)


def _shape(data, name):
    error = next(_validator(name).iter_errors(data), None)
    if error:
        # Paths are known schema field names/indexes, not error.message values.
        raise ContractError('SCHEMA_' + str(error.validator).upper(), '/'.join(map(str, error.absolute_path)))


def taxonomy_profiles(snapshot, project_ids):
    """Definitions to attach to a request; does not bypass runtime approval."""
    catalog = validate_catalog(snapshot['catalog'])
    output = []
    for project_id in project_ids:
        profile = snapshot['profiles'].get(project_id)
        if profile is None:
            raise ContractError('UNKNOWN_PROJECT')
        validate_profile(profile, snapshot['catalog'])
        issues = []
        for identifier, priority in profile['issue_priorities'].items():
            issue = catalog[identifier]
            issues.append({**{key: deepcopy(issue[key]) for key in ('issue_id', 'family_id', 'name', 'definition',
                'include_examples', 'exclude_examples', 'required_evidence')}, 'priority': priority})
        output.append({'project_id': project_id, 'issues': issues})
    return output


def _origins(item):
    return {item['target']['evidence_id']: {'item_id': item['item_id'], 'text': item['target']['text'], 'role': 'TARGET'},
        **{p['evidence_id']: {'item_id': p['item_id'], 'text': p['text'], 'role': p['role']} for p in item['context']},
        **{p['evidence_id']: {'item_id': p['item_id'], 'text': p['text'], 'role':p['role']} for p in item.get('image_evidence',[])}}


def _project_evidence(match, item, origins):
    ids, basis = match['evidence_ids'], match['basis']
    if any(e not in origins or not (origins[e]['text'] or '').strip() for e in ids):
        raise ContractError('PROJECT_EVIDENCE_UNKNOWN_OR_EMPTY')
    if basis == 'CONTENT_EXPLICIT':
        if not ids or any(origins[e]['role'] != 'TARGET' for e in ids):
            raise ContractError('PROJECT_EXPLICIT_REQUIRES_TARGET')
    elif basis == 'PARENT_CONTEXT':
        if not ids or any(origins[e]['role'] == 'TARGET' for e in ids):
            raise ContractError('PROJECT_PARENT_REQUIRES_CONTEXT')
    elif ids:
        raise ContractError('CONTEXT_OR_UNRESOLVED_HAS_TEXT_EVIDENCE')


def validate_request(payload, snapshot):
    data = parse_json(payload)
    name=data.get('schema_version') if isinstance(data,dict) else None
    if name not in {'classification-request-v2','classification-request-v3'}:raise ContractError('UNKNOWN_SCHEMA')
    _shape(data, name)
    if data['taxonomy_version'] != snapshot['catalog']['taxonomy_version']:
        raise ContractError('TAXONOMY_VERSION_MISMATCH')
    project_ids = [p['project_id'] for p in data['taxonomy_profiles']]
    if len(set(project_ids)) != len(project_ids):
        raise ContractError('DUPLICATE_TAXONOMY_PROFILE')
    expected = {p['project_id']: p for p in taxonomy_profiles(snapshot, project_ids)}
    for profile in data['taxonomy_profiles']:
        ids = [i['issue_id'] for i in profile['issues']]
        expected_issues = {i['issue_id']: i for i in expected[profile['project_id']]['issues']}
        if len(ids) != len(set(ids)) or {i['issue_id']: i for i in profile['issues']} != expected_issues:
            raise ContractError('TAXONOMY_DEFINITIONS_MISMATCH')
    item_ids = [i['item_id'] for i in data['items']]
    if len(set(item_ids)) != len(item_ids):
        raise ContractError('DUPLICATE_ITEM_ID')
    for item in data['items']:
        evidence_ids = [item['target']['evidence_id'], *[p['evidence_id'] for p in item['context']]]
        evidence_ids.extend(p['evidence_id'] for p in item.get('image_evidence',[]))
        owners={item['item_id']:item['revision_id'],**{p['item_id']:p['revision_id'] for p in item['context']}}
        roles={item['item_id']:'TARGET',**{p['item_id']:p['role'] for p in item['context']}}
        for evidence in item.get('image_evidence',[]):
            if owners.get(evidence['item_id'])!=evidence['revision_id'] or roles.get(evidence['item_id'])!=evidence['role']:
                raise ContractError('IMAGE_EVIDENCE_OWNER_MISMATCH')
        origin_ids = [item['item_id'], *[p['item_id'] for p in item['context']]]
        if len(set(evidence_ids)) != len(evidence_ids) or len(set(origin_ids)) != len(origin_ids):
            raise ContractError('DUPLICATE_EVIDENCE_OR_ORIGIN_ID')
        if item['node_type'] == 'POST' and item['context']:
            raise ContractError('POST_HAS_PARENT_CONTEXT')
        origins = _origins(item)
        candidates = [c['project_id'] for c in item['project_candidates']]
        if len(set(candidates)) != len(candidates) or not set(candidates) <= set(project_ids):
            raise ContractError('INVALID_PROJECT_CANDIDATES')
        for match in item['project_candidates']:
            _project_evidence(match, item, origins)
            if match['basis'] == 'GROUP_CONTEXT' and item['source_id'] not in snapshot['profiles'][match['project_id']]['source_ids']:
                raise ContractError('PROJECT_GROUP_NOT_MAPPED')
            if match['basis']=='QUERY_CONTEXT':
                query=item.get('query_context',{})
                if item.get('platform')!='THREADS' or query.get('query_id')!=item['source_id'] or query.get('project_id')!=match['project_id']:
                    raise ContractError('PROJECT_QUERY_NOT_MAPPED')
    return data


def _result(result, item, request_profiles):
    if result['revision_id'] != item['revision_id']:
        raise ContractError('REVISION_MISMATCH')
    origins = _origins(item)
    candidates = {p['project_id']: p for p in item['project_candidates']}
    matches = result['project_matches']
    match_ids = [m['project_id'] for m in matches]
    if len(set(match_ids)) != len(match_ids):
        raise ContractError('DUPLICATE_PROJECT_MATCH')
    for match in matches:
        candidate = candidates.get(match['project_id'])
        if candidate is None or match['basis'] != candidate['basis'] or not set(match['evidence_ids']) <= set(candidate['evidence_ids']):
            raise ContractError('UNSUPPORTED_PROJECT_MATCH')
        _project_evidence(match, item, origins)
    applicable = match_ids or list(candidates)
    allowed = {i['issue_id'] for pid in applicable for i in request_profiles[pid]['issues']}
    ids = [i['issue_id'] for i in result['issues']]
    if len(set(ids)) != len(ids) or not set(ids) <= allowed:
        raise ContractError('UNKNOWN_DISABLED_OR_DUPLICATE_ISSUE')
    unspecified = next((i for i in result['issues'] if i['issue_id'] == 'GATE_CONGESTION_UNSPECIFIED'), None)
    if unspecified:
        claims = {(e['evidence_id'], e['quote']) for e in unspecified['evidence']}
        for issue in result['issues']:
            if issue['issue_id'] in {'ENTRY_QUEUE', 'EXIT_QUEUE', 'CHECKIN_BOTTLENECK', 'VEHICLE_CONGESTION', 'WORKER_CONGESTION'} and claims & {(e['evidence_id'], e['quote']) for e in issue['evidence']}:
                raise ContractError('CONFLICTING_GATE_LABELS')
    if result['needs_review'] != (result['review_reason'] is not None):
        raise ContractError('REVIEW_FLAG_REASON_MISMATCH')
    relevance = result['relevance']
    intents=set(result.get('content_intents',[]))
    if relevance=='DROP' and 'COMPLAINT' in intents:
        raise ContractError('COMPLAINT_INTENT_CANNOT_BE_DROPPED')
    if relevance=='KEEP' and intents & {'ADVERTISING','SALES','RECRUITMENT','RENTAL','BUY_SELL','LOAN_DEBT','GOODS_EXCHANGE'} and 'COMPLAINT' not in intents:
        raise ContractError('COMMERCIAL_KEEP_REQUIRES_COMPLAINT_INTENT')
    if relevance == 'DROP':
        if result['issues'] or result['drop_reason'] is None or result['needs_review']:
            raise ContractError('INVALID_DROP_STATE')
    else:
        if result['drop_reason'] is not None:
            raise ContractError('UNEXPECTED_DROP_REASON')
        if relevance == 'REVIEW' and not result['needs_review']:
            raise ContractError('REVIEW_REQUIRES_REASON')
    if relevance == 'KEEP':
        target_text=bool((item['target']['text'] or '').strip()) or any(e['role']=='TARGET' and e['text'].strip() for e in item.get('image_evidence',[]))
        if not ids or not target_text or not matches or any(m['basis'] in {'UNRESOLVED','QUERY_CONTEXT'} for m in matches):
            raise ContractError('KEEP_INSUFFICIENT_EVIDENCE_OR_PROJECT')
        if item['context_truncated'] and not result['needs_review']:
            raise ContractError('TRUNCATED_CONTEXT_REQUIRES_REVIEW')
    from src.analysis.ocr_policy import uncertain_ocr_requires_review
    if uncertain_ocr_requires_review(item,result):
        if relevance=='DROP' or not result['needs_review']:
            raise ContractError('UNCERTAIN_OCR_REQUIRES_REVIEW')
    for issue in result['issues']:
        target_support = False
        for evidence in issue['evidence']:
            origin = origins.get(evidence['evidence_id'])
            if origin is None or origin['item_id'] != evidence['origin_item_id'] or not origin['text'] or evidence['quote'] not in origin['text']:
                raise ContractError('EVIDENCE_NOT_IN_INPUT')
            target_support |= origin['role'] == 'TARGET'
        if relevance == 'KEEP' and not target_support:
            raise ContractError('KEEP_ISSUE_REQUIRES_TARGET_EVIDENCE')
        if issue['location'] is not None and not any(issue['location'] in (origin['text'] or '') for origin in origins.values()):
            raise ContractError('LOCATION_NOT_IN_INPUT')


def validate_response(payload, request, snapshot, *, allow_partial=False):
    """Return accepted items plus retry reasons, or reject atomically in strict mode."""
    request = validate_request(request, snapshot)
    data = parse_json(payload)
    result_schema='classification-result-v3' if request['schema_version']=='classification-request-v3' else 'classification-result-v2'
    # Envelope invalid/JSON invalid is never partially accepted.
    if not isinstance(data, dict) or set(data) != {'schema_version', 'batch_id', 'results'} or data.get('schema_version') != result_schema or data.get('batch_id') != request['batch_id'] or not isinstance(data.get('results'), list) or len(data['results']) > 100:
        raise ContractError('INVALID_RESPONSE_ENVELOPE')
    items = {i['item_id']: i for i in request['items']}
    profiles = {p['project_id']: p for p in request['taxonomy_profiles']}
    counts = Counter(r.get('item_id') for r in data['results'] if isinstance(r, dict) and isinstance(r.get('item_id'), str))
    accepted, rejected, unknown = [], {}, []
    seen = set()
    item_schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$defs': get_schema(result_schema)['$defs'], '$ref': '#/$defs/result'}
    validator = Draft202012Validator(item_schema)
    for result in data['results']:
        identifier = result.get('item_id') if isinstance(result, dict) else None
        if not isinstance(identifier, str) or identifier not in items:
            unknown.append('UNKNOWN_OR_MISSING_ITEM_ID')
            continue
        seen.add(identifier)
        if counts[identifier] != 1:
            rejected[identifier] = 'DUPLICATE_RESULT_ID'
            continue
        if next(validator.iter_errors(result), None) is not None:
            rejected[identifier] = 'INVALID_RESULT_SCHEMA'
            continue
        try:
            _result(result, items[identifier], profiles)
        except ContractError as exc:
            rejected[identifier] = exc.code
        else:
            accepted.append(result)
    for identifier in items.keys() - seen:
        rejected[identifier] = 'MISSING_RESULT'
    if (rejected or unknown) and not allow_partial:
        raise ContractError('INVALID_BATCH_RESULTS')
    return {'accepted': accepted, 'rejected': rejected, 'batch_errors': unknown,
        'complete': not rejected and not unknown}
