"""Threads read-only acquisition. Public DOM/API evidence, bounded pages, no hidden APIs."""
import hashlib
import re
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import requests
from src.acquisition.browser import navigate,page_failure
from src.acquisition.identity import identify
from src.acquisition.models import AdapterError,parse_utc
from src.domain.conversation import ContentNode

PARSER_VERSION='threads-dom-v5'
READ_DOM=r'''() => {
 const out=[],seen=new Set();
 for(const t of document.querySelectorAll('a[href*="/post/"] time')){
  const a=t.closest('a'), href=a.getAttribute('href');
  if(!/^\/@[^/]+\/post\/[A-Za-z0-9_-]+$/.test(href)||seen.has(href))continue;
  const row=a.closest('[data-pressable-container]');if(!row||!row.getClientRects().length)continue;
  seen.add(href);
  const own=e=>e.closest('[data-pressable-container]')===row;
  const actions=Array.from(row.querySelectorAll('[role="button"],button')).filter(own);
  const footer=actions.find(e=>/^(like|unlike|thích|bỏ thích|reply|trả lời)(?:\s|$)/i.test(e.getAttribute('aria-label')||e.querySelector('svg title')?.textContent||''));
  const spans=Array.from(row.querySelectorAll('[dir="auto"]')).filter(e=>own(e)&&!e.closest('a,button,[role="button"],time,[role="textbox"],[contenteditable="true"]')&&!e.querySelector('[dir="auto"],time')&&(!footer||Boolean(e.compareDocumentPosition(footer)&Node.DOCUMENT_POSITION_FOLLOWING)));
  const text=spans.map(e=>{
    const copy=e.cloneNode(true);
    copy.querySelectorAll('button,[role="button"],[role="textbox"],[contenteditable="true"]').forEach(n=>n.remove());
    copy.querySelectorAll('br').forEach(n=>n.replaceWith(document.createTextNode('\n')));
    return copy.textContent.trim();
  }).filter(Boolean).join('\n');
  const buttons=Array.from(row.querySelectorAll('[role="button"],button')).filter(own).map(e=>({
    label:e.getAttribute('aria-label')||e.querySelector('svg title')?.textContent||'',text:e.innerText}));
  const images=Array.from(row.querySelectorAll('img')).filter(e=>own(e)&&!/avatar|profile|đại diện/i.test(e.alt||'')).map(e=>({url:e.currentSrc||e.src,alt_text:e.alt||null,kind:'IMAGE'}));
  out.push({url:new URL(href,location.origin).href,shortcode:href.split('/').pop(),pagelet:row.closest('[data-pagelet]')?.getAttribute('data-pagelet')||null,
    username:href.split('/')[1].slice(1),text:text||null,timestamp:t.getAttribute('datetime'),
    timestamp_raw:t.innerText,buttons,media_refs:images});
 }
 return out;
}'''


def node_key(item):
    identity='native:'+str(item['id']) if item.get('id') else 'url:'+identify(item['url']).url
    return 'threads_'+hashlib.sha256(identity.encode()).hexdigest()


