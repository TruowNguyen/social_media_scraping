"""Read accessible comment/reply evidence, without pretending UI exhaustion proves all."""
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from src.acquisition.browser import page_failure
from src.acquisition.identity import identify
from src.acquisition.models import AdapterError
from src.domain.conversation import ContentNode


COMMENT_DOM = r'''nodes => nodes.map(node => {
  const own = el => el.closest('[role="article"]') === node;
  const links = [...node.querySelectorAll('a[href]')].filter(own);
  // Hidden jump anchors can point at a reply from its parent's article.
  // Prefer the article's visible timestamp link before any anchor fallback.
  const commentLinks = links.filter(a=>/[?&](?:comment_id|reply_comment_id)=/.test(a.href));
  const permalink = commentLinks.find(a=>a.innerText.trim() && a.getClientRects().length)
    || commentLinks.find(a=>a.getClientRects().length);
  if(!permalink) return null;
  const parent = node.parentElement?.closest('[role="article"]');
  const parentLink = parent && [...parent.querySelectorAll('a[href]')].find(a=>a.closest('[role="article"]')===parent&&/[?&]comment_id=/.test(a.href));
  const author = links.find(a=>/profile\.php|\/user\//.test(a.href));
  const explicit = [...node.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"], [data-comment-text]')].filter(own);
  const candidates = explicit.length ? explicit : [...node.querySelectorAll('div[dir="auto"]')].filter(own)
    .filter(el=>!el.closest('a,button,[role="button"],time') && !el.querySelector('time,abbr'));
  const message = candidates.filter(el=>!candidates.some(other=>other!==el && other.contains(el)));
  const stamp=[...node.querySelectorAll('time[datetime],abbr[data-utime]')].find(own);
  return {url:permalink.href,parent_url:parentLink?.href||null,text:message.map(el=>el.innerText).filter(Boolean).join('\n')||null,
    author_name:author?.innerText||null,author_url:author?.href||null,datetime:stamp?.getAttribute('datetime')||null,
    epoch:stamp?.getAttribute('data-utime')||null,time_raw:permalink.innerText||null,parser:'FACEBOOK_COMMENT_DOM_V1'};
}).filter(Boolean)'''

COMMENT_JSON = r'''(scripts, postId) => {
 const rows=[],visited=new WeakSet();let count=0;
 const decode=id=>{try{return atob(id)}catch(e){return String(id||'')}};
 for(const script of scripts){let data;try{data=JSON.parse(script.textContent)}catch(e){continue}
 const stack=[data];while(stack.length&&count++<100000){const node=stack.pop();if(!node||typeof node!=='object'||visited.has(node))continue;visited.add(node);
 if(node.__typename==='Comment'){
 const decoded=decode(node.id),match=/^comment:(\d+)_(\d+)$/.exec(decoded);
 const feedback=decode(node.feedback?.id||'');
 const root=match?.[1]||(/^feedback:(\d+)$/.exec(feedback)?.[1]);
 const native=String(node.legacy_fbid||match?.[2]||'');
 if(root===String(postId)&&/^\d+$/.test(native)){
 const parent=decode(node.parent_comment?.id||node.reply_to_comment?.id||'');
 const pm=/^comment:(\d+)_(\d+)$/.exec(parent);
 rows.push({native_id:native,parent_native_id:pm&&pm[1]===String(postId)?pm[2]:null,
 text:typeof node.body?.text==='string'?node.body.text:typeof node.message?.text==='string'?node.message.text:null,
 author_name:node.author?.name||null,author_uid:/^\d+$/.test(String(node.author?.id||''))?String(node.author.id):null,
 epoch:node.created_time||node.creation_time||null,parser:'FACEBOOK_COMMENT_HYDRATION_V1'});
 }}
 for(const [key,value]of Object.entries(node))if(value&&typeof value==='object'&&key!=='attached_story')stack.push(value);
 }}return rows;
}'''


