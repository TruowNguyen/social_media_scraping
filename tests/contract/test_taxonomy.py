from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from src.analysis.taxonomy import (load_snapshot, read_yaml, validate_catalog,
    validate_profile, require_runtime_ready, TaxonomyError)
from src.analysis.taxonomy_fixtures import validate_fixture_set


ROOT = Path(__file__).resolve().parents[2]


class TaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.sources = {s['source_id'] for s in read_yaml(ROOT / 'config/sources.yaml')['sources']}
        self.snapshot = load_snapshot(ROOT / 'specs/taxonomy/v1', self.sources)
        self.fixtures = read_yaml(ROOT / 'tests/fixtures/taxonomy_v1/golden.yaml')

    def test_snapshot_and_development_labels_are_consistent_not_predictions(self):
        self.assertEqual(len(self.snapshot['catalog']['issues']), 17)
        summary = validate_fixture_set(self.fixtures, self.snapshot)
        self.assertEqual(summary['case_count'], 26)
        self.assertEqual(summary['project_counts'], {'vincons': 10, 'vinwonders_vu_yen': 16})

    def test_duplicate_yaml_keys_fail_instead_of_silent_override(self):
        with patch.object(Path, 'read_text', return_value='status: DRAFT\nstatus: APPROVED\n'):
            with self.assertRaises(TaxonomyError): read_yaml('bad.yaml')

    def test_catalog_rejects_invalid_definition_identity_and_legacy_mapping(self):
        for mutation in ['duplicate', 'empty', 'subcategory', 'missing_evidence', 'unknown_policy']:
            with self.subTest(mutation=mutation):
                data = deepcopy(self.snapshot['catalog'])
                if mutation == 'duplicate': data['issues'].append(deepcopy(data['issues'][0]))
                if mutation == 'empty': data['issues'][0]['definition'] = ''
                if mutation == 'subcategory': data['issues'][0]['legacy_subcategory'] = 'ENTRY_QUUE'
                if mutation == 'missing_evidence': data['issues'][0]['required_evidence'] = []
                if mutation == 'unknown_policy': data['issues'][0]['legacy_projection_policy'] = 'GUESS'
                with self.assertRaises(TaxonomyError): validate_catalog(data)

    def test_profiles_reject_unknown_sources_issues_priorities_and_versions(self):
        for mutation in ['source', 'issue', 'priority', 'version', 'overlap']:
            with self.subTest(mutation=mutation):
                data = deepcopy(self.snapshot['profiles']['vincons'])
                if mutation == 'source': data['source_ids'].append('not_registered')
                if mutation == 'issue': data['issue_priorities']['NONEXISTENT'] = 'P0'
                if mutation == 'priority': data['issue_priorities']['ENTRY_QUEUE'] = 'P999'
                if mutation == 'version': data['taxonomy_version'] = 'other'
                if mutation == 'overlap': data['not_enabled_issue_ids'].append('ENTRY_QUEUE')
                with self.assertRaises(TaxonomyError): validate_profile(data, self.snapshot['catalog'], self.sources)

    def test_draft_user_acceptance_does_not_bypass_runtime_gate(self):
        with self.assertRaises(TaxonomyError): require_runtime_ready(self.snapshot)
        data = deepcopy(self.snapshot)
        for document in [data['catalog'], *data['profiles'].values()]: document['status'] = 'APPROVED'
        with self.assertRaises(TaxonomyError): require_runtime_ready(data)
        for document in [data['catalog'], *data['profiles'].values()]: document['runtime_enabled'] = True
        require_runtime_ready(data)

    def test_case_evidence_and_expected_labels_reject_fabricated_or_disabled_values(self):
        for mutation in ['quote', 'origin', 'disabled', 'forbidden', 'empty_target', 'missing_time']:
            with self.subTest(mutation=mutation):
                data = deepcopy(self.fixtures)
                case = data['cases'][0]
                if mutation == 'quote': case['expected']['evidence'][0]['quote'] = 'not actually said'
                if mutation == 'origin': case['expected']['evidence'][0]['origin_item_id'] = 'unknown'
                if mutation == 'disabled': case['expected']['issue_ids'] = ['REFUND_DISPUTE']
                if mutation == 'forbidden': case['expected']['forbidden_issue_ids'] = ['ENTRY_QUEUE']
                if mutation == 'empty_target': case['target']['text'] = None
                if mutation == 'missing_time': case['expected']['window_status'] = 'IN_WINDOW'
                with self.assertRaises(TaxonomyError): validate_fixture_set(data, self.snapshot)

    def test_golden_claims_cannot_pretend_to_be_human_held_out_data(self):
        data = deepcopy(self.fixtures)
        data['human_label_status'] = 'APPROVED'
        with self.assertRaises(TaxonomyError): validate_fixture_set(data, self.snapshot)

    def test_old_parent_does_not_define_target_date_in_window_fixture(self):
        case = deepcopy(next(c for c in self.fixtures['cases'] if c['case_id'] == 'VC-10'))
        data = deepcopy(self.fixtures)
        data['cases'] = [case]
        self.assertEqual(validate_fixture_set(data, self.snapshot)['case_count'], 1)
        case['target']['published_at'] = '2026-10-08T17:00:00Z'
        with self.assertRaises(TaxonomyError): validate_fixture_set(data, self.snapshot)


if __name__ == '__main__':
    unittest.main()