def node_from_item(item, *, root=None, parent=None, relationship='RESOLVED', node_type='POST'):
    stamp=item.get('timestamp');missing=[]
    try:stamp=parse_utc(stamp).isoformat() if stamp else None
    except (ValueError,TypeError):stamp=None
    if not stamp:missing.append('UNRESOLVED_TIMESTAMP')
    if not item.get('text'):missing.append('MISSING_TEXT')
    if relationship!='RESOLVED':missing.append('UNVERIFIED_NODE_TYPE' if node_type=='POST' else 'UNRESOLVED_PARENT')
    engagement=dict(item.get('engagement') or {})
    for button in item.get('buttons',[]):
        label=button['label'].casefold();value=button['text'].strip().replace(',','').replace('.','')
        metric=next((k for k,labels in {'likes':('thích','like'),'comments':('trả lời','reply'),'shares':('chia sẻ','share')}.items() if any(x in label for x in labels)),None)
        if metric:engagement[metric]=int(value) if re.fullmatch(r'\d+',value) else None
    return ContentNode(node_type,node_id=node_key(item),platform='THREADS',schema_version='conversation-record-v3',
        platform_item_id=str(item['id']) if item.get('id') else None,canonical_url=item.get('url'),
        platform_shortcode=item.get('shortcode'),author_name=item.get('username'),author_uid=item.get('owner'),
        author_url=('https://threads.com/@'+item['username']) if item.get('username') else None,
        raw_text=item.get('text'),published_at=stamp,publication_precision='INSTANT' if stamp else 'UNKNOWN',
        timestamp_raw=item.get('timestamp_raw'),timestamp_basis=item.get('timestamp_basis','PLATFORM_DATETIME'),
        root_post_id=root,parent_node_id=parent,relationship_status=relationship,
        media_refs=item.get('media_refs',[]),engagement=engagement,
        platform_topic_tags=item.get('topic_tags',[]),link_relations=item.get('link_relations',[]),
        extraction_status='PARTIAL' if missing else 'COMPLETE',missing_fields=missing)


