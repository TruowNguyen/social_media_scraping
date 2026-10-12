"""Public Facebook group and TikTok UI adapters. Selectors require live pilot."""
from dataclasses import replace
import re
import time
from urllib.parse import quote, urlsplit, parse_qs

from src.acquisition.browser import navigate, page_failure
from src.acquisition.identity import identify, identity, hashtag_query, source_references
from src.acquisition.models import (AdapterError, AccessProbeResult, Candidate, CandidateBatch, FetchResult, parse_utc)

FB_SELECTOR = '[role="feed"] [role="article"], [role="article"]'
TT_SELECTOR = '[data-e2e="search_video-item"], [data-e2e="search-video-item"], [data-e2e="challenge-item"], [data-e2e="user-post-item"]'
FB_TEXT = '[data-ad-preview="message"], [data-ad-comet-preview="message"], [data-ad-rendering-role="story_message"]'
FB_REFERENCE_SCRIPT = r"""nodes => {
  const references=new Map();
  for(const node of nodes){let url;try{url=new URL(node.href)}catch{continue}
    if(!['facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'].includes(url.hostname))continue;
    const match=url.pathname.match(/^\/groups\/([^/]+)\/(?:posts|permalink)\/([^/]+)\/?$/);
    if(!match)continue;
    const canonical='https://www.facebook.com/groups/'+match[1]+'/posts/'+match[2];
    // A comment URL proves a parent reference, never the parent's text or time.
    references.set(canonical,{links:[canonical],post_id:match[2],caption:null,reference_only:true});
  }
  return [...references.values()];
}"""
TT_TEXT = '[data-e2e="search-card-desc"], [data-e2e="search-video-desc"], [data-e2e="video-desc"], [data-e2e="browse-video-desc"]'

CARD_SCRIPT = r"""(nodes, platform) => nodes.map(node => {
    const texts = platform === 'facebook'
      ? '[data-ad-preview="message"], [data-ad-comet-preview="message"], [data-ad-rendering-role="story_message"]'
      : '[data-e2e="search-card-desc"], [data-e2e="search-video-desc"], [data-e2e="video-desc"], [data-e2e="browse-video-desc"]';
    const caption = [...node.querySelectorAll(texts)].find(n=>platform!=='facebook'||n.closest('[role="article"]')===node)?.innerText || null;
    const own = n => platform!=='facebook'||n.closest('[role="article"]')===node;
    const stamp = [...node.querySelectorAll('time[datetime], abbr[data-utime]')].find(own);
    return {links: [...node.querySelectorAll('a[href]')].filter(own).map(a => a.href),
      caption: caption ? caption.slice(0,4000) : null, truncated: (caption?.length || 0)>4000,
      datetime: stamp?.getAttribute('datetime') || null, epoch: stamp?.getAttribute('data-utime') || null,
      time_raw: stamp?.innerText || null,
      author_name: node.querySelector('[data-e2e="search-card-user-unique-id"], [data-e2e="video-author-uniqueid"], h2 a[href], h3 a[href]')?.innerText || null,
      author_url: node.querySelector('h2 a[href], h3 a[href]')?.href || null,
      metric_labels: [...node.querySelectorAll('[aria-label]')].slice(0,100).map(n=>n.getAttribute('aria-label')),
      video_present: !!node.querySelector('video'),
      media: [...node.querySelectorAll('video[src], a[href*="/photo"] img[src], a[href*="photo.php"] img[src], a[href*="/video/"] img[src]')]
        .filter(m=>platform!=='facebook'||m.closest('[role="article"]')===node).slice(0,8)
        .map(m => ({media_type:m.tagName==='VIDEO'?'VIDEO':'IMAGE',url:m.src}))};
})"""

