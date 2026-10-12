"""Opt-in real Chromium checks on synthetic DOM and isolated profiles only."""
from datetime import datetime, timedelta, timezone
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.acquisition.browser import browser_job, page_failure
from src.acquisition.browser_adapters import FacebookGroupAdapter, TikTokSearchAdapter, FB_STORY_SCRIPT, candidate_from_row, CARD_SCRIPT
from src.acquisition.models import Candidate, Deadline, DiscoveryRequest, FetchContext, Window


@unittest.skipUnless(os.environ.get("ACQUISITION_BROWSER_TESTS") == "1", "Opt-in Chromium local DOM checks")
class ChromiumAcquisitionTests(unittest.TestCase):
    def test_native_dialog_caption_outside_article_keeps_identity_and_ignores_feed(self):
        url='https://www.facebook.com/groups/123/posts/456'
        payload={'__typename':'Story','post_id':'456','permalink_url':url,'creation_time':1791342799}
        html='<script type="application/json">'+json.dumps(payload)+'</script><div data-ad-preview="message">Unrelated background feed</div><button onclick="document.body.dataset.badClick=\'yes\'">See more</button><div role="dialog"><div role="dialog"><div data-ad-preview="message">Own caption</div><button onclick="document.querySelector(\'[role=dialog] [data-ad-preview]\').innerText=\'Own caption expanded\';this.remove()">See more</button><article role="article"><a href="'+url+'?comment_id=222">1h</a><div data-ad-preview="message">Comment must not become caption</div></article></div></div>'
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,html)
            candidate=Candidate('facebook',url,url,self.source['source_id'],'fixture','BROWSER',platform_item_id='456')
            adapter=FacebookGroupAdapter(page,Deadline(30))
            fetched=adapter.fetch_item(candidate,FetchContext(self.source,self.window,adapter.deadline,raw_first=True)).candidate
            self.assertEqual(fetched.raw_text,'Own caption expanded')
            self.assertEqual(fetched.publication_precision,'INSTANT')
            self.assertEqual(fetched.extraction_status,'FETCHED')
            self.assertIsNone(page.evaluate('document.body.dataset.badClick||null'))

    def test_unrelated_dialog_does_not_supply_missing_caption(self):
        url='https://www.facebook.com/groups/123/posts/456'
        payload={'__typename':'Story','post_id':'456','permalink_url':url,'creation_time':1791342799}
        html='<script type="application/json">'+json.dumps(payload)+'</script><div role="dialog"><a href="https://www.facebook.com/groups/123/posts/999">Other post</a><div data-ad-preview="message">Unrelated message</div></div>'
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,html)
            candidate=Candidate('facebook',url,url,self.source['source_id'],'fixture','BROWSER',platform_item_id='456')
            adapter=FacebookGroupAdapter(page,Deadline(30))
            fetched=adapter.fetch_item(candidate,FetchContext(self.source,self.window,adapter.deadline,raw_first=True)).candidate
            self.assertIsNone(fetched.raw_text)

    def test_photo_hydration_excludes_attached_shared_story(self):
        url='https://www.facebook.com/groups/123/posts/456'
        photo={'__typename':'Photo','id':'photo1','image':{'uri':'https://scontent.example.fbcdn.net/post.jpg','width':900,'height':900}}
        payload={'__typename':'Story','post_id':'456','permalink_url':url,'message':{'text':'Own caption'},'attachments':[{'media':photo,'attached_story':{'media':{'__typename':'Photo','image':{'uri':'https://scontent.example.fbcdn.net/shared.jpg'}}}}]}
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,'<script type="application/json">'+json.dumps(payload)+'</script>')
            candidate=Candidate('facebook',url,url,self.source['source_id'],'fixture','BROWSER',platform_item_id='456')
            adapter=FacebookGroupAdapter(page,Deadline(30))
            fetched=adapter.fetch_item(candidate,FetchContext(self.source,self.window,adapter.deadline,raw_first=True)).candidate
            self.assertEqual(fetched.media_refs,[dict(media_type='IMAGE',url=photo['image']['uri'],platform_media_id='photo1')])

    def test_story_metadata_does_not_skip_expanded_dom_caption(self):
        url='https://www.facebook.com/groups/123/posts/456'
        payload={'__typename':'Story','post_id':'456','permalink_url':url,'creation_time':1791342799,'message':{'text':'Waiting at gate'}}
        html='<script type="application/json">'+json.dumps(payload)+'</script><article role="article"><a href="'+url+'">Post</a><div data-ad-preview="message">Waiting at gate</div><button onclick="document.querySelector(\'[data-ad-preview]\').innerText=\'Waiting at gate for 40 minutes\';this.remove()">See more</button></article>'
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,html)
            c=Candidate('facebook',url,url,self.source['source_id'],'fixture','BROWSER',platform_item_id='456')
            adapter=FacebookGroupAdapter(page,Deadline(30))
            fetched=adapter.fetch_item(c,FetchContext(self.source,self.window,adapter.deadline,raw_first=True)).candidate
            self.assertEqual(fetched.raw_text,'Waiting at gate for 40 minutes')
            self.assertEqual(fetched.publication_precision,'INSTANT')

    def test_public_story_metadata_uses_own_post_not_comment_or_attached_story(self):
        payload = dict(story=dict(__typename="Story", post_id="456", creation_time=1791342799,
                                  permalink_url="https://www.facebook.com/groups/123/posts/456", message=dict(text="VinCons complaint")),
                       comment=dict(__typename="Comment", post_id="456", creation_time=1791515599, message=dict(text="comment should not replace caption")),
                       conflict=[dict(__typename="Story",post_id="999",creation_time=1,permalink_url="https://www.facebook.com/groups/123/posts/999"),dict(__typename="Story",post_id="999",creation_time=2)])
        html = '<script type="application/json">'+json.dumps(payload)+'</script><article role="article"><article role="article"><time datetime="2026-10-08T10:00:00Z"></time></article></article>'
        with browser_job("facebook", Deadline(30)) as page:
            self.load(page, html)
            page.goto(self.source["url"])
            rows = page.locator('script[type="application/json"]').evaluate_all(FB_STORY_SCRIPT)
            self.assertEqual(len(rows),2)
            own = next(row for row in rows if row['post_id']=='456')
            conflict = next(row for row in rows if row['post_id']=='999')
            self.assertIsNone(conflict['epoch'])
            self.assertEqual(own["epoch"],1791342799)
            self.assertEqual(own["caption"],"VinCons complaint")
            req=DiscoveryRequest(self.source,"fixture",self.window,Deadline(30),"RECENT_SOURCE_ITEMS")
            candidate=candidate_from_row(own,req,"facebook")
            self.assertEqual(candidate.platform_item_id,"456")
            self.assertEqual(candidate.publication_precision,"INSTANT")
            cards=page.locator('[role="article"]').evaluate_all(CARD_SCRIPT,"facebook")
            self.assertIsNone(cards[0]["datetime"])

    def test_missing_publication_keeps_caption_through_raw_and_classifier_schema(self):
        from src.storage.conversations import ConversationStore
        from engine.classification_input import build_item,make_request
        from src.analysis.taxonomy import load_snapshot
        payload={'__typename':'Story','post_id':'456','permalink_url':'https://www.facebook.com/groups/123/posts/456',
                 'message':{'text':'VinCons kẹt cổng'}}
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,'<script type="application/json">'+json.dumps(payload)+'</script>')
            candidate=Candidate('facebook',payload['permalink_url'],payload['permalink_url'],self.source['source_id'],'fixture','BROWSER',platform_item_id='456')
            adapter=FacebookGroupAdapter(page,Deadline(30))
            fetched=adapter.fetch_item(candidate,FetchContext(self.source,self.window,adapter.deadline,raw_first=True)).candidate
            self.assertEqual(fetched.raw_text,payload['message']['text'])
            self.assertIsNone(fetched.published_at)
            self.assertEqual(fetched.publication_precision,'UNKNOWN')
            self.assertNotIn('FACEBOOK_NATIVE_PUBLICATION_TIME',fetched.evidence_provenance)
            raw=ConversationStore(self.root/'roundtrip.db')
            try:
                node_id=raw.ingest_candidate(fetched)['node_id']
                snapshot=load_snapshot(Path(__file__).resolve().parents[2]/'specs/taxonomy/v1')
                request=make_request([build_item(raw,node_id,self.source['source_id'],snapshot)],snapshot)
                self.assertEqual(request['items'][0]['target']['text'],payload['message']['text'])
                self.assertEqual(self.window.status(raw.get(node_id)['published_at'],'UNKNOWN'),'UNKNOWN')
            finally: raw.close()

    def test_unavailable_content_span_is_access_outcome_not_schema_error(self):
        with browser_job('facebook',Deadline(30)) as page:
            self.load(page,'<span>Bạn hiện không xem được nội dung này</span>')
            page.goto(self.source['url'])
            self.assertEqual(page_failure(page),('SOURCE_UNAVAILABLE','CONTENT_UNAVAILABLE'))
            page.unroute('https://www.facebook.com/**')
            self.load(page,'<article role="article"><span>Bạn hiện không xem được nội dung này</span></article>')
            page.goto(self.source['url'])
            self.assertIsNone(page_failure(page))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile_patch = patch("src.browser.profiles.DEFAULT_PROFILE_ROOT", self.root / "profiles")
        self.profile_patch.start()
        now = datetime.now(timezone.utc)
        self.window = Window(now-timedelta(minutes=180), now)
        self.source = dict(source_id="fb_fixture", source_type="FACEBOOK_GROUP", platform="facebook", platform_group_ref="123", url="https://www.facebook.com/groups/123")

    def tearDown(self):
        self.profile_patch.stop()
        self.temporary.cleanup()

    def load(self, page, html):
        page.route("https://fixture.invalid/**", lambda route: route.fulfill(status=204, body=""))
        page.route("https://www.facebook.com/**", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))
        page.route("https://www.tiktok.com/**", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))

    def test_fb_ac_07_listing_prefilter_then_expand_full_post(self):
        html = '''<html><body><div role="feed"><div role="article">
        <h2><a href="https://www.facebook.com/profile.php?id=999">Tác giả mẫu</a></h2>
        <a href="https://www.facebook.com/groups/123/posts/456">Post</a>
        <div data-ad-preview="message">Cổng công trường đông</div>
        <button onclick="document.querySelector('[data-ad-preview]').innerText+='; công nhân chờ lâu'">Xem thêm</button>
        <span aria-label="0 reactions"></span><span aria-label="3 comments"></span>
        <a href="https://www.facebook.com/photo.php?fbid=1"><img src="https://fixture.invalid/post.jpg"></a>
        <time datetime="2026-10-08T01:00:00Z">8 Oct</time>
        <div role="article"><div data-ad-preview="message">COMMENT MUST NOT BE COLLECTED</div>
        <a href="https://www.facebook.com/photo.php?fbid=2"><img src="https://fixture.invalid/comment.jpg"></a>
        <button onclick="document.body.dataset.commentExpanded='yes'">Xem thêm</button></div>
        </div></div></body></html>'''
        with browser_job("facebook", Deadline(30)) as page:
            self.load(page, html)
            adapter = FacebookGroupAdapter(page, Deadline(30))
            req = DiscoveryRequest(self.source, "fixture", self.window, adapter.deadline, "RECENT_SOURCE_ITEMS", max_candidates=1)
            batch = adapter.discover(req)
            self.assertEqual(batch.status, "SUCCESS")
            self.assertEqual(batch.stop_reason, "ITEM_LIMIT")
            self.assertEqual(len(batch.candidates), 1)
            candidate = batch.candidates[0]
            self.assertEqual(candidate.engagement["likes"], 0)
            self.assertEqual(candidate.author["platform_author_id"], "999")
            self.assertEqual(candidate.media_refs, [dict(media_type="IMAGE", url="https://fixture.invalid/post.jpg")])
            candidate.prefilter_decision = "REVIEW"
            result = adapter.fetch_item(candidate, FetchContext(self.source, self.window, adapter.deadline))
            self.assertIn("công nhân chờ lâu", result.candidate.raw_text)
            self.assertNotIn("COMMENT", result.candidate.raw_text)
            self.assertIsNone(page.evaluate("document.body.dataset.commentExpanded || null"))

    def test_ad_ac_07_explicit_empty_is_not_parser_mismatch(self):
        with browser_job("facebook", Deadline(30)) as page:
            self.load(page, '<h1>No posts yet</h1>')
            adapter = FacebookGroupAdapter(page, Deadline(30))
            req = DiscoveryRequest(self.source, "fixture", self.window, adapter.deadline, "RECENT_SOURCE_ITEMS")
            self.assertEqual(adapter.discover(req).status, "NO_NEW_DATA")
            page.unroute("https://www.facebook.com/**")
            self.load(page, '<h1>Changed layout</h1>')
            adapter.deadline = Deadline(15)
            req.deadline = adapter.deadline
            self.assertEqual(adapter.discover(req).status, "EXTRACTION_FAILED")

    def test_tt_ac_01_02_real_browser_distinct_search_and_hashtag(self):
        html = '''<div data-e2e="search_video-item"><a href="https://www.tiktok.com/@demo/video/123">video</a>
        <div data-e2e="search-card-desc">VinCons kẹt xe #VinCons</div></div>'''
        with browser_job("tiktok", Deadline(30)) as page:
            self.load(page, html)
            source = dict(source_id="tt_fixture", source_type="TIKTOK_SEARCH", platform="tiktok")
            adapter = TikTokSearchAdapter(page, Deadline(30))
            candidates = []
            for mode, term, query_type in (("KEYWORD_SEARCH", "VinCons kẹt xe", "KEYWORD"), ("HASHTAG_SEARCH", "#VinCons", "HASHTAG")):
                req = DiscoveryRequest(source, "fixture", self.window, adapter.deadline, mode, max_candidates=1, query_id=mode, query_type=query_type, search_keyword=term)
                batch = adapter.discover(req)
                self.assertEqual(batch.status, "SUCCESS")
                candidates.append(batch.candidates[0])
                self.assertIn("/tag/" if mode == "HASHTAG_SEARCH" else "/search/video?", page.url)
            self.assertEqual(candidates[0].platform_item_id, candidates[1].platform_item_id)
            self.assertNotEqual(candidates[0].query_id, candidates[1].query_id)

    def test_persistent_profile_survives_two_launches_on_local_data(self):
        for attempt in range(2):
            with browser_job("facebook", Deadline(30)) as page:
                page.route("https://fixture.invalid/**", lambda route: route.fulfill(status=200, content_type="text/html", body="<h1>Offline fixture</h1>"))
                page.goto("https://fixture.invalid/")
                if attempt == 0:
                    page.evaluate("localStorage.setItem('fixture', 'persisted')")
                else:
                    self.assertEqual(page.evaluate("localStorage.getItem('fixture')"), "persisted")
