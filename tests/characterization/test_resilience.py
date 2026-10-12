"""Additional boundary cases also exercised against the saved original files."""
import asyncio
import datetime as dt
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error

from tests.characterization.test_collectors import collector



class Resilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {name: collector(name) for name in ("youtube", "telegram", "tiktok", "truthsocial")}

    def test_youtube_search_trusted_preference_fallback_and_cap(self):
        m = self.modules["youtube"]
        entries = [{"id": "abcdefghij1", "uploader": "Other"}, {"id": "abcdefghij2", "uploader": "Reuters"}]
        with patch.object(m.yt_dlp, "YoutubeDL") as ydl, patch.object(m.time, "sleep"):
            ydl.return_value.__enter__.return_value.extract_info.return_value = {"entries": entries}
            self.assertEqual(m.search_youtube_videos("oil", ["Reuters"], 1), ["abcdefghij2"])
            self.assertEqual(m.search_youtube_videos("oil", ["not-found"], 1), ["abcdefghij1"])
            self.assertTrue(ydl.return_value.__enter__.return_value.extract_info.call_args.args[0].startswith("ytsearch30:oil news after:"))

    def test_youtube_exhausted_search_and_channel_quota(self):
        m = self.modules["youtube"]
        with patch.object(m.yt_dlp, "YoutubeDL") as ydl, patch.object(m.time, "sleep"), patch.object(m, "SEARCH_MAX_RETRIES", 2):
            extract = ydl.return_value.__enter__.return_value.extract_info
            extract.side_effect = RuntimeError("offline failure")
            self.assertEqual(m.search_youtube_videos("oil", []), [])
            self.assertEqual(extract.call_count, 2)
            extract.side_effect = None
            extract.return_value = {"entries": [{"id": "abcdefghij1"}, {"id": "abcdefghij2"}]}
            self.assertEqual(m.list_channel_uploads("UCabcdefghijklmnopqrstuv", 1), ["abcdefghij1"])
            self.assertEqual(ydl.call_args.args[0]["playlistend"], 1)

    def test_tiktok_caption_audio_description_missing_hierarchy(self):
        m = self.modules["tiktok"]
        info = {"id": "7300000000000000001", "description": "fallback description", "duration": 60}
        with patch.object(m, "transcribe_audio", return_value="spoken") as audio:
            self.assertEqual(m.extract_video_text("url", info, "caption"), ("caption", True, []))
            audio.assert_not_called()
            self.assertEqual(m.extract_video_text("url", info, None), ("spoken", True, []))
            audio.return_value = None
            text, complete, errors = m.extract_video_text("url", info, None)
            self.assertEqual(text, "fallback description")
            self.assertFalse(complete)
            self.assertTrue(errors)
            self.assertIsNone(m.extract_video_text("url", {}, None)[0])

    def test_tiktok_vtt_markup_and_consecutive_repeat(self):
        m = self.modules["tiktok"]
        self.assertEqual(m._vtt_to_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\n<b>Oil news</b>\n\n2\n00:00:01.000 --> 00:00:02.000\nOil news\nNew report"), "Oil news New report")

    def test_telegram_flood_retry_honors_buffer_and_exhaustion(self):
        m = self.modules["telegram"]
        class Flood(Exception):
            seconds = 3
        with patch.object(m, "FloodWaitError", Flood), patch.object(m, "MAX_FLOOD_RETRIES", 2), patch.object(m, "FLOOD_WAIT_BUFFER", 1), patch.object(m.asyncio, "sleep", new=AsyncMock()) as sleep:
            operation = AsyncMock(side_effect=[Flood(), "ok"])
            self.assertEqual(asyncio.run(m._with_flood_retry(operation, "test")), "ok")
            sleep.assert_awaited_once_with(4)
            sleep.reset_mock()
            operation = AsyncMock(side_effect=Flood())
            with self.assertRaises(Flood):
                asyncio.run(m._with_flood_retry(operation, "test"))
            self.assertEqual(operation.await_count, 2)
            sleep.assert_awaited_once_with(4)

    def test_telegram_cutoff_skips_missing_date_and_stops_old(self):
        m = self.modules["telegram"]
        now = dt.datetime.now(dt.timezone.utc)
        messages = [NS(id=1, date=None), NS(id=2, date=now), NS(id=3, date=now - dt.timedelta(days=365)), NS(id=4, date=now)]
        async def listing(*args, **kwargs):
            for item in messages:
                yield item
        client = NS(iter_messages=MagicMock(side_effect=listing))
        result = asyncio.run(m._collect_messages(client, "entity", 7, now - dt.timedelta(minutes=1)))
        self.assertEqual([msg.id for msg in result], [2])
        self.assertEqual(client.iter_messages.call_args.kwargs["min_id"], 7)

    def test_truth_partial_page_failure_keeps_prior_results(self):
        m = self.modules["truthsocial"]
        now = dt.datetime.now(dt.timezone.utc)
        row = {"id": "109999999999999999", "created_at": now.isoformat()}
        with patch.object(m, "_api_request", side_effect=[[row], RuntimeError("second page failed")]) as request, patch.object(m._fetch_rate_limiter, "wait"):
            self.assertEqual(m.fetch_statuses("10", "fake", now - dt.timedelta(minutes=1)), [row])
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args.kwargs["params"]["max_id"], row["id"])

    def test_truth_permanent_auth_error_not_retried_transient_retried(self):
        m = self.modules["truthsocial"]
        with patch.object(m.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("https://example.com", 401, "denied", {}, None)) as request:
            with self.assertRaises(urllib.error.HTTPError):
                m._api_request("/test", token="fake")
            request.assert_called_once()
        with patch.object(m.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("https://example.com", 503, "temporary", {}, None)) as request, patch.object(m.time, "sleep"):
            with self.assertRaises(m._RetryableApiError):
                m._api_request("/test", token="fake")
            self.assertEqual(request.call_count, 3)

    def test_truth_time_budget_keeps_partial_data(self):
        m = self.modules["truthsocial"]
        now = dt.datetime.now(dt.timezone.utc)
        row = {"id": "109999999999999999", "created_at": now.isoformat()}
        with patch.object(m.time, "monotonic", side_effect=[0, 0, 2]), patch.object(m, "ACCOUNT_TIME_BUDGET", 1), patch.object(m, "_api_request", return_value=[row]) as request, patch.object(m._fetch_rate_limiter, "wait"):
            self.assertEqual(m.fetch_statuses("10", "fake", now - dt.timedelta(minutes=1)), [row])
            request.assert_called_once()

    def test_real_dedup_exact_near_reload_and_self_update(self):
        from src.filtering import dedup as dedup_utils
        with tempfile.TemporaryDirectory() as directory, patch.object(dedup_utils, "DB_PATH", str(Path(directory) / "dedup.db")):
            lsh, hashes = dedup_utils.load_lsh()
            text = "Oil prices rose as traders reviewed the latest global supply report today."
            original = dedup_utils.check_and_register("first", text, lsh, hashes)
            self.assertFalse(original["is_duplicate"])
            exact = dedup_utils.check_and_register("second", text, lsh, hashes)
            self.assertTrue(exact["is_duplicate"])
            self.assertEqual(exact["original_record_id"], "first")
            updated = dedup_utils.check_and_register("first", "A completely different solar research announcement was published.", lsh, hashes)
            self.assertFalse(updated["is_duplicate"])
            reloaded, hashes = dedup_utils.load_lsh()
            repeated = dedup_utils.check_and_register("third", text, reloaded, hashes)
            self.assertTrue(repeated["is_duplicate"])
            near = dedup_utils.check_and_register("fourth", text + " Updated.", reloaded, hashes)
            self.assertTrue(near["is_duplicate"])


if __name__ == "__main__":
    unittest.main()