# Public page hydration only. Match the post's own Story object; never infer
# publication from comment objects, attached/shared stories or discovery time.
FB_STORY_SCRIPT = r"""nodes => {
  const posts=new Map(); let visited=0;
  for(const script of nodes){let data;try{data=JSON.parse(script.textContent)}catch(e){continue}
    const stack=[[data,0]];
    while(stack.length&&visited<60000){const [node,depth]=stack.pop();visited++;
      if(!node||typeof node!=='object'||depth>45)continue;
      const id=String(node.post_id||'');
      const isStory=node.__typename==='Story';
      const fragment=!node.__typename&&(node.target_group||node.comet_permalink_url||node.actors);
      if(/^\d+$/.test(id)&&(isStory||fragment)){
        const row=posts.get(id)||{post_id:id,links:[],caption:null,epoch:null,video_present:false,media:[],metric_labels:[]};
        const url=node.permalink_url||node.comet_permalink_url||node.url;
        if(typeof url==='string'&&url.includes('/groups/'))row.links.push(url);
        if(isStory&&Number.isInteger(node.creation_time)&&node.creation_time>0){
          if(row.epoch&&row.epoch!==node.creation_time)row.time_conflict=true;
          row.epoch=node.creation_time;
        }
        if(typeof node.message?.text==='string')row.caption=node.message.text;
        if(isStory&&node.attachments){const media=[node.attachments];let checked=0;
          while(media.length&&checked++<300){const entry=media.pop();if(!entry||typeof entry!=='object')continue;
            if(entry.__typename==='Video')row.video_present=true;
            if(entry.__typename==='Photo'){
              const images=Object.values(entry).filter(v=>v&&typeof v==='object'&&typeof v.uri==='string'&&/^https:\/\//.test(v.uri));
              images.sort((a,b)=>(b.width||0)*(b.height||0)-(a.width||0)*(a.height||0));
              if(images.length&&!row.media.some(m=>m.url===images[0].uri))row.media.push({media_type:'IMAGE',url:images[0].uri,platform_media_id:String(entry.id||'')||null});
            }
            for(const [key,value]of Object.entries(entry))if(key!=='attached_story'&&value&&typeof value==='object')media.push(value);
          }
        }posts.set(id,row);
      }
      for(const value of Object.values(node))if(value&&typeof value==='object')stack.push([value,depth+1]);
    }
  }return [...posts.values()].filter(row=>row.links.length).map(row=>{
    if(row.time_conflict)row.epoch=null;
    return row;
  });
}"""


