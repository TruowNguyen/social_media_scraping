"""Fixtures exercise actual record construction, file writes and reruns.

Only acquisition, language detection and optional analysis are replaced. The
same assertions run before and after the structural migration.
"""
import asyncio
import datetime as dt
import importlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for key in ("SENTIMENT_MODEL", "MULTILINGUAL_SENTIMENT_MODEL", "ASSET_NLI_MODEL"):
    os.environ[key] = "none"

ROOT = Path(__file__).resolve().parents[2]
FILES = {"youtube": "yt", "x": "twtr", "telegram": "tel", "reddit": "reddit",
         "tiktok": "tiktok", "truthsocial": "truth"}


def collector(name):
    return importlib.import_module(f"src.collectors.{name}.collector")


class LegacyCollectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {name: collector(name) for name in FILES}

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.now = dt.datetime.now(dt.timezone.utc)
        for module in self.modules.values():
            self.stack.enter_context(patch.object(module, "detect_language", return_value=("en", 1.0)))
            self.stack.enter_context(patch.object(module, "analyze_text", return_value=(None, [])))
        from src.filtering import dedup as dedup_utils
        self.dedup = self.stack.enter_context(patch.object(dedup_utils, "check_and_register",
            return_value={"is_duplicate": False, "duplicate_of": None, "dedup_method": None}))

    def rows(self, name):
        return json.loads((self.directory / name).read_text(encoding="utf-8"))

    def test_youtube_sorted_records_rerun_and_duplicate_drop(self):
        m = self.modules["youtube"]
        target = self.directory / "youtube.json"
        def process(vid):
            published = self.now - dt.timedelta(minutes=int(vid[-1]))
            return vid, f"https://www.youtube.com/watch?v={vid}", {
                "created_dt": published, "upload_datetime": published.strftime(m.TIMESTAMP_FMT)
                if hasattr(m, "TIMESTAMP_FMT") else published.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "channel_id": "UCabcdefghijklmnopqrstuv", "channel": "Example", "title": vid}, "Oil prices moved today"
        with patch.object(m, "_process_single_video", side_effect=process) as fetch:
            m._fetch_and_write_videos(["abcdefghij1", "abcdefghij2"], str(target), [], None, {}, "test")
            rows = self.rows("youtube.json")
            self.assertEqual([r["Source"]["Source_id"] for r in rows], ["abcdefghij2", "abcdefghij1"])
            self.assertEqual(rows[0]["record_id"], "YouTube_UCabcdefghijklmnopqrstuv_abcdefghij2")
            before = target.read_bytes()
            fetch.reset_mock()
            m._fetch_and_write_videos(["abcdefghij1", "abcdefghij2"], str(target), [], None, {}, "test")
            fetch.assert_not_called()
            self.assertEqual(target.read_bytes(), before)
            self.dedup.return_value["is_duplicate"] = True
            m._fetch_and_write_videos(["abcdefghij3"], str(target), [], None, {}, "test")
            self.assertEqual(target.read_bytes(), before)

    def test_youtube_missing_text_and_fetch_error_have_no_file(self):
        m = self.modules["youtube"]
        with patch.object(m, "_process_single_video", return_value=("abcdefghijk", "url", {"title": "test"}, None)):
            m._fetch_and_write_videos(["abcdefghijk"], str(self.directory / "none.json"), [], None, {}, "test")
        self.assertFalse((self.directory / "none.json").exists())
        with patch.object(m, "fetch_video_metadata", side_effect=RuntimeError("offline failure")), patch.object(m._fetch_rate_limiter, "wait"):
            self.assertEqual(m._process_single_video("abcdefghijk")[2:], (None, None))

    def test_youtube_transcript_precedes_audio_fallback(self):
        m = self.modules["youtube"]
        api = NS(list=lambda _: NS(find_transcript=lambda _: NS(fetch=lambda: NS(to_raw_data=lambda: [{"text": "caption\nfirst"}]))))
        with patch.object(m, "YouTubeTranscriptApi", return_value=api), patch.object(m, "transcribe_audio") as audio:
            self.assertEqual(m.extract_video_text("https://www.youtube.com/watch?v=abcdefghijk"), "caption first")
            audio.assert_not_called()
        with patch.object(m, "YouTubeTranscriptApi", side_effect=None) as constructor, patch.object(m, "transcribe_audio", return_value="spoken") as audio:
            constructor.return_value.list.side_effect = RuntimeError("no subtitles")
            self.assertEqual(m.extract_video_text("https://www.youtube.com/watch?v=abcdefghijk", 90), "spoken")
            self.assertEqual(audio.call_args.kwargs["duration"], 90)

    def test_x_duplicate_retained_and_rerun_skips_fetch(self):
        m = self.modules["x"]
        target = self.directory / "x.json"
        tweet = {"text": "Oil prices moved today", "created_at": self.now.isoformat(),
                 "user": {"screen_name": "Reuters", "name": "Reuters"}}
        self.dedup.return_value["is_duplicate"] = True
        m._fetch_and_write_tweets([], str(target), [], None, {}, "test", prefetched=[("Reuters", "1799999999999999999", tweet)])
        row = self.rows("x.json")[0]
        self.assertEqual(row["record_id"], "X_Reuters_1799999999999999999")
        self.assertTrue(row["deduplication"]["is_duplicate"])
        before = target.read_bytes()
        with patch.object(m, "_fetch_tweet_safe") as fetch:
            m._fetch_and_write_tweets([("Reuters", "1799999999999999999")], str(target), [], None, {}, "test")
            fetch.assert_not_called()
        self.assertEqual(target.read_bytes(), before)

    def test_x_empty_old_and_untrusted_posts_are_skipped(self):
        m = self.modules["x"]
        posts = [("unknown", "1799999999999999999", {"text": "", "created_at": self.now.isoformat()}),
                 ("unknown", "1799999999999999998", {"text": "Old news", "created_at": (self.now - dt.timedelta(days=365)).isoformat()}),
                 ("unknown", "1799999999999999997", {"text": "Recent news", "created_at": self.now.isoformat()})]
        m._fetch_and_write_tweets([], str(self.directory / "none.json"), [], None, {}, "test", prefetched=posts, trusted={"Reuters"})
        self.assertFalse((self.directory / "none.json").exists())
        self.dedup.assert_not_called()

    def test_tiktok_pinned_old_video_does_not_end_listing(self):
        m = self.modules["tiktok"]
        self.dedup.return_value["is_duplicate"] = True
        def fetch(url):
            old = url.endswith("7300000000000000000")
            return {"timestamp": (self.now - dt.timedelta(days=365) if old else self.now).timestamp(), "description": "oil prices"}, "oil prices"
        with patch.object(m, "list_account_videos", return_value=["7300000000000000000", "7300000000000000001"]), patch.object(m, "fetch_video", side_effect=fetch) as fetched, patch.object(m, "extract_video_text", return_value=("oil prices", True, [])), patch.object(m._fetch_rate_limiter, "wait"):
            result = m.scrape_account("reuters", None, {}, keywords=["oil", "prices"], output_dir=str(self.directory))
            self.assertEqual(len(result), 1)
            self.assertFalse((self.directory / "tiktok_prices.json").exists())
            row = self.rows("tiktok_oil.json")[0]
            self.assertEqual(row["record_id"], "TikTok_reuters_7300000000000000001")
            self.assertTrue(row["deduplication"]["is_duplicate"])
            before = (self.directory / "tiktok_oil.json").read_bytes()
            fetched.reset_mock()
            self.assertIsNone(m.scrape_account("reuters", None, {}, keywords=["oil", "prices"], output_dir=str(self.directory)))
            # The old pin was never saved and can be fetched again; the stored video cannot.
            self.assertEqual([c.args[0] for c in fetched.call_args_list], ["https://www.tiktok.com/@reuters/video/7300000000000000000"])
            self.assertEqual((self.directory / "tiktok_oil.json").read_bytes(), before)

    def test_tiktok_empty_text_and_listing_failure(self):
        m = self.modules["tiktok"]
        with patch.object(m, "list_account_videos", return_value=["7300000000000000001"]), patch.object(m, "fetch_video", return_value=({}, None)), patch.object(m, "extract_video_text", return_value=(None, False, ["missing"])), patch.object(m._fetch_rate_limiter, "wait"):
            self.assertIsNone(m.scrape_account("reuters", None, {}, output_dir=str(self.directory)))
        self.assertEqual(list(self.directory.glob("*.json")), [])
        with patch.object(m, "list_account_videos", side_effect=RuntimeError("blocked")):
            self.assertIsNone(m.scrape_account("reuters", None, {}, output_dir=str(self.directory)))

    def test_telegram_edit_refresh_in_place_duplicate_retained(self):
        m = self.modules["telegram"]
        client = NS(get_entity=AsyncMock(return_value=NS(username="reuters", title="Reuters")))
        message = NS(id=42, raw_text="Oil prices moved today", date=self.now, edit_date=None)
        self.dedup.return_value["is_duplicate"] = True
        with patch.object(m, "_collect_messages", new=AsyncMock(return_value=[message])), patch.object(m, "REFRESH_EDITED_MESSAGES", True):
            asyncio.run(m.scrape_channel(client, "alias", None, {}, output_dir=str(self.directory)))
            row = self.rows("telegram_alias.json")[0]
            self.assertEqual(row["record_id"], "Telegram_reuters_42")
            self.assertTrue(row["deduplication"]["is_duplicate"])
            message.raw_text = "Updated oil report"
            message.edit_date = self.now + dt.timedelta(minutes=1)
            asyncio.run(m.scrape_channel(client, "alias", None, {}, output_dir=str(self.directory)))
            rows = self.rows("telegram_alias.json")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Content"]["raw_text"], "Updated oil report")
            self.assertEqual(rows[0]["time_stamps"]["published_at"], row["time_stamps"]["published_at"])

    def test_telegram_no_public_username_or_empty_text(self):
        m = self.modules["telegram"]
        client = NS(get_entity=AsyncMock(return_value=NS(username=None)))
        self.assertIsNone(asyncio.run(m.scrape_channel(client, "alias", None, {}, output_dir=str(self.directory))))
        client.get_entity.return_value = NS(username="reuters", title="Reuters")
        with patch.object(m, "_collect_messages", new=AsyncMock(return_value=[NS(id=42, raw_text="", message="")])):
            asyncio.run(m.scrape_channel(client, "alias", None, {}, output_dir=str(self.directory)))
        self.assertEqual(list(self.directory.glob("*.json")), [])

    def submission(self, ident, title, age=0):
        return NS(id=ident, subreddit="worldnews", title=title, selftext="", created_utc=(self.now - dt.timedelta(days=age)).timestamp(), permalink=f"/r/worldnews/comments/{ident}/test/", edited=False)

    def test_reddit_title_only_rerun_and_duplicate_drop(self):
        m = self.modules["reddit"]
        target = self.directory / "reddit.json"
        post = self.submission("1abc2de", "Oil prices moved today")
        m._merge_submissions([post], str(target), "oil", None, {}, "test")
        row = self.rows("reddit.json")[0]
        self.assertEqual(row["Content"]["raw_text"], post.title)
        self.assertEqual(row["record_id"], "Reddit_worldnews_1abc2de")
        before = target.read_bytes()
        self.dedup.reset_mock()
        m._merge_submissions([post], str(target), "oil", None, {}, "test")
        self.dedup.assert_not_called()
        self.dedup.return_value["is_duplicate"] = True
        m._merge_submissions([self.submission("1abc2df", "Oil prices moved today")], str(target), "oil", None, {}, "test")
        self.assertEqual(target.read_bytes(), before)

    def test_reddit_empty_and_old_posts_have_no_file(self):
        m = self.modules["reddit"]
        m._merge_submissions([self.submission("1abc2de", ""), self.submission("1abc2df", "Old news", 365)], str(self.directory / "none.json"), None, None, {}, "test")
        self.assertFalse((self.directory / "none.json").exists())
        self.dedup.assert_not_called()

    def test_truth_repost_identity_media_missing_and_duplicate_retained(self):
        m = self.modules["truthsocial"]
        statuses = [{"id": "109999999999999999", "created_at": self.now.isoformat(), "reblog": {"content": "<p>Oil &amp; gas</p>", "media_attachments": []}},
                    {"id": "109999999999999998", "created_at": self.now.isoformat(), "content": "", "media_attachments": []}]
        self.dedup.return_value["is_duplicate"] = True
        with patch.object(m, "lookup_account", return_value={"id": "10", "username": "renamed"}), patch.object(m, "fetch_statuses", return_value=statuses):
            m.scrape_account("oldname", "fake-token", None, {}, output_dir=str(self.directory))
            rows = self.rows("truthsocial_renamed.json")
            self.assertEqual(rows[0]["record_id"], "TruthSocial_renamed_109999999999999999")
            self.assertEqual(rows[0]["Content"]["raw_text"], "Oil & gas")
            self.assertTrue(rows[0]["deduplication"]["is_duplicate"])
            self.assertEqual(rows[1]["Content"]["raw_text"], "[media-only post with no text]")
            self.assertLess(rows[1]["quality"]["quality_score"], 100)
            before = (self.directory / "truthsocial_renamed.json").read_bytes()
            self.assertIsNone(m.scrape_account("oldname", "fake-token", None, {}, output_dir=str(self.directory)))
            self.assertEqual((self.directory / "truthsocial_renamed.json").read_bytes(), before)

    def test_truth_resolve_failure_has_no_file(self):
        m = self.modules["truthsocial"]
        with patch.object(m, "lookup_account", side_effect=RuntimeError("offline denied")), patch.object(m, "fetch_statuses") as fetch:
            self.assertIsNone(m.scrape_account("reuters", "fake-token", None, {}, output_dir=str(self.directory)))
            fetch.assert_not_called()
        self.assertEqual(list(self.directory.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
