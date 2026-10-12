"""Visible DOM parser fixtures, no social network or credentials."""
import os
import unittest
from src.acquisition.threads import READ_DOM
from src.browser.profiles import prepare_browser_path

@unittest.skipUnless(os.environ.get('ACQUISITION_BROWSER_TESTS')=='1','Opt-in Chromium')
class ThreadsDOMTests(unittest.TestCase):
    def test_caption_ends_before_actions_and_composer_notices(self):
        from playwright.sync_api import sync_playwright
        prepare_browser_path()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page()
            html='''<div data-pagelet="threads_post_page_1"><div data-pressable-container="true">
                <span dir="auto"><a href="/@tester/post/abc"><time datetime="2026-10-01T00:00:00Z">Yesterday</time></a></span>
                <span dir="auto">No replies yet is the caption itself</span><span dir="auto">Caption second paragraph</span>
                <div role="button" aria-label="Like"><span dir="auto">12</span></div>
                <span dir="auto">No replies yet</span><div role="textbox" contenteditable="true"><p dir="auto">draft</p></div>
                <span dir="auto">Reply to tester...</span><span dir="auto">This post and replies from Meta AI are public.</span>
                </div></div>'''
            page.route('https://www.threads.com/**',lambda route:route.fulfill(content_type='text/html',body=html))
            page.goto('https://www.threads.com/@tester/post/abc')
            values=page.evaluate(READ_DOM)
            self.assertEqual(values[0]['text'],'No replies yet is the caption itself\nCaption second paragraph')
            self.assertEqual(values[0]['timestamp'],'2026-10-01T00:00:00Z');browser.close()

    def test_inline_translation_control_is_not_caption_and_links_are_kept(self):
        from playwright.sync_api import sync_playwright
        prepare_browser_path()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page()
            html='''<div data-pagelet="threads_post_page_1"><div data-pressable-container="true">
              <a href="/@tester/post/abc"><time datetime="2026-10-01T00:00:00Z">Yesterday</time></a>
              <span dir="auto"><span>Translate is a legitimate caption word<br>Second <a href="/search">#topic</a></span><div role="button"><span>Translate</span></div></span>
              <div role="button" aria-label="Like"></div></div></div>'''
            page.route('https://www.threads.com/**',lambda route:route.fulfill(content_type='text/html',body=html))
            page.goto('https://www.threads.com/@tester/post/abc')
            self.assertEqual(page.evaluate(READ_DOM)[0]['text'],'Translate is a legitimate caption word\nSecond #topic')
            browser.close()

if __name__=='__main__':unittest.main()
