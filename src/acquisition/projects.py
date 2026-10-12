"""Evidence-based project labels, independent of crawl query and group context."""
from pathlib import Path
import re
import yaml
from src.acquisition.prefilter import normalize


def load_projects(config_dir):
    path = Path(config_dir) / 'projects.yaml'
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema_version') != 'project-registry-v1':
        raise ValueError('Cấu hình dự án không hợp lệ.')
    projects = {}
    for p in data.get('projects', []):
        if not isinstance(p, dict) or not isinstance(p.get('project_id'), str) or not p['project_id'] or p['project_id'] in projects:
            raise ValueError('ID dự án thiếu hoặc trùng.')
        if not isinstance(p.get('name'), str) or not p['name'].strip() or type(p.get('enabled')) is not bool:
            raise ValueError('Tên/trạng thái dự án không hợp lệ.')
        for key in ('aliases', 'hashtags', 'discovery_terms', 'source_ids'):
            if not isinstance(p.get(key), list) or any(not isinstance(v, str) or not v.strip() for v in p[key]):
                raise ValueError('Danh mục dự án không hợp lệ: ' + key)
        projects[p['project_id']] = p
    return projects


def validate_project(project_id, projects, allow_unknown=False):
    if project_id == '__unknown__' and allow_unknown:
        return None
    if not project_id:
        return None
    if not isinstance(project_id, str) or project_id not in projects or not projects[project_id]['enabled']:
        raise ValueError('Dự án không tồn tại hoặc đang tắt.')
    return projects[project_id]


def match_projects(item, projects):
    # Source names, query terms and Google snippets may refer to a different
    # post. Use only the target item's title/caption/raw text as evidence.
    text = normalize(' '.join(item.get(k) or '' for k in ('title', 'caption', 'raw_text')))
    tags = {normalize(t.lstrip('#')) for t in item.get('hashtags', [])}
    matches = []
    for p in projects.values():
        if not p['enabled']:
            continue
        aliases = [a for a in p['aliases'] if re.search(r'(?<!\w)' + re.escape(normalize(a)) + r'(?!\w)', text)]
        aliases += [tag for tag in p['hashtags'] if normalize(tag.lstrip('#')) in tags or re.search(r'(?<!\w)' + re.escape(normalize(tag)) + r'(?!\w)', text)]
        if aliases:
            matches.append(dict(project_id=p['project_id'], name=p['name'], matched_aliases=aliases))
    # An alias shared between projects cannot resolve identity by itself.
    shared = {normalize(a) for m in matches for a in m['matched_aliases']
              if sum(normalize(a) in {normalize(x) for x in other['matched_aliases']} for other in matches) > 1}
    return [m for m in matches if any(normalize(a) not in shared for a in m['matched_aliases'])]


def project_fields(item, projects):
    matches = match_projects(item, projects)
    context = [p for p in projects.values() if p['enabled'] and (item.get('context_source_id') or item.get('source_id')) in p['source_ids']]
    return dict(project_ids=[m['project_id'] for m in matches], projects=matches,
                project_context_ids=[p['project_id'] for p in context],
                project='; '.join(m['name'] for m in matches) or ('; '.join(p['name'] for p in context) + ' (theo group, chưa xác nhận)' if context else None),
                project_match_status='MATCHED' if matches else 'CONTEXT_ONLY' if context else 'UNRESOLVED')


def selected_match(fields, selected):
    return not selected or (not fields['project_ids'] if selected == '__unknown__' else selected in fields['project_ids'] or (not fields['project_ids'] and selected in fields.get('project_context_ids', [])))
