"""Behavioral acquisition checks with synthetic candidates and provider fixtures."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import io
import os
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch

from engine.acquisition import AcquisitionEngine, query_jobs
from engine.acquisition_cli import draft_from_entry, main
from engine.registry import Registry
from src.acquisition.browser_adapters import candidate_from_row, FacebookGroupAdapter, TikTokSearchAdapter
from src.acquisition.google import GoogleSocialAdapter, google_query
from src.acquisition.identity import identify, identity, text_hash, hashtag_query, resolve_redirects
from src.acquisition.models import (AdapterError, AccessProbeResult, Candidate, CandidateBatch, Deadline, DiscoveryRequest, FetchContext, FetchResult, Window, parse_utc)
from src.acquisition.prefilter import apply_prefilter
from src.acquisition.youtube import YouTubeItemAdapter
from src.browser.profiles import PROJECT_ROOT
from src.storage.acquisition import AcquisitionStore

WINDOW = Window(parse_utc("2026-10-08T00:00:00Z"), parse_utc("2026-10-08T03:00:00Z"))


def item(text="Cổng công trường đông", item_id="123", platform="facebook", run_id="run_test"):
    url = f"https://www.facebook.com/groups/139108668844789/posts/{item_id}" if platform == "facebook" else f"https://www.tiktok.com/@demo/video/{item_id}"
    target = identify(url)
    return Candidate(platform, url, target.url, "fb_group_139108668844789" if platform == "facebook" else "tt_search_vincons", run_id, "FACEBOOK_GROUP_BROWSER" if platform == "facebook" else "TIKTOK_KEYWORD_BROWSER", platform_item_id=item_id, origin_source_ref=target.origin, caption=text, published_at="2026-10-08T01:00:00Z", publication_precision="INSTANT", window_status="IN_WINDOW")


def request(source=None, **kwargs):
    source = source or dict(source_id="fb_group_139108668844789", platform="facebook", source_type="FACEBOOK_GROUP", url="https://www.facebook.com/groups/139108668844789", platform_group_ref="139108668844789")
    return DiscoveryRequest(source, "run_test", WINDOW, Deadline(120), "RECENT_SOURCE_ITEMS", **kwargs)


class FixtureAdapter:
    def __init__(self, candidates, status="SUCCESS", fetch_error=None):
        self.candidates, self.status, self.fetch_error = candidates, status, fetch_error
        self.fetch_calls = []

    def probe_access(self, source):
        return AccessProbeResult("ACCESSIBLE")

    def discover(self, req):
        return CandidateBatch(candidates=[replace(c, crawl_run_id=req.crawl_run_id, candidate_id=c.candidate_id+req.crawl_run_id+req.source["source_id"]+(req.query_id or ""), source_id=req.source["source_id"], query_id=req.query_id, query_type=req.query_type, search_keyword=req.search_keyword) for c in self.candidates], status=self.status, error_code="PARSER_CHANGED" if self.status == "PARTIAL" else None)

    def fetch_item(self, candidate, context):
        self.fetch_calls.append(candidate.platform_item_id)
        if self.fetch_error:
            raise self.fetch_error
        candidate.raw_text = candidate.caption
        candidate.extraction_status = "FETCHED"
        return FetchResult(candidate)


class AcquisitionTests(unittest.TestCase):
    def test_recruitment_only_in_google_snippet_never_fetches_or_queues(self):
        ad = item(None)
        ad.discovered_via = "GOOGLE_SERPAPI"
        ad.title = "Ms Thương"
        ad.search_snippet = "VINCONS tiếp nhận thông tin nhân sự cơ điện. Phụ cấp ăn trưa 60k/ngày."
        adapter = FixtureAdapter([ad])
        outcome = self.run_fixture(adapter)["jobs"][0]
        self.assertEqual(outcome["counters"]["prefilter_drop"], 1)
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.list_queue(), [])
        rejection = self.store.db.execute("SELECT payload FROM rejections").fetchone()[0]
        self.assertNotIn("Ms Thương", rejection)
        self.assertNotIn("60k", rejection)

    def test_live_recruitment_wordings_drop_before_fetch(self):
        examples = ["Tháng này thiếu thợ, tìm gấp 20 công nhân đi làm ngay. Thu nhập 16-33tr, bao ăn ở",
                    "Công ty mình tuyển đội thi công công trình #VieclamTanuyen",
                    "Cần tuyển thêm 10 lao động phổ thông", "Tuyển gấp 20 nam/nữ nhân viên"]
        for caption in examples:
            with self.subTest(caption=caption):
                adapter = FixtureAdapter([item(caption)])
                outcome = self.run_fixture(adapter)["jobs"][0]
                self.assertEqual(outcome["counters"]["prefilter_drop"], 1)
                self.assertEqual(adapter.fetch_calls, [])
                self.assertEqual(self.store.export_records(), [])
        for caption in ["Cảnh báo lừa đảo tuyển đội thi công", "Phản ánh tuyển công nhân nhưng nợ lương",
                        "Cổng công trường kẹt xe trong buổi tuyển công nhân", "Trao đổi ca làm ngày mai"]:
            self.assertEqual(apply_prefilter(item(caption)), "REVIEW")

    def test_existing_full_recruitment_is_purged_before_reuse(self):
        stale = item("Công ty mình tuyển đội thi công công trình")
        stale.prefilter_decision = "PASS"
        stale.extraction_status = "FETCHED"
        stale.raw_text = stale.caption
        self.store.save_candidate(stale)
        adapter = FixtureAdapter([item(None)])
        outcome = self.run_fixture(adapter)["jobs"][0]
        self.assertEqual(outcome["counters"]["prefilter_drop"], 1)
        self.assertEqual(outcome["counters"]["existing"], 0)
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.export_records(), [])

    def test_numeric_gender_recruitment_never_fetches_or_persists_raw(self):
        for caption in ("Tuyển 50 nam công nhân xây dựng", "Tuyển 20 nữ nhân viên", "Tuyển gấp 30 nam/nữ công nhân"):
            with self.subTest(caption=caption):
                adapter = FixtureAdapter([item(caption)])
                result = self.run_fixture(adapter)
                self.assertEqual(result["jobs"][0]["counters"]["prefilter_drop"], 1)
                self.assertEqual(adapter.fetch_calls, [])
                self.assertEqual(self.store.export_records(), [])
        self.assertEqual(apply_prefilter(item("Cảnh báo lừa đảo tuyển 50 nam công nhân")), "REVIEW")

    def test_facebook_comment_permalink_cannot_identify_source_post(self):
        row = dict(links=["https://www.facebook.com/groups/139108668844789/posts/123/?comment_id=456"], caption="Comment text", datetime="2026-10-08T01:00:00Z")
        self.assertIsNone(candidate_from_row(row, request(), "facebook"))
        row["links"].append("https://www.facebook.com/groups/139108668844789/posts/123/")
        self.assertEqual(candidate_from_row(row, request(), "facebook").platform_item_id, "123")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.store = AcquisitionStore(self.directory / "acquisition.sqlite3")
        self.registry = Registry(PROJECT_ROOT / "config")
        self.watchlist = deepcopy(self.registry.watchlists["vincons_acquisition_v1"])
        self.watchlist["enabled"] = True
        self.registry.watchlists["vincons_acquisition_v1"] = self.watchlist
        self.source = self.registry.sources["fb_group_139108668844789"]
        self.source.update(enabled=True, verification_status="VERIFIED", access_type="PUBLIC", access_verified=True, requires_login=False)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def engine(self, adapter):
        @contextmanager
        def factory(source, deadline, store):
            yield adapter
        return AcquisitionEngine(self.registry, self.store, factory)

    def run_fixture(self, adapter, source_ids=None):
        return self.engine(adapter).run("vincons_acquisition_v1", WINDOW, source_ids or [self.source["source_id"]])

    def test_ad_ac_01_disabled_and_unverified_do_not_launch(self):
        adapter = FixtureAdapter([item()])
        self.source["enabled"] = False
        report = self.run_fixture(adapter)
        self.assertEqual(report["error_code"], "NO_ELIGIBLE_SOURCE")
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.export_records(), [])

    def test_ad_ac_02_half_open_window_and_unknown(self):
        self.assertEqual(WINDOW.status("2026-10-08T00:00:00Z", "INSTANT"), "IN_WINDOW")
        self.assertEqual(WINDOW.status("2026-10-08T03:00:00Z", "INSTANT"), "OUT_OF_WINDOW")
        self.assertEqual(WINDOW.status(None, "UNKNOWN"), "UNKNOWN")
        self.assertEqual(WINDOW.status("2026-10-08T01:00:00Z", "APPROXIMATE"), "UNKNOWN")
        with self.assertRaises(ValueError):
            parse_utc("2026-10-08T00:00:00")

    def test_fb_ac_04_old_pinned_does_not_stop_new_post(self):
        old = item(item_id="old")
        old.window_status = "OUT_OF_WINDOW"
        adapter = FixtureAdapter([old, item(item_id="new")])
        report = self.run_fixture(adapter)
        self.assertEqual(adapter.fetch_calls, ["new"])
        self.assertEqual(report["jobs"][0]["counters"]["out_of_window"], 1)

    def test_ad_ac_05_drop_never_fetches_or_persists_raw(self):
        adapter = FixtureAdapter([item("Tuyển công nhân cơ hữu, nhận hồ sơ ứng tuyển")])
        report = self.run_fixture(adapter)
        self.assertEqual(report["jobs"][0]["status"], "SUCCESS")
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.list_queue(), [])
        rows = [json.loads(row[0]) for row in self.store.db.execute("SELECT payload FROM rejections")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), set(item().rejection()))
        self.assertNotIn("nhận hồ sơ", json.dumps(rows, ensure_ascii=False))

    def test_exclusion_intents_and_mixed_complaints(self):
        for text, expected in [
            ("Bán căn hộ, liên hệ để nhận bảng giá", "DROP"),
            ("Tuyển công nhân cơ hữu, nhận hồ sơ ứng tuyển", "DROP"),
            ("Cần mua xe máy, ai thanh lý liên hệ", "DROP"),
            ("Đổi xe lấy máy tính, bù tiền theo thỏa thuận", "DROP"),
            ("Mua ngay, khuyến mãi chốt đơn", "DROP"),
            ("Nhân viên bán hàng không phản hồi phản ánh của tôi", "REVIEW"),
            ("Cổng công trường ùn, công nhân chờ vào trong buổi tuyển dụng", "REVIEW"),
            ("Trao đổi ca làm ngày mai", "REVIEW"),
            ("Tôi đã trao đổi với quản lý nhưng chưa xử lý", "REVIEW"),
            (None, "REVIEW"),
            ("Tin tuyển dụng", "DROP"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(apply_prefilter(item(text)), expected)

    def test_explicit_offers_without_contact_and_protected_complaints(self):
        for text, expected in [
            ("VinCons tuyển dụng công nhân", "DROP"),
            ("#Vincons tuyển dụng CÔNG TY CPPT & DT XD", "DROP"),
            ("Cơ hội việc làm cho mọi người", "DROP"),
            ("Cho thuê xe máy", "DROP"),
            ("Cần thuê phòng gần công trường", "DROP"),
            ("Cho vay tiền nhanh", "DROP"),
            ("Cần vay vốn", "DROP"),
            ("Mua bán nợ", "DROP"),
            ("Công ty nợ lương khiến tôi phải vay tiền", "REVIEW"),
            ("Cảnh báo lừa đảo cho vay tiền", "REVIEW"),
            ("Phản ánh tuyển dụng không trả lương", "REVIEW"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(apply_prefilter(item(text)), expected)
        candidate = item(None)
        candidate.title = "Vincons Cần Giờ"
        candidate.search_snippet = "Tổ Sơn Bả ▻ TUYỂN DỤNG CÔNG NHÂN CƠ HỮU VINCONS. Làm cho Vin chủ nhật đông hơn."
        self.assertEqual(apply_prefilter(candidate), "REVIEW")
        candidate.title = "Mời anh em vào thăm ký túc xá"
        candidate.search_snippet = "𝐕𝐈𝐍𝐂𝐎𝐍𝐒 𝐓𝐔𝐘Ể𝐍 𝐆Ấ𝐏 100.000 𝐂Ô𝐍𝐆 𝐍𝐇Â𝐍 xây dựng"
        self.assertEqual(apply_prefilter(candidate), "DROP")

    def test_expanded_exclusions_do_not_fetch_or_queue(self):
        adapter = FixtureAdapter([item("Cho thuê xe", item_id="rent"), item("Cho vay tiền", item_id="loan"), item("VinCons tuyển dụng công nhân", item_id="recruit")])
        report = self.run_fixture(adapter)
        self.assertEqual(report["jobs"][0]["counters"]["prefilter_drop"], 3)
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.list_queue(), [])

    def test_ad_ac_04_rerun_native_identity_many_observations(self):
        adapter = FixtureAdapter([item()])
        self.run_fixture(adapter)
        self.run_fixture(adapter)
        self.assertEqual(len(self.store.export_records()), 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 2)
        self.assertEqual(adapter.fetch_calls, ["123"])

    def test_ad_ac_08_partial_keeps_items_and_next_source_runs(self):
        source2 = self.registry.sources["fb_group_1675953926771851"]
        source2.update(enabled=True, verification_status="VERIFIED", access_verified=True, requires_login=False)
        adapter = FixtureAdapter([item()], status="PARTIAL")
        report = self.run_fixture(adapter, [self.source["source_id"], source2["source_id"]])
        self.assertEqual(len(report["jobs"]), 2)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(len(self.store.export_records()), 1)

    def test_ad_ac_07_empty_and_parser_failure_differ(self):
        for status in ("NO_NEW_DATA", "EXTRACTION_FAILED"):
            report = self.run_fixture(FixtureAdapter([], status=status))
            self.assertEqual(report["jobs"][0]["status"], status)

    def test_unknown_time_metadata_retained_as_review(self):
        candidate = item(None)
        candidate.published_at = None
        candidate.publication_precision = "UNKNOWN"
        candidate.window_status = "UNKNOWN"
        self.run_fixture(FixtureAdapter([candidate]))
        saved = self.store.export_records()[0]["candidate"]
        self.assertEqual(saved["prefilter_decision"], "REVIEW")
        self.assertIsNone(saved["engagement"]["likes"])
        self.assertIsNone(saved["published_at"])

    def test_ad_ac_11_empty_text_never_merges_distinct_ids(self):
        for key in ("1", "2"):
            candidate = item(None, key)
            apply_prefilter(candidate)
            self.store.save_candidate(candidate)
        self.assertEqual(len(self.store.export_records()), 2)
        self.assertIsNone(text_hash("😀  "))

    def test_metadata_only_failure_retries_on_rerun(self):
        failing = FixtureAdapter([item()], fetch_error=AdapterError("SOURCE_UNAVAILABLE", "ITEM_NOT_FOUND"))
        self.run_fixture(failing)
        healthy = FixtureAdapter([item()])
        self.run_fixture(healthy)
        self.assertEqual(healthy.fetch_calls, ["123"])
        self.assertEqual(len(self.store.export_records()), 1)

    def test_auth_failure_stops_fetch_but_retains_metadata(self):
        adapter = FixtureAdapter([item(item_id="1"), item(item_id="2")], fetch_error=AdapterError("AUTH_REQUIRED", "SESSION_EXPIRED"))
        report = self.run_fixture(adapter)
        self.assertEqual(adapter.fetch_calls, ["1"])
        self.assertEqual(len(self.store.export_records()), 2)
        self.assertEqual(report["jobs"][0]["status"], "PARTIAL")

    def test_dq_ac_01_google_outside_registry_pending_no_fetch(self):
        candidate = item("Phản ánh cổng công trường", platform="tiktok")
        candidate.discovered_via = "GOOGLE_SERPAPI"
        counters = dict(prefilter_pass=0,prefilter_drop=0,prefilter_review=0,queued=0,out_of_window=0,existing=0)
        adapter = FixtureAdapter([])
        self.engine(adapter).process_candidate(candidate, request(), self.watchlist, adapter, counters)
        self.assertEqual(adapter.fetch_calls, [])
        entry = self.store.list_queue()[0]
        self.assertEqual(entry["status"], "PENDING")
        self.assertEqual(entry["reason"], "UNAPPROVED_SOURCE")

    def test_dq_ac_06_rejected_rediscovery_does_not_reopen(self):
        candidate = item()
        apply_prefilter(candidate)
        key = self.store.enqueue(candidate, "UNAPPROVED_SOURCE", "FACEBOOK_GROUP")
        self.store.review(key, "REJECTED", "reviewer", "out of scope")
        self.store.enqueue(replace(candidate, candidate_id="another"), "UNAPPROVED_SOURCE", "FACEBOOK_GROUP")
        self.assertEqual(self.store.queue_entry(key)["status"], "REJECTED")
        self.store.review(key, "PENDING", "reviewer", "reconsider")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM review_history").fetchone()[0], 2)

    def test_dq_ac_02_approval_draft_stays_disabled(self):
        candidate = item()
        apply_prefilter(candidate)
        key = self.store.enqueue(candidate, "UNAPPROVED_SOURCE", "FACEBOOK_GROUP")
        source = draft_from_entry(self.store.queue_entry(key), "new_source")
        self.store.save_draft(source)
        self.store.review(key, "APPROVED", "reviewer", "group manually resolved", "new_source")
        self.assertFalse(self.store.draft_sources()[0]["enabled"])
        self.assertEqual(self.store.queue_entry(key)["dispatch_state"], "NOT_READY")

    def test_dq_ac_03_explicit_process_fetches_ready_item_without_nested_profile(self):
        candidate = item("Cổng đông")
        candidate.discovered_via = "GOOGLE_SERPAPI"
        apply_prefilter(candidate)
        key = self.store.enqueue(candidate, "SOURCE_NOT_READY", "FACEBOOK_GROUP")
        self.store.review(key, "APPROVED", "reviewer", "same group", self.source["source_id"])
        adapter = FixtureAdapter([])
        result = self.engine(adapter).process_discovery(key, "vincons_acquisition_v1", WINDOW)
        self.assertEqual(result["status"], "FETCHED")
        self.assertEqual(adapter.fetch_calls, ["123"])
        self.assertEqual(self.store.export_records()[0]["candidate"]["discovered_via"], "GOOGLE_SERPAPI")

    def test_dq_ac_04_disabled_target_never_fetches(self):
        candidate = item()
        apply_prefilter(candidate)
        key = self.store.enqueue(candidate, "SOURCE_NOT_READY", "FACEBOOK_GROUP")
        self.store.review(key, "APPROVED", "reviewer", "same group", self.source["source_id"])
        self.source["enabled"] = False
        adapter = FixtureAdapter([])
        with self.assertRaises(ValueError):
            self.engine(adapter).process_discovery(key, "vincons_acquisition_v1", WINDOW)
        self.assertEqual(adapter.fetch_calls, [])

    def test_dq_ac_08_container_does_not_create_content_or_drop_on_name(self):
        target = identify("https://www.facebook.com/groups/139108668844789?ref=share")
        candidate = Candidate("facebook", target.url, target.url, "google", "run", "GOOGLE_SERPAPI", candidate_kind=target.kind, title="TUYỂN DỤNG CÔNG NHÂN", origin_source_ref=target.origin)
        self.assertEqual(apply_prefilter(candidate), "REVIEW")
        self.store.enqueue(candidate, "CONTAINER_DISCOVERY", "FACEBOOK_GROUP")
        self.assertEqual(self.store.export_records(), [])

    def test_gg_ac_14_existing_tiktok_observation_no_refetch_or_creator_approval(self):
        candidate = item(platform="tiktok")
        apply_prefilter(candidate)
        self.store.save_candidate(candidate)
        discovered = replace(candidate, candidate_id="google_obs", discovered_via="GOOGLE_SERPAPI")
        counters = dict(prefilter_pass=0,prefilter_drop=0,prefilter_review=0,queued=0,out_of_window=0,existing=0)
        adapter = FixtureAdapter([])
        self.engine(adapter).process_candidate(discovered, request(), self.watchlist, adapter, counters)
        self.assertEqual(adapter.fetch_calls, [])
        self.assertEqual(self.store.list_queue(), [])
        self.assertNotIn("demo", self.registry.sources)

    def test_reapply_drop_purges_existing_raw_and_queue(self):
        candidate = item()
        apply_prefilter(candidate)
        self.store.save_candidate(candidate)
        discovery_id = self.store.enqueue(candidate, "SOURCE_NOT_READY", "FACEBOOK_GROUP")
        self.store.review(discovery_id, "REJECTED", "reviewer", "deferred scope")
        candidate.caption = "Cần bán xe, liên hệ giá rẻ"
        self.assertEqual(apply_prefilter(candidate), "DROP")
        self.store.reject(candidate)
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.list_queue(), [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM review_history").fetchone()[0], 0)

    def test_gg_ac_07_persistent_month_run_and_retry_caps(self):
        self.assertTrue(self.store.reserve_request("run1", run_cap=1, month_cap=2))
        self.assertFalse(self.store.reserve_request("run1", run_cap=1, month_cap=2))
        self.assertTrue(self.store.reserve_request("run2", month_cap=2))
        self.store.close()
        self.store = AcquisitionStore(self.directory / "acquisition.sqlite3")
        self.assertFalse(self.store.reserve_request("run3", month_cap=2))

    def test_job_lock_excludes_concurrent_job_and_releases_on_error(self):
        with self.store.job_lock("same") as first:
            self.assertTrue(first)
            with self.store.job_lock("same") as second:
                self.assertFalse(second)
        with self.store.job_lock("same") as third:
            self.assertTrue(third)

    def test_query_jobs_keyword_hashtag_unicode_google_six_targets(self):
        queries = [dict(query_set_id="test", discovery_terms=["VinCons kẹt xe"], hashtags=["#VinCons"])]
        jobs = list(query_jobs(dict(source_type="TIKTOK_SEARCH", platform="tiktok"), queries))
        self.assertEqual(jobs[0]["search_keyword"], "VinCons kẹt xe")
        self.assertEqual(jobs[1]["effective_query"], "VinCons")
        self.assertEqual(jobs[1]["search_keyword"], "#VinCons")
        google = list(query_jobs(dict(source_type="GOOGLE_SEARCH", platform="google"), queries))
        self.assertEqual(len(google), 6)
        self.assertEqual(len({x["query_id"] for x in google}), 6)
        with self.assertRaises(ValueError):
            hashtag_query("#Vin Cons")

    def test_browser_card_identity_slug_unknown_time_and_caption(self):
        source = dict(source_id="fb_group_suanhathuduc", platform_group_ref="suanhathuduc")
        req = request(source)
        parsed = candidate_from_row(dict(links=["https://www.facebook.com/groups/suanhathuduc/posts/123"], caption=None, time_raw="2 giờ trước"), req, "facebook")
        self.assertEqual(parsed.source_id, "fb_group_suanhathuduc")
        self.assertIsNone(parsed.published_at)
        self.assertEqual(parsed.window_status, "UNKNOWN")
        self.assertIsNone(parsed.engagement["likes"])

    def test_youtube_unknown_channel_stays_pending(self):
        target = identify("https://youtu.be/abcdefghijk")
        candidate = Candidate("youtube", target.url, target.url, "google", "run", "GOOGLE_SERPAPI", platform_item_id=target.item_id)
        self.assertIsNone(candidate.origin_source_ref)
        with self.assertRaises(ValueError):
            draft_from_entry(dict(platform="youtube", origin_source_ref=None, proposed_source_type="YOUTUBE_CHANNEL"), "channel")

    def test_youtube_bridge_channel_gate_and_missing_values(self):
        adapter = YouTubeItemAdapter(lambda url, deadline: dict(id="abcdefghijk", channel_id="UCdemo", title="VinCons", timestamp=None, upload_date="20261008", description=None, view_count=0))
        candidate = Candidate("youtube", "https://www.youtube.com/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk", "google", "run", "GOOGLE_SERPAPI", platform_item_id="abcdefghijk", prefilter_decision="REVIEW")
        result = adapter.fetch_item(candidate, FetchContext(dict(platform_source_ref="UCdemo"), WINDOW, Deadline()))
        self.assertEqual(result.candidate.engagement["views"], 0)
        self.assertIsNone(result.candidate.engagement["likes"])
        self.assertEqual(result.candidate.publication_precision, "DATE_ONLY")
        with self.assertRaises(AdapterError):
            adapter.fetch_item(candidate, FetchContext(dict(platform_source_ref="UCother"), WINDOW, Deadline()))

    def test_atomic_content_and_observation_rollback_on_crash(self):
        candidate = item()
        apply_prefilter(candidate)
        with patch.object(self.store, "observation", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                self.store.save_candidate(candidate)
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM aliases").fetchone()[0], 0)

    def test_fallback_native_resolution_keeps_record_and_queue_history(self):
        candidate = item()
        candidate.platform_item_id = None
        apply_prefilter(candidate)
        record_id, _ = self.store.save_candidate(candidate)
        discovery_id = self.store.enqueue(candidate, "SOURCE_NOT_READY", "FACEBOOK_GROUP")
        self.store.review(discovery_id, "REJECTED", "reviewer", "defer")
        resolved = replace(candidate, platform_item_id="123", candidate_id="resolved")
        self.assertEqual(self.store.save_candidate(resolved)[0], record_id)
        self.assertEqual(self.store.enqueue(resolved, "SOURCE_NOT_READY", "FACEBOOK_GROUP"), discovery_id)
        self.assertEqual(self.store.queue_entry(discovery_id)["status"], "REJECTED")
        self.assertEqual(self.store.queue_entry(discovery_id)["platform_item_id"], "123")
        self.assertEqual(len(self.store.export_records()), 1)

    def test_equal_text_is_relationship_not_item_identity(self):
        for key in ("1", "2"):
            candidate = item("Cổng công trường VinCons đông công nhân chờ lâu", key)
            apply_prefilter(candidate)
            self.store.save_candidate(candidate)
        self.assertEqual(len(self.store.export_records()), 2)
        self.assertEqual(self.store.db.execute("SELECT kind FROM content_relationships").fetchone()[0], "EXACT_TEXT")

    def test_alias_resolution_merges_records_queue_and_keeps_rejection_history(self):
        short = "https://vm.tiktok.com/fixture"
        native = item(platform="tiktok")
        fallback = replace(native, platform_item_id=None, source_url=short, canonical_url=short, candidate_id="fallback")
        for candidate in (fallback, native):
            apply_prefilter(candidate)
            self.store.save_candidate(candidate)
        first = self.store.enqueue(fallback, "UNKNOWN_ORIGIN_SOURCE", "TIKTOK_ACCOUNT")
        self.store.review(first, "REJECTED", "ops", "defer")
        self.store.enqueue(native, "UNAPPROVED_SOURCE", "TIKTOK_ACCOUNT")
        resolved = replace(native, source_url=short, candidate_id="resolved_alias")
        self.store.save_candidate(resolved)
        self.assertEqual(self.store.enqueue(resolved, "UNAPPROVED_SOURCE", "TIKTOK_ACCOUNT"), first)
        self.assertEqual(len(self.store.export_records()), 1)
        self.assertEqual(len(self.store.list_queue()), 1)
        self.assertEqual(self.store.queue_entry(first)["status"], "REJECTED")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations WHERE discovery_id=?", (first,)).fetchone()[0], 3)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM review_history WHERE discovery_id=?", (first,)).fetchone()[0], 1)

    def test_drop_purges_all_matching_native_and_fallback_records(self):
        short = "https://vm.tiktok.com/fixture"
        native = item(platform="tiktok")
        fallback = replace(native, platform_item_id=None, source_url=short, canonical_url=short, candidate_id="fallback")
        for candidate in (native, fallback):
            apply_prefilter(candidate)
            self.store.save_candidate(candidate)
            self.store.enqueue(candidate, "UNAPPROVED_SOURCE", "TIKTOK_ACCOUNT")
        dropped = replace(native, source_url=short, caption="Cần bán xe, liên hệ giá rẻ", candidate_id="drop")
        apply_prefilter(dropped)
        self.store.reject(dropped)
        self.assertEqual(self.store.export_records(), [])
        self.assertEqual(self.store.list_queue(), [])

    def test_atomic_quota_across_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        path = self.directory / "acquisition.sqlite3"
        def reserve_many(_):
            connection = AcquisitionStore(path)
            try:
                return sum(connection.reserve_request("concurrent", run_cap=20) for _ in range(15))
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(reserve_many, range(2))), 20)

    def test_registry_rejects_bad_version_refs_types_and_enabled_unverified(self):
        import yaml
        directory = self.directory / "config"
        directory.mkdir()
        for path in (PROJECT_ROOT / "config").glob("*.yaml"):
            shutil.copy2(path, directory / path.name)
        path = directory / "sources.yaml"
        original = yaml.safe_load(path.read_text(encoding="utf-8"))
        original["sources"][0].update(enabled=False, verification_status="PENDING_VERIFICATION", requires_login=None)
        for change in (lambda d: d.update(schema_version="future-v99"), lambda d: d["sources"][0].update(enabled=True), lambda d: d["sources"][0].update(enabled="false"), lambda d: d["sources"].append(d["sources"][0].copy())):
            data = deepcopy(original)
            change(data)
            path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
            with self.subTest(change=change), self.assertRaises(ValueError):
                Registry(directory)
        path.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")
        watchlist_path = directory / "watchlists.yaml"
        data = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
        data["watchlists"][0]["source_ids"].append("unknown")
        watchlist_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        with self.assertRaises(ValueError): Registry(directory)

    def test_cli_validate_and_export_are_offline(self):
        from contextlib import redirect_stdout
        database = self.directory / "cli.sqlite3"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["--db", str(database), "validate"]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "VALID")
        output_path = self.directory / "output.json"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db", str(database), "export", "--output", str(output_path)]), 0)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["records"], [])

    def test_source_enable_requires_verification_without_mutating_file(self):
        before = (PROJECT_ROOT / "config/sources.yaml").read_bytes()
        directory = self.directory / "unverified-config"
        shutil.copytree(PROJECT_ROOT / "config", directory)
        registry = Registry(directory)
        source = registry.sources["fb_group_1675953926771851"]
        source.update(enabled=False, verification_status="PENDING_VERIFICATION", access_verified=False, requires_login=None)
        with self.assertRaises(ValueError):
            registry.update("sources", source["source_id"], dict(enabled=True))
        self.assertFalse(source["enabled"])
        self.assertEqual((PROJECT_ROOT / "config/sources.yaml").read_bytes(), before)

    def test_tt_ac_08_keyword_hashtag_share_item_and_keep_both_queries(self):
        source = self.registry.sources["tt_search_vincons"]
        source.update(enabled=True, verification_status="VERIFIED", access_type="PUBLIC", access_verified=True, requires_login=False)
        adapter = FixtureAdapter([item(platform="tiktok")])
        report = self.run_fixture(adapter, [source["source_id"]])
        self.assertEqual(len(report["jobs"]), 2)
        self.assertEqual(adapter.fetch_calls, ["123"])
        self.assertEqual(len(self.store.export_records()), 1)
        observations = [json.loads(row[0]) for row in self.store.db.execute("SELECT payload FROM observations")]
        self.assertEqual({x["query_type"] for x in observations}, {"KEYWORD", "HASHTAG"})
        self.assertEqual({x["search_keyword"] for x in observations}, {"VinCons", "#VinCons"})

    def test_hashtag_container_draft_is_query_scope_not_creator(self):
        source = draft_from_entry(dict(platform="tiktok", proposed_source_type="TIKTOK_SEARCH", origin_source_ref="VinCons"), "new_query")
        self.assertFalse(source["enabled"])
        jobs = list(query_jobs(source, [self.registry.queries["vincons_ecosystem"]]))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["mode"], "HASHTAG_SEARCH")
        self.assertEqual(jobs[0]["search_keyword"], "#VinCons")

    def test_expired_deadline_does_not_launch_or_fetch(self):
        candidate = item()
        adapter = FixtureAdapter([candidate])
        req = request()
        req.deadline = Deadline(-1)
        result = self.engine(adapter).run_job(req, self.watchlist, "expired")
        self.assertEqual(result["status"], "BUDGET_EXHAUSTED")
        self.assertEqual(adapter.fetch_calls, [])


class IdentityAndProviderTests(unittest.TestCase):
    def test_gg_ac_02_aliases_tracking_and_identity_params(self):
        self.assertEqual(identify("https://web.facebook.com/groups/123/posts/456/?ref=share").url, "https://www.facebook.com/groups/123/posts/456")
        self.assertEqual(identify("https://m.facebook.com/groups/123/permalink/456/?ref=share#x").url, "https://www.facebook.com/groups/123/posts/456")
        self.assertEqual(identify("https://youtube.com/watch?v=abcdefghijk&utm_source=x").url, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(identify("https://youtu.be/abcdefghijk?si=x").item_id, "abcdefghijk")
        self.assertIn("story_fbid=12", identify("https://facebook.com/permalink.php?story_fbid=12&id=34&ref=x").url)
        for url in ("https://www.facebook.com.evil.test/groups/1", "https://evil.test/", "file:///x", "https://user:secret@facebook.com/groups/1"):
            with self.assertRaises(ValueError): identify(url)

    def test_gg_ac_08_missing_key_never_calls_api(self):
        http = Mock()
        with patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            batch = GoogleSocialAdapter(Mock(), http).discover(request())
        self.assertEqual(batch.status, "AUTH_REQUIRED")
        http.get.assert_not_called()

    def test_gg_ac_09_empty_vs_invalid_and_key_redaction(self):
        for payload, expected in [({"organic_results": []}, "NO_NEW_DATA"), ({"organic_results": "bad"}, "EXTRACTION_FAILED"), ({"error": "Invalid API key secret_value"}, "AUTH_REQUIRED"), ({"error": "Your plan has run out of searches"}, "BUDGET_EXHAUSTED")]:
            http = Mock()
            http.get.return_value.status_code = 200
            http.get.return_value.json.return_value = payload
            with patch.dict(os.environ, {"SERPAPI_API_KEY": "secret_value"}):
                batch = GoogleSocialAdapter(lambda _: True, http).discover(request(effective_query='site:tiktok.com "VinCons"'))
            self.assertEqual(batch.status, expected)
            self.assertNotIn("secret_value", json.dumps(batch.__dict__))

    def test_gg_ac_03_platforms_containers_snippet_not_content(self):
        links = ["https://www.facebook.com/groups/123", "https://www.tiktok.com/@demo/video/123", "https://www.youtube.com/watch?v=abcdefghijk"]
        http = Mock()
        http.get.return_value.status_code = 200
        http.get.return_value.json.return_value = {"organic_results": [dict(link=url, title="VinCons", snippet="yesterday", position=i+1) for i, url in enumerate(links)]}
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            batch = GoogleSocialAdapter(lambda _: True, http).discover(request(effective_query='site:tiktok.com "VinCons"'))
        self.assertEqual([c.platform for c in batch.candidates], ["facebook", "tiktok", "youtube"])
        self.assertEqual(batch.candidates[0].candidate_kind, "SOURCE_CONTAINER")
        self.assertTrue(all(c.raw_text is None and c.published_at is None and c.caption is None for c in batch.candidates))
        self.assertEqual(http.get.call_args.kwargs["params"]["gl"], "vn")
        self.assertEqual(http.get.call_args.kwargs["params"]["hl"], "vi")

    def test_google_date_filter_uses_fixed_window_including_historical_reruns(self):
        http = Mock()
        http.get.return_value.status_code = 200
        http.get.return_value.json.return_value = {"organic_results": []}
        for start, end, expected in [
            ("2026-10-01T11:00:00Z", "2026-10-08T11:00:00Z", "cdr:1,cd_min:10/01/2026,cd_max:10/08/2026"),
            ("2025-01-10T00:00:00Z", "2025-01-17T00:00:00Z", "cdr:1,cd_min:01/10/2025,cd_max:01/17/2025"),
        ]:
            req = request(effective_query='site:facebook.com/groups "VinCons"')
            req.source = dict(req.source, search_date_filter="WINDOW")
            req.window = Window(parse_utc(start), parse_utc(end))
            with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
                GoogleSocialAdapter(lambda _: True, http).discover(req)
            self.assertEqual(http.get.call_args.kwargs["params"]["tbs"], expected)

    def test_google_retry_reserves_each_attempt_and_never_logs_exception(self):
        import requests
        http, reserve = Mock(), Mock(return_value=True)
        http.get.side_effect = requests.Timeout("https://serpapi.com/search.json?api_key=secret")
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "secret"}):
            batch = GoogleSocialAdapter(reserve, http).discover(request())
        self.assertEqual(batch.attempts, 2)
        self.assertEqual(reserve.call_count, 2)
        self.assertEqual(batch.error_code, "SERPAPI_NETWORK_ERROR")

    def test_google_quota_reached_before_call(self):
        http = Mock()
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            batch = GoogleSocialAdapter(lambda _: False, http).discover(request())
        self.assertEqual(batch.status, "BUDGET_EXHAUSTED")
        http.get.assert_not_called()

    def test_keyword_and_hashtag_urls_are_distinct(self):
        adapter = TikTokSearchAdapter(None, Deadline())
        self.assertIn("/search/video?q=", adapter.discovery_url({}, "KEYWORD_SEARCH", "VinCons kẹt xe"))
        self.assertEqual(adapter.discovery_url({}, "HASHTAG_SEARCH", "#VinCons"), "https://www.tiktok.com/tag/VinCons")

    def test_redirect_stops_before_outside_allowlist(self):
        http = Mock()
        http.head.return_value.status_code = 302
        http.head.return_value.headers = {"Location": "https://evil.test/private"}
        with self.assertRaises(ValueError):
            resolve_redirects("https://vm.tiktok.com/abc", Deadline(), http)
        self.assertEqual(http.head.call_count, 1)

    def test_redirect_limit_and_valid_native_resolution(self):
        http = Mock()
        response1, response2 = Mock(status_code=302), Mock(status_code=200)
        response1.headers = {"Location": "https://www.tiktok.com/@demo/video/123?tracking=1"}
        http.head.side_effect = [response1, response2]
        target = resolve_redirects("https://vm.tiktok.com/abc", Deadline(), http)
        self.assertEqual(target.item_id, "123")
        self.assertEqual(http.head.call_count, 2)
