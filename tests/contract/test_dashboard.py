"""Dashboard exposes acquisition data without credentials or DB mutations."""
import json
import sqlite3
import tempfile
import unittest
import threading
import time as clock
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from engine.dashboard import snapshot, search_input, date_window, result_row, search_output, SearchService, SearchAlreadyRunning, make_handler
from src.storage.acquisition import AcquisitionStore
from src.browser.profiles import PROJECT_ROOT
from src.acquisition.models import Window, parse_utc


class DashboardTests(unittest.TestCase):
    def test_snapshot_rechecks_records_and_queue_against_current_filter(self):
        from src.acquisition.models import Candidate
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'
            store = AcquisitionStore(path)
            url = 'https://www.facebook.com/groups/123/posts/456'
            stale = Candidate('facebook', url, url, 'source', 'run', 'BROWSER', caption='VinCons đang tiếp nhận thông tin nhân sự', prefilter_decision='PASS')
            store.save_candidate(stale)
            queued_url = 'https://www.facebook.com/groups/123/posts/789'
            queued = Candidate('facebook', queued_url, queued_url, 'source', 'run', 'GOOGLE_SERPAPI', title='Cơ hội mới', search_snippet='Việc làm hấp dẫn đang chờ bạn!')
            store.enqueue(queued, 'UNAPPROVED_SOURCE')
            store.close()
            data = snapshot(path, PROJECT_ROOT / 'config')
            self.assertEqual(data['items'], [])
            # Display filtering must not silently mutate the persisted audit.
            connection = sqlite3.connect(path)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
            connection.close()

    def test_daily_slots_fixed_45_minute_grid_and_window_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SearchService(Path(directory) / "test.sqlite3", PROJECT_ROOT / "config")
            service.configure_schedule(dict(enabled=True,window_mode="DAILY_SLOTS",daily_slots=[dict(start="05:00",end="08:30"),dict(start="17:00",end="18:30")],interval_min_minutes=45,interval_max_minutes=45))
            service.schedule["next_run_at"] = "2026-10-07T22:00:01Z"
            with patch.object(service,"start",return_value=dict(job_id="peak")) as start:
                self.assertIsNone(service.schedule_tick(parse_utc("2026-10-07T21:59:59Z")))
                for stamp in ["2026-10-07T22:00:01Z","2026-10-07T22:45:00Z","2026-10-07T23:30:00Z","2026-10-08T00:15:00Z","2026-10-08T01:00:00Z"]:
                    self.assertIsNotNone(service.schedule_tick(parse_utc(stamp)))
                self.assertEqual(start.call_count,5)
                self.assertEqual(start.call_args.kwargs["window_override"].start,parse_utc("2026-10-07T22:00:00Z"))
                self.assertEqual(start.call_args.kwargs["window_override"].end,parse_utc("2026-10-08T01:00:00Z"))
                self.assertEqual(service.schedule["next_run_at"],"2026-10-08T01:30:00+00:00")
                self.assertIsNotNone(service.schedule_tick(parse_utc("2026-10-08T01:30:00Z")))
                self.assertEqual(start.call_args.kwargs["window_override"].end,parse_utc("2026-10-08T01:30:00Z"))
                self.assertTrue(start.call_args.args[0]['_schedule_context']['final_tick'])
                self.assertEqual(service.schedule["next_run_at"],"2026-10-08T10:00:01+00:00")
                for stamp in ["2026-10-08T10:00:01Z","2026-10-08T10:45:00Z","2026-10-08T11:30:01Z"]:
                    self.assertIsNotNone(service.schedule_tick(parse_utc(stamp)))
                window=start.call_args.kwargs["window_override"]
                self.assertEqual(window.start,parse_utc("2026-10-08T10:00:00Z"))
                self.assertEqual(window.end,parse_utc("2026-10-08T11:30:00Z"))
                self.assertEqual(window.status("2026-10-08T11:30:00Z","INSTANT"),"OUT_OF_WINDOW")
                self.assertEqual(service.schedule["next_run_at"],"2026-10-08T22:00:01+00:00")
                self.assertIsNone(service.schedule_tick(parse_utc("2026-10-08T12:00:00Z")))
                self.assertEqual(start.call_count,9)

    def test_legacy_schedule_migrates_to_raw_v2_without_losing_user_config(self):
        with tempfile.TemporaryDirectory() as directory:
            database=Path(directory)/'test.sqlite3'
            service=SearchService(database,PROJECT_ROOT/'config')
            service.configure_schedule(dict(enabled=True,window_mode='DAILY_SLOTS',project_id='vinwonders_vu_yen'))
            saved=dict(service.schedule,schema_version='dashboard-schedule-v1',next_run_at='2099-01-01T00:00:00Z')
            service.schedule_path.write_text(json.dumps(saved),encoding='utf-8')
            restored=SearchService(database,PROJECT_ROOT/'config',enable_scheduler=True)
            try:
                status=restored.schedule_status()
                self.assertEqual(status['schema_version'],'dashboard-schedule-v2')
                self.assertEqual(status['pipeline'],'RAW_V2_THREADS')
                self.assertEqual(status['record_schema_version'],'conversation-record-v2')
                self.assertEqual(status['node_types'],['POST','COMMENT','REPLY'])
                self.assertTrue(status['enabled'])
                self.assertEqual(status['daily_slots'],saved['daily_slots'])
                self.assertEqual(status['project_id'],'vinwonders_vu_yen')
                self.assertEqual(status['next_run_at'],saved['next_run_at'])
                self.assertEqual(json.loads(service.schedule_path.read_text())['schema_version'],'dashboard-schedule-v2')
            finally: restored.close()

    def test_daily_busy_restart_and_outside_slot_do_not_replay_missed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.sqlite3"
            service=SearchService(path,PROJECT_ROOT/"config")
            service.configure_schedule(dict(enabled=True,window_mode="DAILY_SLOTS"))
            service.schedule["next_run_at"]="2026-10-07T22:45:00Z"
            with patch.object(service,"start",side_effect=SearchAlreadyRunning("busy","CRAWL")) as start:
                self.assertIsNone(service.schedule_tick(parse_utc("2026-10-07T22:45:01Z")))
                self.assertEqual(service.schedule["next_run_at"],"2026-10-07T22:45:00Z")
                self.assertIsNone(service.schedule_tick(parse_utc("2026-10-08T02:00:00Z")))
                self.assertEqual(start.call_count,1)
                self.assertEqual(service.schedule["next_run_at"],"2026-10-08T10:00:01+00:00")
            service.schedule["next_run_at"]="2099-01-01T00:00:00Z"
            service._save_schedule()
            restored=SearchService(path,PROJECT_ROOT/"config",enable_scheduler=True)
            restored.close()
            self.assertEqual(restored.schedule["window_mode"],"DAILY_SLOTS")
            self.assertEqual(restored.schedule["daily_slots"],service.schedule["daily_slots"])
            self.assertEqual(restored.schedule["interval_min_minutes"],45)

    def test_daily_schedule_rejects_overlaps_bad_times_and_reversed_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            service=SearchService(Path(directory)/"test.sqlite3",PROJECT_ROOT/"config")
            for change in [dict(daily_slots=[]),dict(daily_slots=[dict(start="25:00",end="08:30")]),
                           dict(daily_slots=[dict(start="05:00",end="08:30"),dict(start="05:00",end="18:30")]),
                           dict(daily_slots=[dict(start="18:30",end="17:00")]),dict(interval_min_minutes=46,interval_max_minutes=45)]:
                with self.assertRaises(ValueError):
                    service.configure_schedule(dict(enabled=True,window_mode="DAILY_SLOTS",**change))
                self.assertFalse(service.schedule["enabled"])
                self.assertFalse(service.schedule_path.exists())

    def test_crawl_without_queries_uses_only_ready_facebook_even_if_google_disabled(self):
        from engine.registry import Registry
        registry = Registry(PROJECT_ROOT / "config")
        registry.sources["google_social_vincons"]["enabled"] = False
        captured, called = {}, threading.Event()
        def fake_crawl(registry, database, sources, window, run_id):
            captured.update(sources=sources, window=window)
            called.set()
            return dict(status="PARTIAL", crawl_run_id="fake_crawl", jobs=[],unresolved_time=0)
        with tempfile.TemporaryDirectory() as directory, patch("engine.dashboard.Registry", return_value=registry), patch("engine.dashboard_conversations.crawl", fake_crawl), patch("engine.dashboard_conversations.results",return_value=[]):
            service = SearchService(Path(directory) / "test.sqlite3", PROJECT_ROOT / "config",conversation_db=Path(directory)/'raw.db')
            job = service.start(dict(start_date="2026-10-01", end_date="2026-10-08"), "CRAWL")
            self.assertTrue(called.wait(3))
            limit = clock.monotonic() + 3
            while service.get(job["job_id"])["status"] == "RUNNING" and clock.monotonic() < limit: clock.sleep(.01)
            self.assertEqual(service.get(job["job_id"])["status"], "PARTIAL")
            self.assertEqual(job["mode"], "CRAWL")
            self.assertTrue(captured["sources"])
            self.assertTrue(all(registry.sources[sid]["source_type"] == "FACEBOOK_GROUP" for sid in captured["sources"]))
            with self.assertRaises(ValueError): service.start(dict(keywords=["VinCons"]), "SEARCH")

    def test_schedule_rolls_window_persists_and_skips_overlapping_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SearchService(Path(directory) / "test.sqlite3", PROJECT_ROOT / "config")
            service.configure_schedule(dict(enabled=True, interval_minutes=30, window_mode="ROLLING", lookback_minutes=180))
            now = parse_utc("2026-10-08T15:00:00Z")
            service.schedule["next_run_at"] = now.isoformat()
            with patch.object(service, "start", return_value=dict(job_id="scheduled")) as start:
                self.assertEqual(service.schedule_tick(now)["job_id"], "scheduled")
                self.assertEqual(start.call_args.args[1], "CRAWL")
                self.assertFalse(start.call_args.args[0]['_schedule_context']['final_tick'])
                window = start.call_args.kwargs["window_override"]
                self.assertEqual(window.start, parse_utc("2026-10-08T12:00:00Z"))
                self.assertEqual(window.end, now)
                self.assertIsNone(service.schedule_tick(now))
                self.assertEqual(start.call_count, 1)
            service.schedule["next_run_at"] = now.isoformat()
            with patch.object(service, "start", side_effect=SearchAlreadyRunning("other", "SEARCH")):
                self.assertIsNone(service.schedule_tick(now))
            self.assertTrue(service.schedule["enabled"])
            service.configure_schedule(dict(enabled=False))
            self.assertIsNone(service.schedule_tick(now))
            saved = json.loads(service.schedule_path.read_text())
            self.assertFalse(saved["enabled"])

    def test_schedule_restores_enabled_config_and_stops_at_fixed_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            service = SearchService(path, PROJECT_ROOT / "config")
            service.configure_schedule(dict(enabled=True, interval_minutes=15, window_mode="FIXED", start_date="2026-10-01", end_date="2026-10-08"))
            service.schedule["next_run_at"] = "2099-01-01T00:00:00Z"
            service._save_schedule()
            restored = SearchService(path, PROJECT_ROOT / "config", enable_scheduler=True)
            restored.close()
            self.assertTrue(restored.schedule["enabled"])
            self.assertEqual(restored.schedule["interval_minutes"], 15)
            service.schedule["next_run_at"] = "2026-10-08T12:00:00Z"
            with patch.object(service, "start", return_value=dict(job_id="fixed")) as start:
                service.schedule_tick(parse_utc("2026-10-08T12:00:00Z"))
                self.assertEqual(start.call_args.kwargs["window_override"].start, parse_utc("2026-09-30T17:00:00Z"))
                service.schedule_tick(parse_utc("2026-10-08T17:00:00Z"))
                self.assertFalse(service.schedule["enabled"])
                self.assertEqual(start.call_count, 1)
            self.assertEqual(service.schedule["error"], "SCHEDULE_WINDOW_ENDED")

    def test_invalid_schedule_does_not_enable_or_write_config(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SearchService(Path(directory) / "test.sqlite3", PROJECT_ROOT / "config")
            for payload in [dict(enabled=True,interval_minutes=0),dict(enabled=True,lookback_minutes=50000),dict(enabled=True,window_mode="BAD"),dict(enabled="yes")]:
                with self.assertRaises(ValueError): service.configure_schedule(payload)
                self.assertFalse(service.schedule["enabled"])
                self.assertFalse(service.schedule_path.exists())

    def test_output_rechecks_stale_pass_recruitment_without_mutating_payload(self):
        window = Window(parse_utc("2026-10-08T00:00:00Z"),parse_utc("2026-10-09T00:00:00Z"))
        for caption in ["Tuyển 50 nam công nhân xây dựng", "Tìm gấp 20 công nhân đi làm ngay",
                        "Công ty mình tuyển đội thi công công trình"]:
            payload = dict(canonical_url="https://www.facebook.com/groups/123/posts/456", caption=caption,
                           prefilter_decision="PASS",published_at="2026-10-08T10:00:00Z",publication_precision="INSTANT")
            before = payload.copy()
            self.assertIsNone(result_row(payload, window))
            self.assertEqual(payload, before)
        payload["caption"] = "Cảnh báo lừa đảo tuyển đội thi công"
        self.assertIsNotNone(result_row(payload, window))

    def test_running_search_returns_existing_job_for_reconnection(self):
        service = SearchService(Path("unused.sqlite3"), PROJECT_ROOT / "config")
        service.running = True
        service.jobs["active"] = dict(job_id="active", status="RUNNING", rows=[])
        with self.assertRaises(SearchAlreadyRunning) as caught:
            service.start(dict(keywords=["VinCons"]))
        self.assertEqual(caught.exception.job_id, "active")
        self.assertEqual(len(service.jobs), 1)

    def test_http_busy_and_validation_report_specific_safe_errors(self):
        service = SearchService(Path("unused.sqlite3"), PROJECT_ROOT / "config")
        service.running = True
        service.jobs["active"] = dict(job_id="active", status="RUNNING", rows=[])
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service.database, service.config_dir, service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            for payload, status, expected in [(dict(keywords=["VinCons"]), 409, "SEARCH_RUNNING"),
                                               (dict(keywords=[], hashtags=[]), 400, "Nhập ít nhất một keyword hoặc hashtag.")]:
                req = Request(url + "/api/search", data=json.dumps(payload).encode(), headers={"Origin":url, "Content-Type":"application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(req, timeout=3)
                with caught.exception as response:
                    self.assertEqual(response.code, status)
                    body = json.load(response)
                if status == 409:
                    self.assertEqual(body["code"], expected)
                    self.assertEqual(body["job_id"], "active")
                else:
                    self.assertEqual(body["error"], expected)
            with self.assertRaises(HTTPError) as missing:
                urlopen(url + '/api/jobs/expired', timeout=3)
            with missing.exception as response:
                self.assertEqual(response.code, 404)
                self.assertEqual(json.load(response)['code'], 'JOB_NOT_FOUND')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(3)

    def test_search_job_passes_user_queries_to_engine_without_writing_config(self):
        config = PROJECT_ROOT / "config"
        before = (config / "keywords.yaml").read_bytes()
        called = threading.Event()
        captured = {}
        class FakeEngine:
            def __init__(self, registry, store):
                captured["terms"] = registry.queries["vincons_ecosystem"]
            def run(self, watchlist, window, sources, *args):
                captured.update(window=window, sources=sources)
                called.set()
                return dict(status="SUCCESS", crawl_run_id="fake_run", jobs=[])
        with tempfile.TemporaryDirectory() as directory, patch("engine.dashboard.AcquisitionEngine", FakeEngine):
            service = SearchService(Path(directory) / "test.sqlite3", config)
            job = service.start(dict(keywords=["Custom keyword"], hashtags=["#CustomTag"]))
            self.assertTrue(called.wait(3))
            limit = clock.monotonic() + 3
            while service.get(job["job_id"])["status"] == "RUNNING" and clock.monotonic() < limit:
                clock.sleep(.01)
            self.assertEqual(service.get(job["job_id"])["status"], "SUCCESS")
            self.assertEqual(captured["terms"]["discovery_terms"], ["Custom keyword"])
            self.assertEqual(captured["terms"]["hashtags"], ["#CustomTag"])
            self.assertIn("google_social_vincons", captured["sources"])
            self.assertEqual(captured["sources"], ["google_social_vincons"])
        self.assertEqual((config / "keywords.yaml").read_bytes(), before)

    def test_search_defaults_today_in_vietnam_and_inclusive_end_day(self):
        now = datetime(2026, 10, 8, 2, tzinfo=timezone.utc)
        terms, window = search_input(dict(keywords=["VinCons"], hashtags=[]), now)
        self.assertEqual(window.start.isoformat(), "2026-10-07T17:00:00+00:00")
        self.assertEqual(window.end, now)
        _, old = search_input(dict(keywords=[], hashtags=["#VinCons"], start_date="2026-10-01", end_date="2026-10-03"), now)
        self.assertEqual(old.end.isoformat(), "2026-10-03T17:00:00+00:00")
        self.assertEqual(terms["keywords"], ["VinCons"])

    def test_bad_queries_and_dates_do_not_start_collection(self):
        for payload in [dict(keywords=[], hashtags=[]), dict(keywords="VinCons"),
                        dict(keywords=["VinCons"], hashtags=["#bad tag"]),
                        dict(keywords=["VinCons"], start_date="2026-10-09", end_date="2026-10-08"),
                        dict(keywords=["VinCons"], start_date="2026-10-08", end_date="2026-10-10")]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                search_input(payload, datetime(2026,10,8,12,tzinfo=timezone.utc))

    def test_only_content_links_and_optional_fields_no_inference(self):
        self.assertIsNone(result_row(dict(canonical_url="https://www.facebook.com/groups/123/posts/456")))
        self.assertIsNone(result_row(dict(canonical_url="https://www.tiktok.com/@demo")))
        self.assertIsNone(result_row(dict(canonical_url="https://example.com/video/1")))
        window = Window(parse_utc("2026-10-08T00:00:00Z"), parse_utc("2026-10-09T00:00:00Z"))
        row = result_row(dict(canonical_url="https://www.youtube.com/watch?v=abcdefghijk", title="Project XYZ congestion", search_snippet="A complaint", published_at="2026-10-08T10:00:00Z", publication_precision="INSTANT"), window)
        self.assertIsNotNone(result_row(dict(canonical_url="https://www.facebook.com/groups/123/posts/456",published_at="2026-10-08T10:00:00Z",publication_precision="INSTANT"),window))
        self.assertIsNone(row["project"])
        self.assertIsNone(row["summary"])
        self.assertIsNone(row["issue"])
        self.assertTrue(row["verified_time"])
        self.assertIsNone(result_row(dict(canonical_url="https://www.youtube.com/watch?v=abcdefghijk", prefilter_decision="DROP")))

    def test_recent_output_rejects_old_unknown_relative_and_future_times(self):
        window = Window(parse_utc("2026-10-08T00:00:00Z"), parse_utc("2026-10-08T12:00:00Z"))
        base = dict(canonical_url="https://www.youtube.com/watch?v=abcdefghijk", publication_precision="INSTANT", window_status="IN_WINDOW", discovered_at="2026-10-08T10:00:00Z")
        for stamp, precision in [(None,"INSTANT"),("2025-10-08T01:00:00Z","INSTANT"),
                                 ("2026-10-08T01:00:00Z","APPROXIMATE"),("2026-10-08","DATE_ONLY"),
                                 ("2026-10-08T12:00:00Z","INSTANT"),("2026-10-09T01:00:00Z","INSTANT"),
                                 ("2026-10-08T10:00:00","INSTANT"),("bad-date","INSTANT")]:
            with self.subTest(stamp=stamp,precision=precision):
                self.assertIsNone(result_row(dict(base,published_at=stamp,publication_precision=precision),window))
        self.assertIsNotNone(result_row(dict(base,published_at="2026-10-08T00:00:00Z"),window))
        self.assertIsNone(result_row(dict(base,published_at="2026-10-08T01:00:00Z")))

    def test_stored_run_window_is_used_and_results_sorted_by_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            store = AcquisitionStore(path)
            try:
                store.put_run("r1",dict(window_start="2026-10-08T00:00:00Z",window_end="2026-10-09T00:00:00Z"))
                for index,stamp in enumerate(["2026-10-08T01:00:00Z","2026-10-07T20:00:00Z","2026-10-08T12:00:00Z",None]):
                    key=str(index)
                    payload=dict(canonical_url=f"https://www.youtube.com/watch?v=abcdefghij{index}",published_at=stamp,publication_precision="INSTANT")
                    with store.db:
                        store.db.execute("INSERT INTO records VALUES (?,?,?)",(key,json.dumps(payload),None))
                        store.db.execute("INSERT INTO observations VALUES (?,?,?,?)",(key,key,None,json.dumps(dict(crawl_run_id="r1"))))
                rows=search_output(path,"r1")
                self.assertEqual([row["published_at"] for row in rows],["2026-10-08T12:00:00Z","2026-10-08T01:00:00Z"])
                self.assertEqual(search_output(path),[])
            finally:
                store.close()

    def test_missing_database_remains_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            result = snapshot(path, PROJECT_ROOT / "config")
            self.assertEqual(result["items"], [])
            self.assertFalse(path.exists())
            self.assertEqual(result["lookback_minutes"], 10080)

    def test_read_only_snapshot_omits_config_and_preserves_unknown_times(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            with sqlite3.connect(path) as db:
                db.executescript("""
                    CREATE TABLE runs(payload TEXT);
                    CREATE TABLE records(record_id TEXT,payload TEXT);
                    CREATE TABLE observations(record_id TEXT,discovery_id TEXT,payload TEXT);
                    CREATE TABLE queue(discovery_id TEXT,payload TEXT);
                    CREATE TABLE rejections(rejection_id TEXT,payload TEXT);
                    CREATE TABLE api_attempts(month TEXT);
                """)
                db.execute("INSERT INTO runs VALUES (?)", (json.dumps(dict(crawl_run_id="run1", status="SUCCESS", config_snapshot={"api_key":"secret-value"}, jobs=[])),))
                db.execute("INSERT INTO records VALUES (?,?)", ("item1",json.dumps(dict(platform="facebook",source_id="source1",canonical_url="https://www.facebook.com/groups/1/posts/2",extraction_status="METADATA_ONLY",published_at=None))))
                db.execute("INSERT INTO observations VALUES (?,?,?)", ("item1", None,json.dumps(dict(crawl_run_id="run1"))))
            db.close()
            before = path.read_bytes()
            result = snapshot(path, PROJECT_ROOT / "config")
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertIsNone(result["items"][0]["published_at"])
            self.assertEqual(result["items"][0]["window_status"], "UNKNOWN")
            self.assertEqual(result["items"][0]["run_ids"], ["run1"])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
