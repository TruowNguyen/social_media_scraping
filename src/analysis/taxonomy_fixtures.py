"""Validate development labels and evidence; never predict classification."""
from collections import Counter
from datetime import datetime
from src.analysis.taxonomy import TaxonomyError, read_yaml


def validate_fixture_set(document, snapshot):
    if document.get('schema_version') != 'taxonomy-golden-v1' or document.get('taxonomy_version') != snapshot['catalog']['taxonomy_version']:
        raise TaxonomyError('Fixture schema/version mismatch')
    if document.get('provenance') != 'SYNTHETIC_DEVELOPMENT_CASES' or document.get('human_label_status') != 'PENDING_REVIEW':
        raise TaxonomyError('Development examples must not claim human/live validation')
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases:
        raise TaxonomyError('Missing fixture cases')
    try:
        window = document['evaluation_window']
        window_start = datetime.fromisoformat(window['start'].replace('Z', '+00:00'))
        window_end = datetime.fromisoformat(window['end'].replace('Z', '+00:00'))
        if window_start.tzinfo is None or window_end.tzinfo is None or window_end <= window_start:
            raise ValueError('Invalid window')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise TaxonomyError('Invalid fixture evaluation window') from exc
    case_ids, target_ids = set(), set()
    relevance_counts, project_counts = Counter(), Counter()
    for case in cases:
        if not isinstance(case, dict):
            raise TaxonomyError('Case must be an object')
        identifier = case.get('case_id')
        if not isinstance(identifier, str) or not identifier or identifier in case_ids:
            raise TaxonomyError('Missing or duplicate case ID')
        case_ids.add(identifier)
        project = case.get('project_id')
        if project not in snapshot['profiles']:
            raise TaxonomyError('Unknown fixture project')
        target, context, expected = case.get('target'), case.get('context'), case.get('expected')
        if not isinstance(target, dict) or not isinstance(context, list) or not isinstance(expected, dict):
            raise TaxonomyError('Invalid target/context/expected')
        item_id = target.get('item_id')
        if not isinstance(item_id, str) or not item_id or item_id in target_ids:
            raise TaxonomyError('Missing or duplicate target ID')
        target_ids.add(item_id)
        if target.get('node_type') not in {'POST', 'COMMENT', 'REPLY'}:
            raise TaxonomyError('Unknown node type')
        if 'text' not in target or (target['text'] is not None and not isinstance(target['text'], str)):
            raise TaxonomyError('Invalid target text')
        origins = {item_id: target.get('text')}
        for parent in context:
            if not isinstance(parent, dict) or parent.get('role') not in {'ROOT_POST', 'PARENT_COMMENT'}:
                raise TaxonomyError('Invalid context role')
            parent_id = parent.get('item_id')
            if not isinstance(parent_id, str) or not parent_id or parent_id in origins or not isinstance(parent.get('text'), str):
                raise TaxonomyError('Invalid/duplicate context evidence ID')
            origins[parent_id] = parent['text']
        rel = expected.get('relevance')
        if rel not in {'KEEP', 'DROP', 'REVIEW'}:
            raise TaxonomyError('Invalid expected relevance')
        issue_ids = expected.get('issue_ids')
        forbidden = expected.get('forbidden_issue_ids', [])
        enabled = snapshot['profiles'][project]['issue_priorities']
        if not isinstance(issue_ids, list) or any(not isinstance(i, str) for i in issue_ids) or len(issue_ids) != len(set(issue_ids)) or not set(issue_ids) <= set(enabled):
            raise TaxonomyError('Invalid or disabled expected issue')
        catalog_ids = {i['issue_id'] for i in snapshot['catalog']['issues']}
        if not isinstance(forbidden, list) or any(not isinstance(i, str) for i in forbidden) or not set(forbidden) <= catalog_ids or set(forbidden) & set(issue_ids):
            raise TaxonomyError('Invalid or contradictory forbidden issues')
        if expected.get('project_basis') not in {'CONTENT_EXPLICIT', 'GROUP_CONTEXT', 'PARENT_CONTEXT', 'UNRESOLVED'}:
            raise TaxonomyError('Invalid project basis')
        if expected['project_basis'] == 'PARENT_CONTEXT' and not context:
            raise TaxonomyError('Parent basis without context')
        evidence = expected.get('evidence')
        if not isinstance(evidence, list):
            raise TaxonomyError('Invalid evidence list')
        if rel == 'KEEP' and (not issue_ids or not evidence or not target.get('text')):
            raise TaxonomyError('KEEP requires target and issue evidence')
        if rel == 'DROP' and (issue_ids or not expected.get('drop_reason')):
            raise TaxonomyError('DROP requires reason and no issues')
        if rel == 'REVIEW' and not expected.get('review_reason'):
            raise TaxonomyError('REVIEW requires reason')
        for entry in evidence:
            if not isinstance(entry, dict):
                raise TaxonomyError('Invalid evidence entry')
            quote, origin = entry.get('quote'), origins.get(entry.get('origin_item_id'))
            if not isinstance(quote, str) or not quote or not isinstance(origin, str) or quote not in origin:
                raise TaxonomyError('Evidence quote is not present in its origin')
        if expected.get('window_status') not in {None, 'IN_WINDOW', 'OUT_OF_WINDOW', 'UNRESOLVED', 'DAY_MATCH_ONLY', 'UNCERTAIN'}:
            raise TaxonomyError('Invalid expected window state')
        if expected.get('window_status') == 'IN_WINDOW':
            timestamp = target.get('published_at')
            if target.get('publication_precision') != 'INSTANT' or not isinstance(timestamp, str):
                raise TaxonomyError('Confirmed window requires instant timestamp')
            try:
                instant = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError as exc:
                raise TaxonomyError('Invalid publication timestamp') from exc
            if instant.tzinfo is None or not window_start <= instant < window_end:
                raise TaxonomyError('Fixture evaluation window does not contain target')
        relevance_counts[rel] += 1
        project_counts[project] += 1
    return {'case_count': len(cases), 'relevance_counts': dict(relevance_counts), 'project_counts': dict(project_counts)}


def load_fixture_set(path, snapshot):
    data = read_yaml(path)
    return data, validate_fixture_set(data, snapshot)