def candidate_from_row(row, request, platform):
    target = None
    allowed_refs = source_references(request.source)
    for url in row.get("links", []):
        try:
            # A comment permalink is not evidence of a post's publication time
            # or listing identity. Never use a reply as the source post.
            if platform == "facebook" and set(parse_qs(urlsplit(url).query)) & {"comment_id", "reply_comment_id"}:
                continue
            parsed = identify(url)
        except (ValueError, TypeError):
            continue
        if parsed.platform == platform and parsed.kind == "CONTENT_ITEM" and (platform != "facebook" or parsed.origin in allowed_refs):
            if row.get("post_id") and parsed.item_id != row["post_id"]:
                continue
            target = parsed
            break
    if not target:
        return None
    candidate = Candidate(platform, target.url, target.url, request.source["source_id"], request.crawl_run_id,
                          "FACEBOOK_GROUP_BROWSER" if platform == "facebook" else "TIKTOK_HASHTAG_BROWSER" if request.mode == "HASHTAG_SEARCH" else "TIKTOK_KEYWORD_BROWSER",
                          platform_item_id=target.item_id, origin_source_ref=target.origin, target_source_id=request.source["source_id"],
                          query_id=request.query_id, query_type=request.query_type, search_keyword=request.search_keyword, effective_query=request.effective_query,
                          caption=row.get("caption") or None, media_refs=row.get("media", []), published_time_raw=row.get("time_raw"))
    candidate.author["display_name"] = row.get("author_name")
    candidate.content_type = "VIDEO" if platform == "tiktok" or row.get("video_present") else "POST"
    if not candidate.media_refs:
        candidate.missing_data_reasons.append("MEDIA_NOT_RESOLVED")
    if platform == "facebook" and row.get("author_url"):
        author_url = urlsplit(row["author_url"])
        if author_url.hostname in {"facebook.com", "www.facebook.com", "web.facebook.com", "m.facebook.com"}:
            candidate.author["profile_url"] = row["author_url"].split("#")[0]
            candidate.author["platform_author_id"] = parse_qs(author_url.query).get("id", [None])[0]
    for label in row.get("metric_labels", []):
        for key, pattern in {"likes": r"(\d+) (?:reactions|lượt cảm xúc)", "comments": r"(\d+) (?:comments|bình luận)", "shares": r"(\d+) (?:shares|lượt chia sẻ)"}.items():
            match = re.fullmatch(pattern, label, re.I)
            if match:
                candidate.engagement[key] = int(match[1])
    if platform == "tiktok":
        candidate.author["profile_url"] = "https://www.tiktok.com/@" + target.origin
        candidate.author["platform_author_id"] = target.origin
    candidate.hashtags = re.findall(r"#[\w]+", candidate.caption or "", re.UNICODE)
    if row.get("truncated"):
        candidate.missing_data_reasons.append("CAPTION_TRUNCATED")
    set_publication(candidate, row.get("datetime"), row.get("epoch"))
    if not candidate.published_at and row.get("time_raw") and re.search(r"\b(?:giờ|phút|ngày|hour|minute|ago|yesterday)\b", row["time_raw"], re.I):
        candidate.publication_precision = "APPROXIMATE"
    candidate.window_status = request.window.status(candidate.published_at, candidate.publication_precision)
    candidate.evidence_provenance = [platform.upper() + "_BROWSER_CAPTION"] if candidate.caption else []
    if row.get('reference_only'):
        candidate.evidence_provenance.append('FACEBOOK_POST_PERMALINK_REFERENCE')
    if candidate.published_at and row.get("post_id"):
        candidate.evidence_provenance += ["FACEBOOK_PUBLIC_STORY_METADATA", "FACEBOOK_NATIVE_PUBLICATION_TIME"]
    if not candidate.caption:
        candidate.missing_data_reasons.append("CAPTION_MISSING")
    if not candidate.published_at:
        candidate.missing_data_reasons.append("PUBLICATION_TIME_UNRESOLVED")
    candidate.missing_data_reasons.append("ENGAGEMENT_PARTIAL")
    return candidate