class ThreadsBrowserAdapter:
    method='THREADS_BROWSER'
    def __init__(self,page,deadline):self.page,self.deadline=page,deadline

    def _read(self):
        failure=page_failure(self.page)
        if failure:raise AdapterError(*failure)
        return self.page.evaluate(READ_DOM)

    def _await_rows(self):
        try:self.page.locator('a[href*="/post/"] time').first.wait_for(timeout=self.deadline.milliseconds(15000))
        except Exception:
            failure=page_failure(self.page)
            if failure:raise AdapterError(*failure) from None
            if self.page.get_by_text(re.compile(r'^(No results|Không có kết quả|No results found)',re.I)).count():return []
            auth=self.page.get_by_text(re.compile(r'^(Continue with Instagram|Log in or sign up for Threads|Tiếp tục với Instagram|Đăng nhập hoặc đăng ký)',re.I))
            if any(auth.nth(i).is_visible() for i in range(auth.count())):raise AdapterError('AUTH_REQUIRED','LOGIN_REQUIRED') from None
            raise AdapterError('EXTRACTION_FAILED','SEARCH_SELECTOR_MISMATCH') from None
        # Timestamp anchors arrive before the hydrated, pressable post cards.
        # Wait for card extraction, not merely an anchor in the initial HTML.
        until=time.monotonic()+min(10,self.deadline.remaining())
        rows=self._read()
        while not rows and time.monotonic()<until:
            self.page.wait_for_timeout(self.deadline.milliseconds(250));rows=self._read()
        if not rows:raise AdapterError('EXTRACTION_FAILED','THREADS_ROW_SELECTOR_MISMATCH')
        return rows

    def probe_access(self,source):
        navigate(self.page,'https://www.threads.com/search?'+urlencode({'q':source['query'],'serp_type':'default','filter':'recent'}),self.deadline)
        self._await_rows();rows=self._search_rows(source['query'])
        return {'search_recent':'SUPPORTED','public_replies':'UNVERIFIED','observed_order':'RECENT_UI','candidates':len(rows),
                'query_verified':True,'parser_version':PARSER_VERSION}

    def _search_rows(self,query):
        target=urlsplit(self.page.url)
        if target.hostname not in {'threads.com','www.threads.com'} or target.path.rstrip('/')!='/search' or parse_qs(target.query).get('q')!=[query]:
            raise AdapterError('EXTRACTION_FAILED','SEARCH_QUERY_MISMATCH')
        values=self.page.evaluate('''() => [...document.querySelectorAll('input')]
            .filter(e=>e.getClientRects().length).map(e=>e.value)''')
        if query not in values:raise AdapterError('EXTRACTION_FAILED','SEARCH_QUERY_UNVERIFIED')
        rows=self._read()
        scoped=[r for r in rows if (r.get('pagelet') or '').startswith('threads_search_results_')]
        if rows and not scoped:raise AdapterError('EXTRACTION_FAILED','SEARCH_RESULTS_SELECTOR_MISMATCH')
        return scoped

    def _scroll(self):
        # Depending on the layout the scroll owner is the column or the document.
        # The data-column-scrollable wrapper itself can have no scroll range.
        self.page.locator('a[href*="/post/"] time').first.evaluate('''(el) => {
            for(let p=el.parentElement;p;p=p.parentElement){
                const style=getComputedStyle(p);
                if(p.scrollHeight>p.clientHeight+10 && /auto|scroll/.test(style.overflowY)){
                    p.scrollBy(0,1400);return;
                }
            }
            window.scrollBy(0,1400);
        }''')

    def discover(self,request):
        navigate(self.page,'https://www.threads.com/search?'+urlencode({'q':request['query'],'serp_type':'default','filter':'recent'}),self.deadline)
        seen=set();pages=request.get('max_pages',5)
        for index in range(pages):
            if index==0:self._await_rows()
            rows=self._search_rows(request['query'])
            fresh=[item for item in rows if item['url'] not in seen]
            seen.update(item['url'] for item in fresh)
            yield {'items':fresh,'page':index,'observed_order':'RECENT_UI',
                'empty_verified':not rows and index==0,'exhausted':False,'method':self.method,
                'query_verified':True,'parser_version':PARSER_VERSION}
            if not fresh:return
            self.deadline.check();self._scroll()
            self.page.wait_for_timeout(min(1200,self.deadline.milliseconds()))

    def fetch_item(self,candidate,context):
        navigate(self.page,candidate['url'],self.deadline)
        rows=self._await_rows();root=next((r for r in rows if identify(r['url']).url==identify(candidate['url']).url),None)
        if not root:raise AdapterError('EXTRACTION_FAILED','PERMALINK_ITEM_MISMATCH')
        items={r['url']:r for r in rows};max_pages=context.get('max_pages',5)
        if context.get('scope')=='POSTS_AND_REPLIES':
            for _ in range(max_pages-1):
                self.deadline.check();self._scroll()
                self.page.wait_for_timeout(self.deadline.milliseconds(1600))
                fresh=self._read();before=len(items);items.update({r['url']:r for r in fresh})
                # Lazy comments can arrive a scroll later. A quiet page is not
                # proof that the conversation ended; the configured page budget
                # remains the bound and coverage stays explicitly partial.
        # DOM presence establishes conversation context, not exact nested parent.
        # Only rows within this post's conversation are accepted; recommended posts
        # following the conversation are excluded unless explicit reply UI verifies them.
        replies=[r for r in items.values() if r['url']!=root['url'] and (r.get('pagelet') or '').startswith('threads_post_')]
        return {'root':root,'replies':replies[:context.get('max_replies',100)] if context.get('scope')=='POSTS_AND_REPLIES' else [],
            'parent_mapping':'UNVERIFIED','coverage_limited':True,'error_code':'DOM_PARENT_MAPPING_UNVERIFIED',
            'method':self.method}


