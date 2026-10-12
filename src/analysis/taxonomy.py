"""Offline taxonomy snapshot validation; does not activate classification."""
from pathlib import Path
import re
import yaml


class TaxonomyError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise TaxonomyError('Invalid or duplicate YAML key')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_yaml(path):
    try:
        data = yaml.load(Path(path).read_text(encoding='utf-8'), Loader=_UniqueLoader)
    except (yaml.YAMLError, OSError) as exc:
        raise TaxonomyError('Cannot read taxonomy YAML') from exc
    if not isinstance(data, dict):
        raise TaxonomyError('Expected YAML object')
    return data


LEGACY = {
    'SITE_ACCESS_CONGESTION': {'ENTRY_QUEUE', 'EXIT_QUEUE', 'VEHICLE_CONGESTION',
        'WORKER_CONGESTION', 'CHECKIN_BOTTLENECK', 'ACCESS_CONTROL_FAILURE', 'EXTERNAL_TRAFFIC_IMPACT'},
    'CUSTOMER_COMPLAINT': {'SERVICE_DELAY', 'NO_RESPONSE', 'APP_SYSTEM_ISSUE',
        'STAFF_ATTITUDE', 'UNRESOLVED_ISSUE', 'OTHER_COMPLAINT'},
    'OTHER_RELEVANT': {None},
}


def _strings(values, label):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
        raise TaxonomyError('Missing or invalid ' + label)


def _header(data):
    if data.get('schema_version') != 'project-issue-taxonomy-v1':
        raise TaxonomyError('Unsupported taxonomy schema')
    if not isinstance(data.get('taxonomy_version'), str) or not data['taxonomy_version'].strip():
        raise TaxonomyError('Missing taxonomy version')
    if data.get('status') not in {'DRAFT', 'APPROVED', 'DEPRECATED'} or type(data.get('runtime_enabled')) is not bool:
        raise TaxonomyError('Invalid approval or runtime flag')


def validate_catalog(data):
    _header(data)
    issues = data.get('issues')
    if not isinstance(issues, list) or not issues:
        raise TaxonomyError('Empty issue catalog')
    index = {}
    for issue in issues:
        if not isinstance(issue, dict):
            raise TaxonomyError('Issue must be an object')
        identifier = issue.get('issue_id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]+', identifier) or identifier in index:
            raise TaxonomyError('Invalid or duplicate issue ID')
        for key in ('name', 'definition'):
            if not isinstance(issue.get(key), str) or not issue[key].strip():
                raise TaxonomyError('Missing ' + key)
        for key in ('include_examples', 'exclude_examples', 'required_evidence'):
            _strings(issue.get(key), key)
        domain = issue.get('legacy_domain')
        if domain not in LEGACY or issue.get('family_id') != domain or 'legacy_subcategory' not in issue:
            raise TaxonomyError('Invalid domain mapping')
        policy = issue.get('legacy_projection_policy')
        sub = issue['legacy_subcategory']
        if policy == 'DIRECT':
            if sub not in LEGACY[domain]:
                raise TaxonomyError('Invalid legacy subcategory')
        elif policy != 'REVIEW_REQUIRE_SUBCATEGORY' or domain != 'SITE_ACCESS_CONGESTION' or sub is not None:
            raise TaxonomyError('Invalid unresolved legacy mapping')
        index[identifier] = issue
    return index


def validate_profile(profile, catalog, source_ids=None):
    _header(profile)
    if profile['taxonomy_version'] != catalog['taxonomy_version']:
        raise TaxonomyError('Profile version differs from catalog')
    if not isinstance(profile.get('project_id'), str) or not profile['project_id'].strip():
        raise TaxonomyError('Missing project ID')
    _strings(profile.get('source_ids'), 'source IDs')
    if len(set(profile['source_ids'])) != len(profile['source_ids']):
        raise TaxonomyError('Duplicate source ID')
    if source_ids is not None and not set(profile['source_ids']) <= set(source_ids):
        raise TaxonomyError('Unknown registry source')
    priorities = profile.get('issue_priorities')
    disabled = profile.get('not_enabled_issue_ids')
    if not isinstance(priorities, dict) or not priorities or not isinstance(disabled, list) or any(not isinstance(i, str) for i in disabled):
        raise TaxonomyError('Invalid issue selection')
    if any(v not in {'P0', 'P1', 'P2'} for v in priorities.values()):
        raise TaxonomyError('Invalid priority')
    index = validate_catalog(catalog)
    if len(disabled) != len(set(disabled)) or set(priorities) & set(disabled) or set(priorities) | set(disabled) != set(index):
        raise TaxonomyError('Unknown, overlapping or missing issue selection')
    return profile


def load_snapshot(directory, source_ids=None):
    """Read a review snapshot. Caller must explicitly pass the runtime gate."""
    directory = Path(directory).resolve()
    catalog = read_yaml(directory / 'common.yaml')
    validate_catalog(catalog)
    profiles = {}
    for path in sorted(directory.glob('*.yaml')):
        if path.name == 'common.yaml':
            continue
        profile = read_yaml(path)
        ref = profile.get('common_catalog')
        if not isinstance(ref, str) or (directory / ref).resolve() != directory / 'common.yaml':
            raise TaxonomyError('Profile must reference the local catalog')
        validate_profile(profile, catalog, source_ids)
        identifier = profile['project_id']
        if identifier in profiles:
            raise TaxonomyError('Duplicate project ID')
        profiles[identifier] = profile
    if not profiles:
        raise TaxonomyError('No project profiles')
    return {'catalog': catalog, 'profiles': profiles}


def require_runtime_ready(snapshot):
    for document in [snapshot['catalog'], *snapshot['profiles'].values()]:
        if document['status'] != 'APPROVED' or document['runtime_enabled'] is not True:
            raise TaxonomyError('Taxonomy is not approved and enabled for runtime')
