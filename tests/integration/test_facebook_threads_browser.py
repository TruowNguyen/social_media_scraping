"""Actual Chromium against controlled Facebook-like DOM, no platform request."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.acquisition.browser import browser_job
from src.acquisition.facebook_threads import collect_rows,scan_comments
from src.acquisition.models import Candidate,Deadline
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore


URL='https://www.facebook.com/groups/123/posts/111'


@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in isolated Chromium DOM test')
class ThreadBrowserTests(unittest.TestCase):
    def test_reply_jump_anchor_does_not_relabel_parent_comment(self):
        html='<article role="article"><a href="'+URL+'?comment_id=222&amp;reply_comment_id=333" hidden></a><a href="'+URL+'?comment_id=222">1h</a><div data-comment-text>parent comment</div><article role="article"><a href="'+URL+'?comment_id=222&amp;reply_comment_id=333">1h</a><div data-comment-text>reply text</div></article></article>'
        with tempfile.TemporaryDirectory() as directory,patch('src.browser.profiles.DEFAULT_PROFILE_ROOT',Path(directory)/'profiles'):
            with browser_job('facebook',Deadline(30)) as page:
                page.route('https://www.facebook.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
                page.goto(URL)
                rows={r['native_id']:r for r in collect_rows(page,URL,'111')}
                self.assertEqual(set(rows),{'222','333'})
                self.assertEqual(rows['222']['raw_text'],'parent comment')
                self.assertEqual(rows['333']['raw_text'],'reply text')
                self.assertEqual(rows['333']['parent_native_id'],'222')

    def test_expand_comment_preserves_link_text_without_nested_duplicates(self):
        html='<article role="article"><a href="'+URL+'?comment_id=222">1h</a><div data-comment-text><div dir="auto">Waiting <a href="https://example.com">at gate</a></div></div><button onclick="document.querySelector(\'[data-comment-text]\').innerText=\'Waiting at gate for 40 minutes\';this.remove()">See more</button></article>'
        with tempfile.TemporaryDirectory() as directory,patch('src.browser.profiles.DEFAULT_PROFILE_ROOT',Path(directory)/'profiles'):
            store=ConversationStore(Path(directory)/'raw.db')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','run')['node_id']
                with browser_job('facebook',Deadline(30)) as page:
                    page.route('https://www.facebook.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
                    page.goto(URL)
                    self.assertEqual(collect_rows(page,URL,'111')[0]['raw_text'],'Waiting at gate')
                    c=Candidate('facebook',URL,URL,'group','run','BROWSER_THREAD',platform_item_id='111')
                    scan_comments(page,store,c,root,Deadline(10))
                    self.assertEqual(next(n for n in store.list_nodes() if n['node_type']=='COMMENT')['raw_text'],'Waiting at gate for 40 minutes')
            finally:store.close()

    def test_background_feed_controls_are_not_clicked_behind_post_dialog(self):
        html='''<button onclick="document.body.dataset.badClick='yes'">View more comments</button>
          <div role="dialog"><div role="dialog"><span>Chưa có bình luận nào</span></div></div>'''
        with tempfile.TemporaryDirectory() as directory,patch('src.browser.profiles.DEFAULT_PROFILE_ROOT',Path(directory)/'profiles'):
            store=ConversationStore(Path(directory)/'raw.db')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL),'group','run')['node_id']
                with browser_job('facebook',Deadline(30)) as page:
                    page.route('https://www.facebook.com/**',lambda route:route.fulfill(status=200,content_type='text/html;charset=utf-8',body=html))
                    page.goto(URL)
                    c=Candidate('facebook',URL,URL,'group','run','BROWSER_THREAD',platform_item_id='111')
                    coverage=scan_comments(page,store,c,root,Deadline(10))
                    self.assertIsNone(page.evaluate('document.body.dataset.badClick||null'))
                    self.assertEqual(coverage['status'],'UNKNOWN')
                    self.assertFalse(coverage['full_thread_verified'])
            finally:store.close()

    def test_hydration_ownership_native_ids_replies_and_own_timestamps(self):
        def relay(text): return base64.b64encode(text.encode()).decode()
        data={'comments':[
            {'__typename':'Comment','id':relay('comment:111_222'),'body':{'text':'comment'},'created_time':1791417600},
            {'__typename':'Comment','id':relay('comment:111_333'),'parent_comment':{'id':relay('comment:111_222')},'body':{'text':'reply'},'created_time':1791421200},
            {'__typename':'Comment','id':relay('comment:999_444'),'body':{'text':'recommended thread must be excluded'}},
        ]}
        with tempfile.TemporaryDirectory() as directory,patch('src.browser.profiles.DEFAULT_PROFILE_ROOT',Path(directory)/'profiles'):
            with browser_job('facebook',Deadline(30)) as page:
                page.route('https://www.facebook.com/**',lambda route: route.fulfill(status=200,content_type='text/html',body='<script type="application/json">'+json.dumps(data)+'</script>'))
                page.goto(URL)
                rows=collect_rows(page,URL,'111')
                self.assertEqual({r['native_id'] for r in rows},{'222','333'})
                self.assertEqual(next(r for r in rows if r['native_id']=='333')['parent_native_id'],'222')
                self.assertTrue(all(r['publication_precision']=='INSTANT' for r in rows))

    def test_comment_pagination_saves_child_and_reports_partial_not_complete(self):
        html='''<article role="article"><a href="''' + URL + '''?comment_id=222">Comment</a>
          <div data-comment-text>kẹt cổng</div><time datetime="2026-10-08T00:00:00Z"></time></article>
          <button id="more" onclick="document.querySelector('#reply').hidden=false;this.remove()">View more replies</button>
          <article role="article" id="reply" hidden><a href="''' + URL + '''?comment_id=222&amp;reply_comment_id=333">Reply</a>
          <div data-comment-text>tôi cũng chờ</div><time datetime="2026-10-08T00:15:00Z"></time></article>'''
        with tempfile.TemporaryDirectory() as directory,patch('src.browser.profiles.DEFAULT_PROFILE_ROOT',Path(directory)/'profiles'):
            store=ConversationStore(Path(directory)/'db.sqlite3')
            try:
                root=store.ingest(ContentNode('POST',platform_item_id='111',canonical_url=URL,raw_text='old parent'),'group','run')['node_id']
                with browser_job('facebook',Deadline(30)) as page:
                    page.route('https://www.facebook.com/**',lambda route: route.fulfill(status=200,content_type='text/html;charset=utf-8',body=html))
                    page.goto(URL)
                    candidate=Candidate('facebook',URL,URL,'group','run','BROWSER_THREAD',platform_item_id='111')
                    coverage=scan_comments(page,store,candidate,root,Deadline(20))
                    self.assertEqual(coverage['observed_comments_and_replies'],2)
                    self.assertFalse(coverage['full_thread_verified'])
                    self.assertEqual(coverage['status'],'PARTIAL')
                self.assertEqual(len(store.list_nodes()),3)
            finally: store.close()