def normalize_comment(row, post_url, post_native_id):
    native = row.get('native_id')
    parent = row.get('parent_native_id')
    url = row.get('url')
    reply = False
    if url:
        try:
            target = identify(url)
        except ValueError:
            return None
        if target.platform != 'facebook' or target.item_id != post_native_id:
            return None
        query = parse_qs(urlsplit(url).query)
        if query.get('reply_comment_id'):
            native, parent, reply = query['reply_comment_id'][0], query.get('comment_id', [None])[0], True
        else:
            native = query.get('comment_id', [None])[0]
            if row.get('parent_url'):
                p = parse_qs(urlsplit(row['parent_url']).query)
                parent = p.get('reply_comment_id', p.get('comment_id', [None]))[0]
                reply = bool(parent and parent != native)
    else:
        reply = bool(parent)
    if not native or not str(native).isdigit():
        return None
    published = None
    try:
        if row.get('datetime'):
            from src.acquisition.models import parse_utc
            published = parse_utc(row['datetime']).isoformat().replace('+00:00','Z')
        elif row.get('epoch') and str(row['epoch']).isdigit():
            published = datetime.fromtimestamp(int(row['epoch']),timezone.utc).isoformat().replace('+00:00','Z')
    except (ValueError, OverflowError, OSError):
        pass
    uid = row.get('author_uid')
    if uid is None and row.get('author_url'):
        uid = parse_qs(urlsplit(row['author_url']).query).get('id',[None])[0]
        if uid and not uid.isdigit(): uid = None
    return {'native_id':str(native),'parent_native_id':str(parent) if parent else None,
        'node_type':'REPLY' if reply else 'COMMENT','canonical_url':url,
        'raw_text':row.get('text'), 'published_at':published, 'publication_precision':'INSTANT' if published else 'UNKNOWN',
        'timestamp_raw':row.get('time_raw'), 'author_uid':uid, 'author_name':row.get('author_name'),
        'author_url':row.get('author_url'), 'parser':row.get('parser','UNKNOWN')}


def thread_scope(page):
    """Native permalinks open in a dialog over an unrelated group feed."""
    dialogs=page.get_by_role('dialog')
    visible=[dialogs.nth(i) for i in range(dialogs.count()) if dialogs.nth(i).is_visible()]
    # Facebook wraps the post dialog in another role=dialog with the same content.
    leaves=[]
    for dialog in visible:
        descendants=dialog.locator('[role="dialog"]')
        if not any(descendants.nth(i).is_visible() for i in range(descendants.count())):
            leaves.append(dialog)
    if len(leaves)>1:
        raise AdapterError('EXTRACTION_FAILED','AMBIGUOUS_THREAD_DIALOG')
    return leaves[0] if leaves else page


def collect_rows(page, post_url, post_native_id):
    rows = page.locator('script[type="application/json"]').evaluate_all(COMMENT_JSON, post_native_id)
    rows += thread_scope(page).locator('[role="article"]').evaluate_all(COMMENT_DOM)
    merged = {}
    for row in rows:
        item = normalize_comment(row, post_url, post_native_id)
        if not item: continue
        old = merged.get(item['native_id'])
        if old:
            # Prefer a verified expansion of the same text, never arbitrary longer UI text.
            if item.get('raw_text') and old.get('raw_text') and item['raw_text'].startswith(old['raw_text'].rstrip('\u2026.')):
                old['raw_text'] = item['raw_text']
            if item['parent_native_id'] and old['parent_native_id'] and item['parent_native_id']!=old['parent_native_id']:
                raise AdapterError('EXTRACTION_FAILED','COMMENT_PARENT_CONFLICT')
            if item['parent_native_id'] and not old['parent_native_id']:
                old['parent_native_id']=item['parent_native_id']
                old['node_type']='REPLY'
            if item['published_at'] and old['published_at'] and item['published_at'] != old['published_at']:
                old['published_at'],old['publication_precision'] = None,'UNKNOWN'
                old['time_conflict'] = True
            for key,value in item.items():
                if old.get(key) is None and value is not None and not (old.get('time_conflict') and key in {'published_at','publication_precision'}): old[key]=value
        else: merged[item['native_id']] = item
    return list(merged.values())


