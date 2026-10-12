"""Unified retained library: v2 raw nodes plus read-only historical v1 evidence."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from engine.content_library import library as historical_library, STATUSES
from src.acquisition.prefilter import normalize
from src.acquisition.projects import project_fields, selected_match, validate_project
from src.storage.conversations import ConversationStore


def library(database, conversation_db, filters=None, sources=None, *, paginate=True, projects=None, raw_store=None):
    filters, sources, projects = filters or {}, sources or {}, projects or {}
    validate_project(filters.get('project_id'), projects, allow_unknown=True)
    page = int(filters.get('page', 1))
    basis = filters.get('date_basis', 'collected_at')
    if page < 1 or filters.get('review','') not in STATUSES | {''} or basis not in {'collected_at','latest_collected_at','published_at'}:
        raise ValueError('Invalid library filter')
    if filters.get('node_type','') not in {'','POST','COMMENT','REPLY'}: raise ValueError('Invalid node type')
    vn = timezone(timedelta(hours=7))
    bounds = [datetime.combine(date.fromisoformat(filters[k]), datetime.min.time(), vn) if filters.get(k) else None for k in ('start_date','end_date')]
    if all(bounds) and bounds[0] > bounds[1]:
        raise ValueError('Invalid dates')
    if bounds[1]: bounds[1] += timedelta(days=1)
    old = historical_library(database, filters, sources, paginate=False, projects=projects)
    rows, v2_urls = [], set()
    all_sources, all_runs = {r['source_id'] for r in old['sources']}, set(old['runs'])
    if Path(conversation_db).exists():
        raw = raw_store or ConversationStore(conversation_db,initialize=False)
        try:
            source_map,observation_map,run_map={},{},{}
            for row in raw.db.execute('SELECT node_id,source_id FROM node_sources'):
                source_map.setdefault(row[0],[]).append(row[1])
            for row in raw.db.execute('SELECT node_id,payload,run_id FROM conversation_observations'):
                observation_map.setdefault(row[0],[]).append(json.loads(row[1]))
                run_map.setdefault(row[0],set()).add(row[2])
            review_map={r[0]:json.loads(r[1]) for r in raw.db.execute('SELECT node_id,payload FROM node_reviews')}
            for node in raw.list_nodes():
                # Even filtered-out v2 nodes supersede historical copies.
                v2_urls.add(node['display_url'])
                if filters.get('node_type') and node['node_type']!=filters['node_type']: continue
                if filters.get('quality') and node['extraction_status']!=filters['quality']:continue
                ids = source_map.get(node['node_id'],[])
                obs = observation_map.get(node['node_id'],[])
                runs = sorted(run_map.get(node['node_id'],set()))
                all_sources.update(ids); all_runs.update(runs)
                sid = filters.get('query_id') or filters.get('source_id') or next(iter(ids), '')
                if sid not in ids or filters.get('platform') and filters['platform'] != node['platform'].lower(): continue
                review = review_map.get(node['node_id'],dict(status='UNREVIEWED',note='',updated_at=None))
                fields = project_fields(dict(raw_text=node['raw_text'],context_source_id=sid),projects)
                query_projects={o['project_scope_id'] for o in obs if node['platform']=='THREADS' and o.get('source_id')==sid and o.get('project_scope_id') in projects}
                if query_projects:
                    fields['project_context_ids']=sorted(set(fields['project_context_ids'])|query_projects)
                    if not fields.get('project'):fields['project']=', '.join(projects[p]['name'] for p in sorted(query_projects))+' (theo truy vấn)'
                if not selected_match(fields,filters.get('project_id')): continue
                if filters.get('review') and review['status'] != filters['review']: continue
                if filters.get('run_id') and filters['run_id'] not in runs: continue
                group = sources.get(sid,{}).get('name',sid)
                from src.storage.image_evidence import bindings
                ocr_text='\n'.join(e['text'] for e in bindings(raw,node['node_id']))
                if filters.get('keyword') and normalize(filters['keyword']) not in normalize((node['raw_text'] or '')+' '+ocr_text+' '+group): continue
                if any(bounds):
                    if basis=='published_at' and node['publication_precision']!='INSTANT': continue
                    values = [node['published_at']] if basis=='published_at' else [node['last_seen_at']] if basis=='latest_collected_at' else [o.get('observed_at') for o in obs]
                    def inside(value):
                        if not value: return False
                        stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
                        return (not bounds[0] or stamp>=bounds[0]) and (not bounds[1] or stamp<bounds[1])
                    if not any(inside(value) for value in values): continue
                rows.append(dict(record_id='v2:'+node['node_id'],url=node['display_url'],platform=node['platform'].lower(),
                    group=group,group_url=sources.get(sid,{}).get('url'),source_id=sid,title=node['node_type'],
                    node_type=node['node_type'],root_post_id=node['root_post_id'],parent_node_id=node['parent_node_id'],
                    author_uid=node['author_uid'],author_name=node['author_name'],
                    text=node['raw_text'],published_at=node['published_at'],publication_precision=node['publication_precision'],
                    collected_at=node['last_seen_at'],extraction_status=node['extraction_status'],
                    missing_data_reasons=node['missing_fields'],observation_count=len(obs),run_ids=runs,review=review,**fields))
        finally:
            if raw_store is None:raw.close()
    if filters.get('node_type','') in {'','POST'}:
        rows += [dict(r,node_type='POST',pipeline='HISTORICAL_V1') for r in old['rows'] if r['url'] not in v2_urls]
    rows.sort(key=lambda r:r['collected_at'] or '',reverse=True)
    page=min(page,max(1,(len(rows)+19)//20))
    return dict(rows=rows[(page-1)*20:page*20] if paginate else rows,total=len(rows),page=page,page_size=20,
        sources=[dict(source_id=s,name=sources.get(s,{}).get('name',s)) for s in sorted(all_sources)],runs=sorted(all_runs,reverse=True))