def set_publication(candidate, timestamp=None, epoch=None):
    from datetime import datetime, timezone
    try:
        if timestamp:
            candidate.published_at = parse_utc(timestamp).isoformat().replace("+00:00", "Z")
        elif epoch is not None:
            candidate.published_at = datetime.fromtimestamp(int(epoch), timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            return
        candidate.publication_precision = "INSTANT"
    except (ValueError, TypeError, OverflowError, OSError):
        candidate.published_at = None
        if isinstance(timestamp, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", timestamp):
            try:
                candidate.publication_date = datetime.fromisoformat(timestamp).date().isoformat()
                candidate.publication_precision = "DATE_ONLY"
            except ValueError:
                pass


class BrowserAdapter:
    def __init__(self, page, deadline, platform):
        self.page, self.deadline, self.platform = page, deadline, platform
        self.selector = FB_SELECTOR if platform == "facebook" else TT_SELECTOR

    def discovery_url(self, source, mode=None, keyword=None):
        if self.platform == "facebook":
            return source["url"]
        if mode == "HASHTAG_SEARCH":
            return "https://www.tiktok.com/tag/" + quote(hashtag_query(keyword), safe="")
        if not keyword or not keyword.strip():
            raise ValueError("Keyword cannot be empty")
        return "https://www.tiktok.com/search/video?q=" + quote(keyword, safe="")

    def is_empty(self):
        pattern = re.compile(r"^(?:No posts yet|No results found|No results|Chưa có bài viết|Không tìm thấy kết quả)[.!]?$", re.I)
        return self.page.get_by_text(pattern).count() > 0

    def listing_rows(self):
        rows = self.page.locator(self.selector).evaluate_all(CARD_SCRIPT, self.platform)
        if self.platform == "facebook":
            rows = self.page.locator('script[type="application/json"]').evaluate_all(FB_STORY_SCRIPT) + rows
            rows += self.page.locator('a[href]').evaluate_all(FB_REFERENCE_SCRIPT)
        return rows

    def latest_order(self):
        """Use visible sort controls only; never assume a query parameter sorted UI."""
        current = self.page.get_by_role("button", name=re.compile(r"^(Most relevant|Relevant|Relevance|Phù hợp nhất|Có liên quan nhất|Sort by|Sắp xếp theo)$", re.I))
        if not current.count() or not current.first.is_visible():
            return "UNKNOWN"
        original_order = "RELEVANCE" if re.search(r"relevant|relevance|phù hợp|liên quan", current.first.inner_text(), re.I) else "UNKNOWN"
        current.first.click(timeout=self.deadline.milliseconds(2000))
        latest = re.compile(r"^(New posts|Newest|Latest|Most recent|Bài viết mới|Bài viết mới nhất|Mới nhất)$", re.I)
        for role in ("menuitem", "menuitemradio", "option"):
            option = self.page.get_by_role(role, name=latest)
            if option.count() and option.first.is_visible():
                option.first.click(timeout=self.deadline.milliseconds(2000))
                selected = self.page.get_by_role("button", name=latest)
                if selected.count() and selected.first.is_visible():
                    pinned = self.page.get_by_text(re.compile(r"^(Pinned post|Bài viết đã ghim)$", re.I))
                    return "MIXED" if pinned.count() else "LATEST"
                return "UNKNOWN"
        self.page.keyboard.press("Escape")
        return original_order

    def wait_listing(self):
        for _ in range(12):
            self.deadline.check()
            failure = page_failure(self.page)
            if failure:
                raise AdapterError(*failure)
            if self.page.locator(self.selector).count() or self.is_empty() or (self.platform == "facebook" and self.listing_rows()):
                return
            self.page.wait_for_timeout(self.deadline.milliseconds(500))
        raise AdapterError("EXTRACTION_FAILED", "LISTING_SELECTOR_MISMATCH")

    def probe_access(self, source):
        try:
            mode = "HASHTAG_SEARCH" if source.get("probe_query_type") == "HASHTAG" else "KEYWORD_SEARCH"
            navigate(self.page, self.discovery_url(source, mode, source.get("probe_query", "VinCons")), self.deadline)
            self.wait_listing()
            from datetime import datetime, timedelta, timezone
            from src.acquisition.models import DiscoveryRequest, Window
            now = datetime.now(timezone.utc)
            request = DiscoveryRequest(source, "access_probe", Window(now-timedelta(minutes=180), now), self.deadline, mode)
            rows = self.listing_rows()
            candidates = [candidate_from_row(row, request, self.platform) for row in rows]
            ids = list(dict.fromkeys(c.platform_item_id for c in candidates if c and c.platform_item_id))[:3]
            if not ids and not self.is_empty():
                raise AdapterError("EXTRACTION_FAILED", "PROBE_ITEM_IDENTITY_UNRESOLVED")
            return AccessProbeResult("ACCESSIBLE", sample_item_ids=ids)
        except AdapterError as error:
            return AccessProbeResult(error.status, error.code, requires_login=True if error.status == "AUTH_REQUIRED" else None)

    def discover(self, request):
        batch = CandidateBatch(observed_order="UNKNOWN", coverage_limited=True)
        seen = set()
        try:
            navigate(self.page, self.discovery_url(request.source, request.mode, request.search_keyword), request.deadline)
            self.wait_listing()
            if self.is_empty() and not self.page.locator(self.selector).count():
                return CandidateBatch(status="NO_NEW_DATA", stop_reason="EXPLICIT_EMPTY_UI")
            batch.observed_order = self.latest_order()
            stalls = 0
            # Reserve remaining job budget for fetch; never infer chronological order.
            listing_end = time.monotonic() + (min(request.listing_seconds,request.deadline.remaining()*.9) if request.listing_seconds else min(30,request.deadline.remaining()*.4))
            while time.monotonic() < listing_end:
                request.deadline.check()
                failure = page_failure(self.page)
                if failure:
                    raise AdapterError(*failure)
                rows = self.listing_rows()
                previous = len(seen)
                for row in rows:
                    candidate = candidate_from_row(row, request, self.platform)
                    if candidate and identity(candidate) not in seen:
                        seen.add(identity(candidate))
                        batch.candidates.append(candidate)
                        if len(batch.candidates) >= request.max_candidates:
                            batch.stop_reason = "ITEM_LIMIT"
                            return batch
                if not seen and rows:
                    raise AdapterError("EXTRACTION_FAILED", "ITEM_IDENTITY_SELECTOR_MISMATCH")
                stalls = stalls + 1 if len(seen) == previous else 0
                if stalls >= request.stall_limit:
                    batch.stop_reason = "NO_MORE_OBSERVED_RESULTS"
                    return batch
                self.page.evaluate("window.scrollBy(0, Math.max(800, window.innerHeight))")
                self.page.wait_for_timeout(request.deadline.milliseconds(750))
            batch.stop_reason = "LISTING_TIME_LIMIT"
            if not batch.candidates:
                raise AdapterError("EXTRACTION_FAILED", "NO_PARSEABLE_ITEMS")
        except AdapterError as error:
            batch.status = "PARTIAL" if batch.candidates else error.status
            batch.error_code, batch.stop_reason = error.code, error.code
        except Exception:
            batch.status = "PARTIAL" if batch.candidates else "EXTRACTION_FAILED"
            batch.error_code = batch.stop_reason = "BROWSER_EXTRACTION_FAILED"
        return batch

    def fetch_item(self, candidate, context):
        if not context.raw_first and candidate.prefilter_decision not in {"PASS", "REVIEW"}:
            raise ValueError("Fetch requires PASS or REVIEW")
        if context.raw_first and self.platform != "facebook":
            raise ValueError("Raw-first fetch is only implemented for Facebook")
        target = identify(candidate.canonical_url)
        if self.platform == "facebook":
            refs = source_references(context.source)
            if target.origin not in refs:
                raise AdapterError("ACCESS_DENIED", "ITEM_SOURCE_MISMATCH")
        if self.platform == "tiktok" and context.source["source_type"] == "TIKTOK_ACCOUNT" and target.origin not in source_references(context.source):
            raise AdapterError("ACCESS_DENIED", "ITEM_SOURCE_MISMATCH")
        navigate(self.page, target.url, context.deadline)
        try:
            resolved = identify(self.page.url)
        except ValueError:
            raise AdapterError("EXTRACTION_FAILED", "ITEM_REDIRECT_UNSUPPORTED") from None
        if resolved.platform != target.platform or resolved.item_id != target.item_id:
            raise AdapterError("EXTRACTION_FAILED", "ITEM_REDIRECT_MISMATCH")
        if self.platform == "facebook":
            # Modern Facebook often gives role=article to comments, while the
            # real post/timestamp is in public Story hydration data.
            from src.acquisition.models import DiscoveryRequest
            # Hydration may appear after DOMContentLoaded. Wait before reading it.
            self.wait_listing()
            hydration_found = False
            for row in self.page.locator('script[type="application/json"]').evaluate_all(FB_STORY_SCRIPT):
                metadata = candidate_from_row(row, DiscoveryRequest(context.source, candidate.crawl_run_id, context.window, context.deadline, "RECENT_SOURCE_ITEMS"), "facebook")
                if metadata and metadata.platform_item_id == candidate.platform_item_id:
                    candidate.caption = candidate.raw_text = metadata.caption
                    candidate.published_at = metadata.published_at
                    candidate.publication_precision = metadata.publication_precision
                    candidate.content_type = metadata.content_type
                    candidate.media_refs = metadata.media_refs or candidate.media_refs
                    candidate.hashtags = metadata.hashtags
                    candidate.window_status = metadata.window_status
                    candidate.missing_data_reasons = metadata.missing_data_reasons
                    candidate.evidence_provenance = list(dict.fromkeys(metadata.evidence_provenance + ["FACEBOOK_PUBLIC_STORY_METADATA"]))
                    candidate.extraction_status = "FETCHED" if candidate.raw_text else "METADATA_ONLY"
                    hydration_found = True
                    break
            # Expand only after the prefilter and only within a matching article.
            articles = self.page.locator(FB_SELECTOR)
            article = None
            for index in range(articles.count()):
                node = articles.nth(index)
                links = node.evaluate('node => [...node.querySelectorAll("a[href]")].filter(a=>a.closest("[role=article]")===node).map(a=>a.href)')
                if any(self._same_item(url, target.item_id) and not parse_qs(urlsplit(url).query).get('comment_id') and not parse_qs(urlsplit(url).query).get('reply_comment_id') for url in links):
                    article = node
                    break
            if article is None:
                # Some native post dialogs put only comments in role=article.
                # Read the post's message from the uniquely scoped dialog, after
                # verifying its Story identity and an in-dialog post reference.
                from src.acquisition.facebook_threads import thread_scope
                scope = thread_scope(self.page)
                if scope is not self.page and hydration_found:
                    scope_links = scope.locator('a[href]').evaluate_all('nodes => nodes.map(n=>n.href)')
                    if any(self._same_item(url, target.item_id) for url in scope_links):
                        article = scope
            if article is None:
                if hydration_found:
                    return FetchResult(candidate)
                raise AdapterError("EXTRACTION_FAILED", "POST_SELECTOR_MISMATCH")
            more = article.get_by_role("button", name=re.compile(r"^(See more|Xem thêm)$", re.I))
            article_handle = article.element_handle()
            for index in range(more.count()):
                own_button = more.nth(index).evaluate('''(node, scope) => node.closest('[role=article]') === scope ||
                    (scope.getAttribute('role') === 'dialog' && !node.closest('[role=article]') && node.closest('[role=dialog]') === scope)''', article_handle)
                if own_button and more.nth(index).is_visible():
                    more.nth(index).click(timeout=context.deadline.milliseconds(3000))
                    self.page.wait_for_timeout(context.deadline.milliseconds(200))
            message = article.evaluate('''scope => {
                const nodes = [...scope.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"], [data-ad-rendering-role="story_message"]')]
                    .filter(n=>n.closest('[role=article]') === scope || (scope.getAttribute('role') === 'dialog' && !n.closest('[role=article]') && n.closest('[role=dialog]') === scope))
                    .filter(n=>n.getClientRects().length);
                const outer = nodes.filter(n=>!nodes.some(other=>other!==n && other.contains(n)));
                const texts = [...new Set(outer.map(n=>n.innerText.trim()).filter(Boolean))];
                return {text:texts.length===1?texts[0]:null,ambiguous:texts.length>1};
            }''')
            if message['ambiguous']:
                raise AdapterError('EXTRACTION_FAILED','POST_MESSAGE_SELECTOR_AMBIGUOUS')
            full_text = message['text']
            if article.get_attribute('role') == 'dialog':
                row = {}
            else:
                row = article.evaluate("(node, platform) => (" + CARD_SCRIPT + ")([node], platform)", "facebook")[0]
            if hydration_found:
                dom_text = full_text
                full_text = candidate.raw_text
                if dom_text and (not full_text or dom_text.startswith(full_text.rstrip('\u2026.'))):
                    full_text = dom_text
            else:
                set_publication(candidate, row.get("datetime"), row.get("epoch"))
            candidate.media_refs = row.get("media", []) or candidate.media_refs
            candidate.published_time_raw = row.get("time_raw") or candidate.published_time_raw
            from src.acquisition.models import DiscoveryRequest
            metadata = candidate_from_row(row, DiscoveryRequest(context.source, candidate.crawl_run_id, context.window, context.deadline, "RECENT_SOURCE_ITEMS"), "facebook")
            if metadata:
                candidate.author.update({key: value for key, value in metadata.author.items() if value is not None})
                candidate.engagement.update({key: value for key, value in metadata.engagement.items() if value is not None})
        else:
            for _ in range(12):
                context.deadline.check()
                failure = page_failure(self.page)
                if failure:
                    raise AdapterError(*failure)
                if self.page.locator('script#__UNIVERSAL_DATA_FOR_REHYDRATION__, video, ' + TT_TEXT).count():
                    break
                self.page.wait_for_timeout(context.deadline.milliseconds(500))
            # Public page hydration only; no private endpoints or ASR.
            info = self.page.evaluate("""() => { const node=document.querySelector('#__UNIVERSAL_DATA_FOR_REHYDRATION__');
              if(!node) return null; try {const data=JSON.parse(node.textContent);
              const item=data.__DEFAULT_SCOPE__?.['webapp.video-detail']?.itemInfo?.itemStruct;
              if(!item) return null; return {id:item.id,desc:item.desc,createTime:item.createTime,
              author:{id:item.author?.id,name:item.author?.nickname},stats:item.stats};} catch{return null;} }""")
            if info and str(info.get("id")) == target.item_id:
                full_text = info.get("desc") or None
                set_publication(candidate, epoch=info.get("createTime"))
                candidate.author.update(platform_author_id=(info.get("author") or {}).get("id"), display_name=(info.get("author") or {}).get("name"))
                for key, native in {"views": "playCount", "likes": "diggCount", "comments": "commentCount", "shares": "shareCount"}.items():
                    value = (info.get("stats") or {}).get(native)
                    candidate.engagement[key] = value if type(value) is int and value >= 0 else None
            else:
                nodes = self.page.locator(TT_TEXT)
                full_text = nodes.first.inner_text() if nodes.count() else None
                if not full_text and not self.page.locator('video, [data-e2e="browse-video"]').count():
                    raise AdapterError("EXTRACTION_FAILED", "VIDEO_SELECTOR_MISMATCH")
        candidate.raw_text = full_text
        candidate.content_type = "VIDEO" if self.platform == "tiktok" or candidate.content_type == "VIDEO" else "POST"
        candidate.extraction_status = "FETCHED" if full_text else "METADATA_ONLY"
        candidate.window_status = context.window.status(candidate.published_at, candidate.publication_precision)
        candidate.hashtags = re.findall(r"#[\w]+", full_text or candidate.caption or "", re.UNICODE)
        candidate.missing_data_reasons = [reason for reason in candidate.missing_data_reasons if not ((reason in {"CAPTION_MISSING", "CAPTION_TRUNCATED"} and full_text) or (reason == "PUBLICATION_TIME_UNRESOLVED" and candidate.published_at))]
        if full_text:
            candidate.evidence_provenance.append(self.platform.upper() + "_BROWSER_FULL_TEXT")
        else:
            candidate.missing_data_reasons.append("FULL_TEXT_MISSING")
        return FetchResult(candidate)

    @staticmethod
    def _same_item(url, item_id):
        try:
            return identify(url).item_id == item_id
        except ValueError:
            return False


class FacebookGroupAdapter(BrowserAdapter):
    def __init__(self, page, deadline):
        super().__init__(page, deadline, "facebook")


class TikTokSearchAdapter(BrowserAdapter):
    def __init__(self, page, deadline):
        super().__init__(page, deadline, "tiktok")