def save_comment_batch(store, rows, root_node_id, post_url, source_id, run_id, task_id, checkpoint):
    by_native = {row['native_id']:row for row in rows}
    saved = {}
    pending = list(rows)
    with store.transaction():
        while pending:
            progressed = False
            for row in pending[:]:
                known=store.db.execute('SELECT node_id FROM node_aliases WHERE alias=?',
                    ('FACEBOOK:COMMENT:native:'+row['native_id'],)).fetchone()
                known=store.get(known[0]) if known else None
                if known and known['root_post_id']!=root_node_id:
                    raise AdapterError('EXTRACTION_FAILED','COMMENT_THREAD_CONFLICT')
                parent_native = row['parent_native_id']
                parent_id = root_node_id
                if parent_native:
                    parent_id = saved.get(parent_native)
                    if parent_id is None:
                        matches = store.db.execute('SELECT node_id FROM node_aliases WHERE alias IN (?,?)',
                            ('FACEBOOK:COMMENT:native:'+parent_native,'FACEBOOK:REPLY:native:'+parent_native)).fetchall()
                        parent_id = matches[0][0] if len(matches)==1 else None
                    if parent_id is None and parent_native in by_native:
                        continue
                    if parent_id is None:
                        parent_id = 'reference_comment_' + root_node_id + '_' + parent_native
                        store.ingest(ContentNode('COMMENT',node_id=parent_id,platform_item_id=parent_native,
                            root_post_id=root_node_id,parent_node_id=root_node_id,relationship_status='UNRESOLVED',
                            extraction_status='REFERENCE_ONLY',availability_status='UNKNOWN'),source_id,run_id)
                fields = {key:row.get(key) for key in ('canonical_url','raw_text','published_at','publication_precision','timestamp_raw','author_uid','author_name','author_url')}
                node_type=row['node_type']
                restored_parent=bool(known and known['node_type']=='REPLY' and not parent_native)
                if restored_parent:
                    # Hydration/flat views can omit a reply's parent. Missing
                    # evidence must not demote an already verified reply.
                    node_type='REPLY';parent_id=known['parent_node_id'];fields['canonical_url']=known['canonical_url']
                if known and not restored_parent and known['relationship_status']=='RESOLVED' and known['parent_node_id']!=parent_id:
                    raise AdapterError('EXTRACTION_FAILED','COMMENT_PARENT_CONFLICT')
                node = ContentNode(node_type, platform_item_id=row['native_id'],root_post_id=root_node_id,parent_node_id=parent_id,
                    extraction_status='COMPLETE' if row['raw_text'] is not None else 'PARTIAL',
                    display_url=post_url if not fields['canonical_url'] else None,url_type='PARENT_FALLBACK' if not fields['canonical_url'] else None,
                    missing_fields=[key for key in ('raw_text','published_at') if row.get(key) is None],**fields)
                result = store.ingest(node,source_id,run_id,lineage={'parser_version':row['parser'],'parent_restored_from_saved_identity':restored_parent})
                saved[row['native_id']] = result['node_id']
                pending.remove(row); progressed = True
            if not progressed:
                raise AdapterError('EXTRACTION_FAILED','COMMENT_PARENT_CYCLE')
        store.ingest_batch([],task_id,checkpoint)
    return saved


def scan_comments(page, store, candidate, root_node_id, deadline, max_steps=30):
    task_id = 'comments:' + root_node_id
    seen = set(); steps = 0; sort = 'UNKNOWN'
    # Only use comment sorting controls; never submit a comment or click reactions.
    scope=thread_scope(page)
    for label in ('Phù hợp nhất','Most relevant'):
        control = scope.get_by_text(label, exact=True)
        if control.count()==1 and control.is_visible():
            control.click(timeout=deadline.milliseconds(2000))
            for option in ('Tất cả bình luận','All comments'):
                match = page.get_by_text(option,exact=True)
                if match.count()==1 and match.is_visible():
                    match.click(timeout=deadline.milliseconds(2000)); sort='ALL_COMMENTS'; break
            break
    reason='STEP_LIMIT'
    while steps<max_steps:
        deadline.check()
        failure=page_failure(page)
        if failure: raise AdapterError(*failure)
        # Expand text only on identified comments in the active thread.
        for article in thread_scope(page).locator('[role="article"]').all():
            if not article.locator('a[href*="comment_id="]').count():
                continue
            for button in article.get_by_role('button',name=re.compile(r'^(See more|Xem thêm)$',re.I)).all():
                if button.is_visible() and button.evaluate('(el,article)=>el.closest("[role=article]")===article',article.element_handle()):
                    button.click(timeout=deadline.milliseconds(2000))
                    page.wait_for_timeout(deadline.milliseconds(200))
        rows=collect_rows(page,candidate.canonical_url,candidate.platform_item_id)
        save_comment_batch(store,rows,root_node_id,candidate.canonical_url,candidate.source_id,candidate.crawl_run_id,
            task_id,{'rescan_anchor':candidate.canonical_url,'observed_native_ids':sorted(seen|{r['native_id'] for r in rows}), 'steps':steps,'coverage':'PARTIAL'})
        seen.update(r['native_id'] for r in rows)
        scope=thread_scope(page)
        buttons=scope.get_by_text(re.compile(r'^(?:Xem (?:thêm|các|\d+).*?(?:bình luận|phản hồi)|View (?:more|previous|\d+).*?(?:comments|replies)|\d+ (?:replies|phản hồi))$',re.I))
        clicked=False
        for index in range(min(buttons.count(),30)):
            button=buttons.nth(index)
            if button.is_visible():
                button.click(timeout=deadline.milliseconds(2000)); clicked=True; break
        steps+=1
        if not clicked:
            reason='NO_MORE_OBSERVED_CONTROLS'; break
        page.wait_for_timeout(deadline.milliseconds(500))
    if not seen:
        reason='NO_PARSEABLE_COMMENTS_OR_UNVERIFIED_EMPTY'
    # Browser controls disappearing cannot prove hidden/ranked/deleted comments are absent.
    coverage={'status':'PARTIAL' if seen else 'UNKNOWN','stop_reason':reason,'observed_comments_and_replies':len(seen),
        'sort':sort,'steps':steps,'full_thread_verified':False}
    store.ingest_batch([],task_id,{'rescan_anchor':candidate.canonical_url,'coverage':coverage})
    return coverage
