"""Review taxonomy and synthetic development cases without network or DB writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from src.analysis.taxonomy import load_snapshot, read_yaml, TaxonomyError
from src.analysis.taxonomy_fixtures import load_fixture_set


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline taxonomy review checks; does not classify content.')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'specs/taxonomy/v1')
    parser.add_argument('--sources', type=Path, default=ROOT / 'config/sources.yaml')
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'tests/fixtures/taxonomy_v1/golden.yaml')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        sources = {s['source_id'] for s in read_yaml(args.sources)['sources']}
        snapshot = load_snapshot(args.snapshot, sources)
        _, fixture_summary = load_fixture_set(args.fixtures, snapshot)
    except (TaxonomyError, KeyError, TypeError) as exc:
        parser.exit(1, 'Taxonomy validation failed: ' + str(exc) + '\n')
    report = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'OFFLINE_TAXONOMY_AND_SYNTHETIC_FIXTURE_CONTRACTS',
        'taxonomy_version': snapshot['catalog']['taxonomy_version'],
        'issue_count': len(snapshot['catalog']['issues']),
        'profiles': {k: {'enabled_issue_count': len(v['issue_priorities']), 'source_count': len(v['source_ids'])} for k, v in snapshot['profiles'].items()},
        'fixture_summary': fixture_summary,
        'runtime_enabled': False, 'live_tested': False, 'classification_accuracy_measured': False,
        'human_labels_approved': False, 'p0_complete': False,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding='utf-8')
    print(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
