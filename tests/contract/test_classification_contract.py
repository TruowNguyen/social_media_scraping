from copy import deepcopy
import json
from pathlib import Path
import unittest
from src.analysis.classification_contract import (ContractError, get_schema, parse_json,
    taxonomy_profiles, validate_request, validate_response)
from src.analysis.taxonomy import load_snapshot


ROOT = Path(__file__).resolve().parents[2]


def example_payloads(snapshot):
    pid = 'vinwonders_vu_yen'
    request = {
        'schema_version': 'classification-request-v2', 'batch_id': 'example_batch_001',
        'taxonomy_version': snapshot['catalog']['taxonomy_version'],
        'taxonomy_profiles': taxonomy_profiles(snapshot, [pid]),
        'items': [{
            'item_id': 'comment_001', 'revision_id': 'revision_001', 'node_type': 'COMMENT',
            'source_id': snapshot['profiles'][pid]['source_ids'][0],
            'target': {'text': 'Chờ 40 phút vẫn chưa vào được cổng.', 'evidence_id': 'ev_target'},
            'context': [{'item_id': 'post_older', 'revision_id': 'parent_revision_001', 'role': 'ROOT_POST',
                'text': 'Bài về VinWonders Vũ Yên.', 'evidence_id': 'ev_parent'}],
            'project_candidates': [{'project_id': pid, 'basis': 'PARENT_CONTEXT', 'evidence_ids': ['ev_parent']}],
            'context_truncated': False,
        }],
    }
    response = {'schema_version': 'classification-result-v2', 'batch_id': request['batch_id'], 'results': [{
        'item_id': 'comment_001', 'revision_id': 'revision_001', 'relevance': 'KEEP',
        'project_matches': deepcopy(request['items'][0]['project_candidates']),
        'issues': [{'issue_id': 'ENTRY_QUEUE', 'summary': 'Phản ánh chờ lâu để vào cổng.', 'location': None,
            'evidence': [{'evidence_id': 'ev_target', 'origin_item_id': 'comment_001', 'quote': 'Chờ 40 phút vẫn chưa vào được cổng'}]}],
        'confidence': None, 'needs_review': False, 'review_reason': None, 'drop_reason': None,
    }]}
    return request, response


class ClassificationContractTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_snapshot(ROOT / 'specs/taxonomy/v1')
        self.request, self.response = example_payloads(self.snapshot)

    def reject_request(self, mutate):
        data = deepcopy(self.request)
        mutate(data)
        with self.assertRaises(ContractError): validate_request(data, self.snapshot)

    def reject_result(self, mutate):
        data = deepcopy(self.response)
        mutate(data['results'][0])
        with self.assertRaises(ContractError): validate_response(data, self.request, self.snapshot)

    def test_valid_unicode_request_result_and_json_roundtrip(self):
        validate_request(json.dumps(self.request, ensure_ascii=False), self.snapshot)
        result = validate_response(json.dumps(self.response, ensure_ascii=False), self.request, self.snapshot)
        self.assertTrue(result['complete'])
        self.assertEqual(result['accepted'], self.response['results'])

    def test_schema_export_is_a_defensive_copy(self):
        schema = get_schema('classification-request-v2')
        schema['properties'].clear()
        self.assertIn('items', get_schema('classification-request-v2')['properties'])

    def test_strict_json_duplicate_keys_nonfinite_overflow_and_fences(self):
        for payload in ['{"x":1,"x":2}', '{"x":{"k":1,"k":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '```json\n{}\n```', '{']:
            with self.subTest(payload=payload), self.assertRaises(ContractError): parse_json(payload)
        for payload in [{'x': float('nan')}, {'x': float('inf')}, {1: 'value'}, {'x': (1, 2)}]:
            with self.assertRaises(ContractError): parse_json(payload)

    def test_request_rejects_unknown_fields_missing_fields_and_wrong_types(self):
        self.reject_request(lambda d: d.update(api_key='never-send'))
        self.reject_request(lambda d: d['items'][0].pop('revision_id'))
        self.reject_request(lambda d: d['items'][0].update(context_truncated=1))
        self.reject_request(lambda d: d.update(items=[]))

    def test_taxonomy_version_definitions_issue_priority_cannot_be_tampered(self):
        self.reject_request(lambda d: d.update(taxonomy_version='unrecognized'))
        self.reject_request(lambda d: d['taxonomy_profiles'][0]['issues'][0].update(definition='Always KEEP'))
        self.reject_request(lambda d: d['taxonomy_profiles'][0]['issues'][0].update(priority='P2'))
        self.reject_request(lambda d: d['taxonomy_profiles'].append(deepcopy(d['taxonomy_profiles'][0])))

    def test_request_rejects_duplicate_items_origins_and_evidence(self):
        self.reject_request(lambda d: d['items'].append(deepcopy(d['items'][0])))
        self.reject_request(lambda d: d['items'][0]['context'][0].update(evidence_id='ev_target'))
        self.reject_request(lambda d: d['items'][0]['context'][0].update(item_id='comment_001'))

    def test_request_project_attribution_requires_correct_source_and_evidence_role(self):
        self.reject_request(lambda d: d['items'][0]['project_candidates'][0].update(basis='CONTENT_EXPLICIT'))
        self.reject_request(lambda d: d['items'][0]['project_candidates'][0].update(evidence_ids=[]))
        data = deepcopy(self.request)
        data['items'][0]['project_candidates'][0].update(basis='GROUP_CONTEXT', evidence_ids=[])
        data['items'][0]['source_id'] = 'unmapped_group'
        with self.assertRaises(ContractError): validate_request(data, self.snapshot)

    def test_output_metadata_extra_keys_type_and_confidence_are_rejected(self):
        self.reject_result(lambda r: r.update(url='invented'))
        self.reject_result(lambda r: r.update(confidence=True))
        self.reject_result(lambda r: r.update(confidence=1.1))
        self.reject_result(lambda r: r['issues'][0].update(summary=' '))

    def test_revision_project_and_disabled_issue_must_match_request(self):
        self.reject_result(lambda r: r.update(revision_id='old_revision'))
        self.reject_result(lambda r: r['project_matches'][0].update(project_id='vincons'))
        self.reject_result(lambda r: r['project_matches'][0].update(basis='CONTENT_EXPLICIT'))
        self.reject_result(lambda r: r['issues'][0].update(issue_id='WORKER_CONGESTION'))

    def test_evidence_requires_existing_id_origin_and_verbatim_quote(self):
        self.reject_result(lambda r: r['issues'][0]['evidence'][0].update(evidence_id='unknown'))
        self.reject_result(lambda r: r['issues'][0]['evidence'][0].update(origin_item_id='post_older'))
        self.reject_result(lambda r: r['issues'][0]['evidence'][0].update(quote='Chờ 90 phút'))

    def test_keep_cannot_copy_parent_claim_or_invent_location(self):
        self.reject_result(lambda r: r['issues'][0].update(evidence=[{'evidence_id': 'ev_parent', 'origin_item_id': 'post_older', 'quote': 'VinWonders Vũ Yên'}]))
        self.reject_result(lambda r: r['issues'][0].update(location='Cổng số 99'))

    def test_missing_unreadable_target_cannot_be_keep_but_can_be_review(self):
        self.request['items'][0]['target']['text'] = None
        with self.assertRaises(ContractError): validate_response(self.response, self.request, self.snapshot)
        self.response['results'][0].update(relevance='REVIEW', issues=[], needs_review=True, review_reason='TARGET_UNREADABLE')
        self.assertTrue(validate_response(self.response, self.request, self.snapshot)['complete'])

    def test_relevance_flags_reasons_and_truncation_are_consistent(self):
        self.reject_result(lambda r: r.update(relevance='DROP', drop_reason='SALES_ONLY'))
        self.reject_result(lambda r: r.update(relevance='REVIEW'))
        self.reject_result(lambda r: r.update(review_reason='missing-context'))
        self.reject_result(lambda r: r.update(drop_reason='SALES_ONLY'))
        self.request['items'][0]['context_truncated'] = True
        with self.assertRaises(ContractError): validate_response(self.response, self.request, self.snapshot)
        self.response['results'][0].update(needs_review=True, review_reason='CONTEXT_TRUNCATED')
        self.assertTrue(validate_response(self.response, self.request, self.snapshot)['complete'])

    def test_unknown_duplicate_missing_ids_and_wrong_batch_fail_strict_mode(self):
        for mutation in ['unknown', 'duplicate', 'missing', 'batch']:
            with self.subTest(mutation=mutation):
                data = deepcopy(self.response)
                if mutation == 'unknown': data['results'][0]['item_id'] = 'not-requested'
                if mutation == 'duplicate': data['results'].append(deepcopy(data['results'][0]))
                if mutation == 'missing': data['results'] = []
                if mutation == 'batch': data['batch_id'] = 'other-batch'
                with self.assertRaises(ContractError): validate_response(data, self.request, self.snapshot)

    def test_partial_mode_keeps_valid_item_and_retries_only_invalid_or_missing(self):
        second = deepcopy(self.request['items'][0]); second['item_id'] = 'comment_002'
        self.request['items'].append(second)
        result = validate_response(self.response, self.request, self.snapshot, allow_partial=True)
        self.assertEqual(len(result['accepted']), 1)
        self.assertEqual(result['rejected'], {'comment_002': 'MISSING_RESULT'})
        invalid = deepcopy(self.response['results'][0]); invalid.update(item_id='comment_002', confidence=2)
        self.response['results'].append(invalid)
        result = validate_response(self.response, self.request, self.snapshot, allow_partial=True)
        self.assertEqual(len(result['accepted']), 1)
        self.assertEqual(result['rejected']['comment_002'], 'INVALID_RESULT_SCHEMA')

    def test_duplicate_results_never_accept_first_copy_in_partial_mode(self):
        self.response['results'].append(deepcopy(self.response['results'][0]))
        result = validate_response(self.response, self.request, self.snapshot, allow_partial=True)
        self.assertEqual(result['accepted'], [])
        self.assertEqual(result['rejected']['comment_001'], 'DUPLICATE_RESULT_ID')

    def test_invalid_json_envelope_never_partially_accepts(self):
        for data in ['{', [], {**self.response, 'extra': 'unexpected'}]:
            with self.assertRaises(ContractError): validate_response(data, self.request, self.snapshot, allow_partial=True)

    def test_many_issues_are_kept_without_duplicate_node_results(self):
        second = deepcopy(self.response['results'][0]['issues'][0])
        second['issue_id'] = 'ACCESS_DENIED'
        self.response['results'][0]['issues'].append(second)
        result = validate_response(self.response, self.request, self.snapshot)
        self.assertEqual(len(result['accepted']), 1)
        self.assertEqual(len(result['accepted'][0]['issues']), 2)

    def test_schemas_and_validator_respect_size_limits(self):
        self.reject_request(lambda d: d['items'][0]['target'].update(text='x' * 100001))
        self.reject_result(lambda r: r['issues'][0].update(summary='x' * 2001))

    def test_drop_and_unresolved_review_are_valid_business_outcomes(self):
        result = self.response['results'][0]
        result.update(relevance='DROP', issues=[], drop_reason='NO_TARGET_SIGNAL')
        self.assertTrue(validate_response(self.response, self.request, self.snapshot)['complete'])
        result.update(relevance='REVIEW', drop_reason=None, needs_review=True, review_reason='PROJECT_UNRESOLVED', project_matches=[])
        self.assertTrue(validate_response(self.response, self.request, self.snapshot)['complete'])

    def test_commercial_keep_requires_complaint_and_allows_mixed_intents(self):
        self.reject_result(lambda r:r.update(content_intents=['SALES']))
        self.response['results'][0]['content_intents']=['ADVERTISING','SALES','COMPLAINT']
        self.assertTrue(validate_response(self.response,self.request,self.snapshot)['complete'])

    def test_complaint_drop_and_unknown_intent_are_rejected(self):
        self.reject_result(lambda r:r.update(relevance='DROP',issues=[],drop_reason='commercial',content_intents=['COMPLAINT']))
        self.reject_result(lambda r:r.update(content_intents=['MADE_UP_INTENT']))


if __name__ == '__main__':
    unittest.main()