class ThreadsAPIAdapter:
    method='THREADS_API'
    fields='id,text,permalink,username,timestamp,shortcode,has_replies,is_reply,root_post,replied_to'
    def __init__(self,token,deadline,http=None,request_budget=None):
        if not token:raise AdapterError('AUTH_REQUIRED','MISSING_THREADS_ACCESS_TOKEN')
        self.token,self.deadline,self.http=token,deadline,http or requests
        self.requests=0
        self.request_budget=request_budget if request_budget is not None else {'used':0,'limit':100}

    def _get(self,path,params):
        if not re.fullmatch(r'(keyword_search|\d+(?:/(conversation|replies))?)',path):raise ValueError('Invalid Threads endpoint')
        self.deadline.check()
        if self.request_budget['used']>=self.request_budget['limit']:raise AdapterError('BUDGET_EXHAUSTED','REQUEST_BUDGET_REACHED')
        self.requests+=1
        self.request_budget['used']+=1
        try:
            response=self.http.get('https://graph.threads.net/v1.0/'+path,params=params,
                headers={'Authorization':'Bearer '+self.token},timeout=min(20,self.deadline.remaining()),allow_redirects=False)
            try:
                if response.status_code==429:raise AdapterError('RATE_LIMITED','HTTP_429')
                if response.status_code in {401,403}:raise AdapterError('ACCESS_DENIED','TOKEN_OR_PERMISSION_DENIED')
                if response.status_code!=200:raise AdapterError('EXTRACTION_FAILED','THREADS_API_HTTP_ERROR')
                if len(response.content)>4_000_000:raise AdapterError('EXTRACTION_FAILED','RESPONSE_TOO_LARGE')
                try:body=response.json()
                except ValueError:raise AdapterError('EXTRACTION_FAILED','THREADS_API_INVALID_JSON') from None
                if not isinstance(body,dict):raise AdapterError('EXTRACTION_FAILED','THREADS_API_SCHEMA_MISMATCH')
                if 'error' in body:raise AdapterError('ACCESS_DENIED','THREADS_PROVIDER_ERROR')
                return body
            finally:response.close()
        except requests.RequestException:raise AdapterError('TEMPORARY_ERROR','THREADS_CONNECTION_FAILED') from None

    @staticmethod
    def item(value):
        target=identify(value['permalink'])
        if target.platform!='threads' or target.kind!='CONTENT_ITEM':raise ValueError('Invalid provider permalink')
        return {**value,'url':target.url,'timestamp_basis':'API_TIMESTAMP'}

    def probe_access(self,source):
        body=self._get('keyword_search',{'q':source['query'],'search_type':'RECENT','fields':self.fields,'limit':1})
        if not isinstance(body.get('data'),list):raise AdapterError('EXTRACTION_FAILED','THREADS_API_SCHEMA_MISMATCH')
        return {'search_recent':'SUPPORTED','public_replies':'UNVERIFIED','candidates':len(body['data'])}

    def discover(self,request):
        cursor=None
        for index in range(request.get('max_pages',5)):
            params={'q':request['query'],'search_type':'RECENT','fields':self.fields,'limit':min(50,request.get('max_candidates',100))}
            if cursor:params['after']=cursor
            body=self._get('keyword_search',params)
            if not isinstance(body.get('data'),list):raise AdapterError('EXTRACTION_FAILED','THREADS_API_SCHEMA_MISMATCH')
            cursor=body.get('paging',{}).get('cursors',{}).get('after') if body.get('paging',{}).get('next') else None
            yield {'items':[self.item(v) for v in body['data']],'page':index,'cursor':cursor,
                'empty_verified':not body['data'] and index==0,'exhausted':not cursor,'observed_order':'RECENT_API','method':self.method}
            if not cursor:return

    def fetch_item(self,candidate,context):
        root=self.item(self._get(str(candidate['id']),{'fields':self.fields}));replies=[];cursor=None
        if context.get('scope')=='POSTS_AND_REPLIES':
            for _ in range(context.get('max_pages',5)):
                params={'fields':self.fields,'limit':50}
                if cursor:params['after']=cursor
                body=self._get(str(candidate['id'])+'/conversation',params)
                if not isinstance(body.get('data'),list):raise AdapterError('EXTRACTION_FAILED','THREADS_API_SCHEMA_MISMATCH')
                replies.extend(self.item(v) for v in body['data'])
                cursor=body.get('paging',{}).get('cursors',{}).get('after') if body.get('paging',{}).get('next') else None
                if not cursor or len(replies)>=context.get('max_replies',100):break
        return {'root':root,'replies':replies[:context.get('max_replies',100)],'parent_mapping':'PROVIDER_FIELDS',
            'coverage_limited':bool(cursor),'error_code':'PAGINATION_LIMIT' if cursor else None,'method':self.method}
