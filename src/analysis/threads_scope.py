"""Threads query attribution is a discovery hint, never entity evidence.

Missing entity evidence defers expensive conversation scans; it does not delete
raw content or declare it irrelevant. Issue terms are deliberately not required:
an initially neutral post can receive a relevant new comment later.
"""
from src.acquisition.projects import match_projects

SCOPE_VERSION = 'threads-entity-scope-v1'


def evaluate_scope(item, project_id, projects, *, evidence=()):
    texts = [item.get('raw_text') or item.get('text') or '']
    texts.extend(e.get('text') or '' for e in evidence)
    matches = match_projects({'raw_text': '\n'.join(texts)}, projects)
    aliases = next((m['matched_aliases'] for m in matches if m['project_id'] == project_id), [])
    if aliases:
        status = 'MATCHED'
    elif not texts[0].strip() or item.get('media_refs'):
        status = 'MISSING_EVIDENCE'
    else:
        status = 'NO_TARGET_EVIDENCE'
    return dict(version=SCOPE_VERSION, project_id=project_id, status=status,
                matched_aliases=aliases, conversation_eligible=status != 'NO_TARGET_EVIDENCE')
