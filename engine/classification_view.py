"""Validated, paginated filters for the saved classification view."""
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from src.acquisition.prefilter import normalize


def query_rows(rows,filters,*,paginate=True):
    page=int(filters.get('page',1));size=int(filters.get('page_size',25))
    if page<1 or not 1<=size<=100: raise ValueError('Invalid pagination')
    relevance=filters.get('relevance','');kind=filters.get('node_type','');precision=filters.get('time_status','')
    if relevance not in {'','KEEP','DROP','REVIEW','UNCLASSIFIED'} or kind not in {'','POST','COMMENT','REPLY'} or precision not in {'','INSTANT','UNKNOWN'}:
        raise ValueError('Invalid classification filter')
    basis=filters.get('date_basis','published_at')
    if basis not in {'published_at','collected_at'}: raise ValueError('Invalid date basis')
    vn=timezone(timedelta(hours=7))
    start=datetime.combine(date.fromisoformat(filters['start_date']),datetime.min.time(),vn) if filters.get('start_date') else None
    end=datetime.combine(date.fromisoformat(filters['end_date'])+timedelta(days=1),datetime.min.time(),vn) if filters.get('end_date') else None
    if start and end and start>=end: raise ValueError('Invalid dates')
    filtered=[]
    for row in rows:
        if filters.get('platform') and row.get('platform','facebook')!=filters['platform']:continue
        if filters.get('query_id') and filters['query_id'] not in row['source_ids']:continue
        analysis=row.get('analysis') or {}
        intents=analysis.get('content_intents') or (row.get('filter_decision',{}).get('content_intents',[])
            if row['processing_status']=='FILTER_DROP' else [])
        projects=analysis.get('project_matches',[])
        if kind and row['node_type']!=kind: continue
        if filters.get('source_id') and filters['source_id'] not in row['source_ids']: continue
        project=filters.get('project_id','')
        if project=='__unknown__' and projects or project and project!='__unknown__' and not any(p['project_id']==project for p in projects): continue
        if filters.get('issue_id') and not any(i['issue_id']==filters['issue_id'] for i in analysis.get('issues',[])): continue
        if filters.get('intent') and filters['intent'] not in intents: continue
        if filters.get('processing_status') and row['processing_status']!=filters['processing_status']: continue
        if precision=='INSTANT' and row['publication_precision']!='INSTANT' or precision=='UNKNOWN' and row['publication_precision']=='INSTANT': continue
        if filters.get('keyword') and normalize(filters['keyword']) not in normalize((row.get('raw_text') or '')+' '+(row.get('ocr_text') or '')): continue
        if start or end:
            stamp=row.get(basis)
            if not stamp or basis=='published_at' and row['publication_precision']!='INSTANT': continue
            value=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if start and value<start or end and value>=end: continue
        filtered.append(row)
    def state(row): return (row.get('analysis') or {}).get('relevance') or ('DROP' if row['processing_status']=='FILTER_DROP' else 'UNCLASSIFIED')
    summary=dict(Counter(state(r) for r in filtered))
    filtered=[r for r in filtered if not relevance or state(r)==relevance]
    filtered.sort(key=lambda r:(bool(r.get(basis)),r.get(basis) or '',r.get('collected_at') or '',r['node_id']),reverse=True)
    total=len(filtered);page=min(page,max(1,(total+size-1)//size))
    return dict(rows=filtered[(page-1)*size:page*size] if paginate else filtered,total=total,page=page,page_size=size,summary=summary)
