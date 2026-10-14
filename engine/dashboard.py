"""Local search form and acquisition output; searches require an explicit click."""
import argparse
import json
import sqlite3
from datetime import datetime, timezone, timedelta, date, time
import threading
import uuid
import os
import tempfile
import random
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import re

from engine.registry import Registry
from engine.acquisition import AcquisitionEngine
from src.acquisition.models import Window, parse_utc
from src.acquisition.identity import identify, hashtag_query, source_references
from src.storage.acquisition import AcquisitionStore
from src.acquisition.prefilter import normalize, classify_payload
from src.acquisition.projects import load_projects, project_fields, selected_match, validate_project
from src.browser.profiles import PROJECT_ROOT


def snapshot(database, config_dir):
    registry = Registry(config_dir)
    sources = [{key: source.get(key) for key in
                ("source_id", "platform", "name", "enabled", "verification_status")}
               for source in registry.sources.values()]
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(), sources=sources,
                  runs=[], items=[], api_attempts_month=0, api_budget_month=200,
                  lookback_minutes=registry.watchlists["vincons_acquisition_v1"]["retrieval"]["lookback_minutes"])
    if not database.is_file():
        return result
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("BEGIN")  # One consistent read snapshot, no schema writes.
        for row in connection.execute("SELECT payload FROM runs ORDER BY rowid DESC"):
            run = json.loads(row[0])
            result["runs"].append({key: run.get(key) for key in
                                   ("crawl_run_id", "status", "started_at", "finished_at", "window_start", "window_end", "jobs")})
        record_runs, queue_runs = {}, {}
        for record_id, discovery_id, payload in connection.execute("SELECT record_id,discovery_id,payload FROM observations"):
            run_id = json.loads(payload).get("crawl_run_id")
            if record_id:
                record_runs.setdefault(record_id, set()).add(run_id)
            if discovery_id:
                queue_runs.setdefault(discovery_id, set()).add(run_id)
        for identifier, payload in connection.execute("SELECT record_id,payload FROM records"):
            item = json.loads(payload)
            if item.get("prefilter_decision") == "DROP" or classify_payload(item).prefilter_decision == "DROP":
                continue
            result["items"].append(dict(
                kind="COLLECTED", id=identifier, platform=item["platform"], source_id=item["source_id"],
                title=item.get("title") or item.get("caption") or item.get("raw_text") or
                "Bài " + (item.get("platform_item_id") or identifier) + " · Chưa lấy được nội dung",
                url=item["canonical_url"], status=item.get("extraction_status", "UNKNOWN"),
                published_at=item.get("published_at"), window_status=item.get("window_status", "UNKNOWN"),
                missing_data_reasons=item.get("missing_data_reasons", []),
                run_ids=sorted(x for x in record_runs.get(identifier, {item.get("crawl_run_id")}) if x)))
        for identifier, payload in connection.execute("SELECT discovery_id,payload FROM queue"):
            item = json.loads(payload)
            if classify_payload(item).prefilter_decision == "DROP":
                continue
            result["items"].append(dict(
                kind="QUEUE", id=identifier, platform=item["platform"], source_id=item["source_id"],
                title=item.get("title") or "Link chờ duyệt", url=item["canonical_url"], status=item["status"],
                published_at=None, window_status="UNKNOWN", snippet=item.get("search_snippet"),
                reason=item.get("reason"), run_ids=sorted(x for x in queue_runs.get(identifier, {item.get("crawl_run_id")}) if x)))
        for identifier, payload in connection.execute("SELECT rejection_id,payload FROM rejections"):
            item = json.loads(payload)
            result["items"].append(dict(
                kind="REJECTED", id=identifier, platform="facebook" if "facebook.com" in item["source_url"] else
                "tiktok" if "tiktok.com" in item["source_url"] else "youtube",
                source_id=item["source_id"], title="Chỉ lưu metadata loại bỏ", url=item["source_url"],
                status="DROP", reason=item["drop_reason"], rule_id=item["rule_id"],
                published_at=None, window_status="UNKNOWN", run_ids=[item["crawl_run_id"]]))
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        result["api_attempts_month"] = connection.execute("SELECT count(*) FROM api_attempts WHERE month=?", (month,)).fetchone()[0]
    finally:
        connection.close()
    return result


VN = timezone(timedelta(hours=7))


def search_input(payload, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(VN).date()
    terms = {}
    for key in ("keywords", "hashtags"):
        values = payload.get(key, [])
        if not isinstance(values, list) or len(values) > 3 or any(not isinstance(v, str) or not v.strip() or len(v) > 150 for v in values):
            raise ValueError("Mỗi nhóm nhận tối đa 3 truy vấn, mỗi truy vấn tối đa 150 ký tự.")
        terms[key] = list(dict.fromkeys(v.strip() for v in values))
    if not terms["keywords"] and not terms["hashtags"]:
        raise ValueError("Nhập ít nhất một keyword hoặc hashtag.")
    for value in terms["hashtags"]:
        hashtag_query(value)
    return terms, date_window(payload, now)


def date_window(payload, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(VN).date()
    try:
        start = date.fromisoformat(payload.get("start_date", today.isoformat()))
        end = date.fromisoformat(payload.get("end_date", today.isoformat()))
    except (TypeError, ValueError):
        raise ValueError("Khoảng ngày không hợp lệ.") from None
    if start > end or end > today:
        raise ValueError("Ngày bắt đầu phải trước ngày kết thúc; không chọn ngày tương lai.")
    window_start = datetime.combine(start, time(), VN).astimezone(timezone.utc)
    window_end = min(now, datetime.combine(end + timedelta(days=1), time(), VN).astimezone(timezone.utc))
    return Window(window_start, window_end)


def result_row(item, window=None, sources=None, projects=None):
    url = item.get("canonical_url", "")
    try:
        target = identify(url)
    except ValueError:
        return None
    if target.kind != "CONTENT_ITEM":
        return None
    if item.get("prefilter_decision") == "DROP" or classify_payload(item).prefilter_decision == "DROP":
        return None
    # Discovery time / Google date filters are not publication evidence.
    # Re-evaluate every item's timestamp against this request, never reuse a
    # previous run's IN_WINDOW label for a narrower or newer search window.
    try:
        if window is None or window.status(item.get("published_at"), item.get("publication_precision")) != "IN_WINDOW":
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    group = group_url = None
    context_source_id = item.get('source_id')
    if target.platform == "facebook" and target.origin:
        group_url = "https://www.facebook.com/groups/" + target.origin
        matches = [source for source in (sources or {}).values()
                   if source.get("source_type") == "FACEBOOK_GROUP" and target.origin in source_references(source)]
        group = matches[0]["name"] if len(matches) == 1 else target.origin
        if len(matches) == 1:
            context_source_id = matches[0].get('source_id', context_source_id)
    project = project_fields(dict(item, context_source_id=context_source_id), projects or {})
    return dict(url=target.url, platform=target.platform, group=group, group_url=group_url, **project,
                summary=item.get("description_summary"), issue=item.get("operational_issue"),
                published_at=item.get("published_at"), verified_time=bool(item.get("published_at")),
                title=item.get("title") or (item.get("caption") or item.get("raw_text") or "")[:180] or None)


def search_output(database, run_id=None, window=None, terms=None, source_names=None, sources=None, projects=None, project_id=None):
    projects = projects or {}
    validate_project(project_id, projects)
    if not database.is_file():
        return []
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("BEGIN")
        if window is None and run_id:
            run = connection.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run:
                payload = json.loads(run[0])
                window = Window(parse_utc(payload["window_start"]), parse_utc(payload["window_end"]))
        if window is None:
            return []
        selected = None
        if run_id:
            selected = {row[0] for row in connection.execute(
                "SELECT record_id FROM observations WHERE json_extract(payload,'$.crawl_run_id')=?", (run_id,)) if row[0]}
        output = {}
        def relevant(item):
            if project_id:
                # Project aliases define result scope; the keyword is a
                # discovery query and must not reject a spelling variant.
                return True
            if not terms:
                return True
            text = normalize(" ".join(str(item.get(key) or "") for key in ("title", "caption", "raw_text")))
            text += " " + normalize((source_names or {}).get(item.get("source_id"), ""))
            keywords = terms.get("keywords", [])
            text_tokens = set(re.findall(r"\w+", text))
            keyword_match = any(tokens and all(token in text_tokens for token in tokens)
                                for tokens in (re.findall(r"\w+",normalize(term)) for term in keywords))
            tags = {normalize(tag.lstrip("#")) for tag in item.get("hashtags", []) + re.findall(r"#[\w]+", item.get("caption") or "")}
            hashtag_match = any(normalize(tag.lstrip("#")) in tags for tag in terms.get("hashtags", []))
            return keyword_match or hashtag_match
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone():
            return []
        for record_id, raw in connection.execute("SELECT record_id,payload FROM records"):
            if selected is not None and record_id not in selected:
                continue
            item = json.loads(raw)
            row = result_row(item, window, sources, projects) if relevant(item) else None
            if row and not selected_match(row, project_id):
                row = None
            if row:
                output[row["url"]] = row
        for discovery_id, raw in connection.execute("SELECT discovery_id,payload FROM queue"):
            item = json.loads(raw)
            if item.get("status") == "REJECTED":
                continue
            if run_id and not connection.execute("SELECT 1 FROM observations WHERE discovery_id=? AND json_extract(payload,'$.crawl_run_id')=?", (discovery_id, run_id)).fetchone():
                continue
            row = result_row(item, window, sources, projects) if relevant(item) else None
            if row and not selected_match(row, project_id):
                row = None
            if row:
                output.setdefault(row["url"], row)
        return sorted(output.values(), key=lambda row: parse_utc(row["published_at"]), reverse=True)
    finally:
        connection.close()


class SearchAlreadyRunning(ValueError):
    def __init__(self, job_id, mode="SEARCH"):
        super().__init__("Đang có lượt tìm kiếm chạy. Đang tiếp tục theo dõi kết quả.")
        self.job_id = job_id
        self.mode = mode


class SearchService:
    def __init__(self, database, config_dir, enable_scheduler=False, conversation_db=None):
        from engine.classification_worker import DEFAULT_DB
        default_raw = Path(database)
        self.conversation_db = Path(conversation_db or default_raw)
        self.database, self.config_dir = database, config_dir
        self.lock = threading.Lock()
        self.jobs = {}
        self.running = False
        self.schedule_path = Path(database).with_name("dashboard-schedule.json")
        self.schedule_lock = threading.RLock()
        self.scheduler_stop = threading.Event()
        self.runtime_recovery = None
        self.runtime_lock = threading.Lock()
        from engine.threads_service import ThreadsService
        self.threads = ThreadsService(self.conversation_db,config_dir,enable_scheduler)
        self.schedule = dict(schema_version="dashboard-schedule-v2", pipeline="RAW_V2_THREADS",
                             record_schema_version="conversation-record-v2", timezone="Asia/Ho_Chi_Minh",
                             node_types=["POST", "COMMENT", "REPLY"], storage_order="RAW_THEN_FILTER_CLASSIFY",
                             enabled=False, interval_minutes=30,
                             window_mode="ROLLING", lookback_minutes=10080, next_run_at=None, last_job_id=None, error=None,
                             daily_slots=[dict(start="05:00", end="08:30"), dict(start="17:00", end="18:30")],
                             interval_min_minutes=45, interval_max_minutes=45, project_id='')
        if enable_scheduler:
            try:
                saved = json.loads(self.schedule_path.read_text(encoding="utf-8"))
                if saved.get("schema_version") in {"dashboard-schedule-v1", "dashboard-schedule-v2"}:
                    legacy = saved["schema_version"] == "dashboard-schedule-v1"
                    self._validate_schedule(saved)
                    if type(saved.get("enabled")) is not bool:
                        raise ValueError("Invalid schedule")
                    if saved.get("next_run_at"):
                        parse_utc(saved["next_run_at"])
                    self.schedule.update({key:value for key,value in saved.items()
                                          if key in (set(self.schedule) | {"start_date", "end_date"}) -
                                          {"schema_version", "pipeline", "record_schema_version", "timezone", "node_types", "storage_order"}})
                    if legacy:
                        self._save_schedule()
            except (OSError, ValueError, TypeError, KeyError):
                pass
            self.scheduler_thread = threading.Thread(target=self._schedule_loop, daemon=True)
            self.scheduler_thread.start()

    @staticmethod
    def _validate_schedule(payload):
        interval = payload.get("interval_minutes", 30)
        if type(interval) is not int or not 5 <= interval <= 1440:
            raise ValueError("Chu kỳ crawl phải từ 5 đến 1440 phút.")
        mode = payload.get("window_mode", "ROLLING")
        if mode not in {"ROLLING", "FIXED", "DAILY_SLOTS"}:
            raise ValueError("Khoảng thời gian của lịch không hợp lệ.")
        if mode == "DAILY_SLOTS":
            slots = payload.get("daily_slots")
            if not isinstance(slots, list) or not 1 <= len(slots) <= 4:
                raise ValueError("Cần chọn từ 1 đến 4 khung giờ trong ngày.")
            bounds = []
            for slot in slots:
                if not isinstance(slot, dict) or any(not isinstance(slot.get(key), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", slot[key]) for key in ("start", "end")):
                    raise ValueError("Giờ phải có định dạng HH:MM.")
                start, end = time.fromisoformat(slot["start"]), time.fromisoformat(slot["end"])
                if start >= end:
                    raise ValueError("Giờ bắt đầu phải trước giờ kết thúc trong cùng ngày.")
                bounds.append((start, end))
            bounds.sort()
            if any(left[1] > right[0] for left,right in zip(bounds,bounds[1:])):
                raise ValueError("Các khung giờ crawl không được chồng nhau.")
            lower, upper = payload.get("interval_min_minutes", 30), payload.get("interval_max_minutes", 45)
            if type(lower) is not int or type(upper) is not int or not 5 <= lower <= upper <= 1440:
                raise ValueError("Chu kỳ nhỏ nhất/lớn nhất phải từ 5 đến 1440 phút và đúng thứ tự.")
        elif mode == "ROLLING":
            lookback = payload.get("lookback_minutes", 10080)
            if type(lookback) is not int or not 1 <= lookback <= 43200:
                raise ValueError("Lookback phải từ 1 phút đến 30 ngày.")
        else:
            # Validate chronology; allow a future end date for the schedule.
            start, end = date.fromisoformat(payload["start_date"]), date.fromisoformat(payload["end_date"])
            if start > end:
                raise ValueError("Khoảng ngày không hợp lệ.")

    def schedule_status(self):
        with self.schedule_lock:
            result = dict(self.schedule)
        result["active_job"] = self.active()
        result["worker_alive"] = bool(getattr(self,'scheduler_thread',None) and self.scheduler_thread.is_alive())
        return result

    def _save_schedule(self):
        self.schedule_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.schedule_path.parent, prefix=".schedule-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.schedule, stream, ensure_ascii=False)
            os.replace(temporary, self.schedule_path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def configure_schedule(self, payload):
        if type(payload.get("enabled")) is not bool:
            raise ValueError("Trạng thái lịch crawl không hợp lệ.")
        with self.schedule_lock:
            updated = dict(self.schedule)
            if payload["enabled"]:
                updated.update({key:payload[key] for key in ("interval_minutes", "window_mode", "lookback_minutes", "start_date", "end_date", "daily_slots", "interval_min_minutes", "interval_max_minutes", "project_id") if key in payload})
                self._validate_schedule(updated)
                if updated["window_mode"] == "DAILY_SLOTS" and updated["interval_min_minutes"] == updated["interval_max_minutes"]:
                    updated["interval_minutes"] = updated["interval_min_minutes"]
                registry = Registry(self.config_dir)
                project = validate_project(updated.get('project_id'), load_projects(self.config_dir))
                if not any(registry.sources[sid]["source_type"] == "FACEBOOK_GROUP" and not registry.readiness(registry.sources[sid])
                           and (not project or sid in project['source_ids'])
                           for sid in registry.watchlists["vincons_acquisition_v1"]["source_ids"]):
                    raise ValueError("Chưa có group Facebook được xác minh cho phạm vi lịch đã chọn.")
                updated["next_run_at"] = datetime.now(timezone.utc).isoformat()
                if updated["window_mode"] == "DAILY_SLOTS":
                    _, due = self._daily_slot(updated, datetime.now(timezone.utc))
                    updated["next_run_at"] = due.isoformat()
            else:
                updated["next_run_at"] = None
            updated.update(enabled=payload["enabled"], error=None)
            previous = self.schedule
            self.schedule = updated
            try:
                self._save_schedule()
            except OSError:
                self.schedule = previous
                raise ValueError("Không lưu được lịch crawl.") from None
        return self.schedule_status()

    @staticmethod
    def _daily_slot(schedule, now):
        """Select today's active slot or the next start, using Vietnam time."""
        local_day = now.astimezone(VN).date()
        for offset in (0, 1):
            day = local_day + timedelta(days=offset)
            for slot in sorted(schedule["daily_slots"], key=lambda slot:slot["start"]):
                start = datetime.combine(day, time.fromisoformat(slot["start"]), VN).astimezone(timezone.utc)
                end = datetime.combine(day, time.fromisoformat(slot["end"]), VN).astimezone(timezone.utc)
                if start < now <= end + timedelta(seconds=2):
                    return (start, end), now
                if now <= start:
                    # A nonempty window begins one second after the slot opens.
                    return None, start + timedelta(seconds=1)
        raise ValueError("No next daily slot")

    @classmethod
    def _next_daily_run(cls, schedule, now, slot_end):
        if now < slot_end:
            lower, upper = schedule["interval_min_minutes"], schedule["interval_max_minutes"]
            if lower == upper:
                slot, _ = cls._daily_slot(schedule, now)
                start = slot[0]
                steps = int((now - start).total_seconds() // (lower * 60)) + 1
                next_due = start + timedelta(minutes=steps * lower)
            else:
                next_due = now + timedelta(minutes=random.randint(lower, upper))
            if next_due <= slot_end:
                return next_due
            # The cadence need not divide the slot length (05:00-08:30 is 210m).
            # Always close the requested window instead of dropping its tail.
            return slot_end
        _, next_start = cls._daily_slot(schedule, slot_end + timedelta(seconds=3))
        return next_start

    def schedule_tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.schedule_lock:
            schedule = self.schedule
            if not schedule["enabled"] or (schedule.get("next_run_at") and now < parse_utc(schedule["next_run_at"])):
                return None
            slot_end = None
            if schedule["window_mode"] == "DAILY_SLOTS":
                slot, due = self._daily_slot(schedule, now)
                if slot is None:
                    schedule["next_run_at"] = due.isoformat()
                    self._save_schedule()
                    return None
                start, slot_end = slot
                window = Window(start, min(now, slot_end))
            elif schedule["window_mode"] == "ROLLING":
                window = Window(now - timedelta(minutes=schedule["lookback_minutes"]), now)
            else:
                start = datetime.combine(date.fromisoformat(schedule["start_date"]), time(), VN).astimezone(timezone.utc)
                end = datetime.combine(date.fromisoformat(schedule["end_date"]) + timedelta(days=1), time(), VN).astimezone(timezone.utc)
                if now <= start:
                    schedule["next_run_at"] = (start + timedelta(seconds=1)).isoformat()
                    self._save_schedule()
                    return None
                if now >= end:
                    schedule.update(enabled=False, next_run_at=None, error="SCHEDULE_WINDOW_ENDED")
                    self._save_schedule()
                    return None
                window = Window(start, min(now, end))
            try:
                crawl_payload={'project_id':schedule['project_id']} if schedule.get('project_id') else {}
                crawl_payload['_schedule_context']=dict(schedule_id='dashboard-v2',
                    final_tick=bool(slot_end and window.end==slot_end))
                job = self.start(crawl_payload, "CRAWL", window_override=window)
            except SearchAlreadyRunning:
                return None
            except (ValueError, KeyError):
                next_due = self._next_daily_run(schedule, now, slot_end) if slot_end else now + timedelta(minutes=schedule["interval_minutes"])
                schedule.update(error="SCHEDULE_SOURCE_NOT_READY", next_run_at=next_due.isoformat())
                self._save_schedule()
                return None
            next_due = self._next_daily_run(schedule, now, slot_end) if slot_end else now + timedelta(minutes=schedule["interval_minutes"])
            schedule.update(last_job_id=job["job_id"], error=None, next_run_at=next_due.isoformat())
            self._save_schedule()
            return job

    def _schedule_loop(self):
        while not self.scheduler_stop.wait(1):
            try:
                if not self.running:
                    from engine.dashboard_conversations import pending_run
                    pending=pending_run(self.conversation_db)
                    if pending:
                        self.start({}, 'CRAWL', window_override=Window(parse_utc(pending['window_start']),parse_utc(pending['window_end'])),resume_report=pending)
                        continue
                self.schedule_tick()
            except sqlite3.OperationalError as error:
                if getattr(error,'sqlite_errorcode',None) in {sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED}:
                    continue  # A transient writer lock must not kill or disable the daily schedule.
                with self.schedule_lock:
                    self.schedule.update(enabled=False,error="SCHEDULE_DATABASE_ERROR")
            except (OSError, ValueError, KeyError):
                with self.schedule_lock:
                    self.schedule.update(enabled=False, error="SCHEDULE_FAILED")

    def close(self):
        self.threads.close()
        self.scheduler_stop.set()

    def recovery_tick(self):
        if not self.runtime_lock.acquire(blocking=False):
            return {'status':'BUSY'}
        try:
            if self.runtime_recovery is None:
                from engine.runtime_recovery import RuntimeRecovery
                from src.config.env import env_int
                self.runtime_recovery=RuntimeRecovery(self,env_int('RUNTIME_CATCHUP_DAYS',7))
            return self.runtime_recovery.tick()
        finally:
            self.runtime_lock.release()

    def runtime_status(self):
        from src.acquisition.models import utcnow
        raw=sqlite3.connect(self.conversation_db,timeout=1)
        try:
            exists=raw.execute("SELECT 1 FROM sqlite_master WHERE name='dashboard_worker_heartbeats'").fetchone()
            workers=[json.loads(r[0]) for r in raw.execute('SELECT payload FROM dashboard_worker_heartbeats')] if exists else []
        finally:raw.close()
        now=datetime.now(timezone.utc)
        active=[w for w in workers if w.get('status')=='RUNNING' and (now-parse_utc(w['updated_at'])).total_seconds()<45]
        return {'schema_version':'local-runtime-v1','root':str(PROJECT_ROOT),'database':str(self.conversation_db),
                'as_of':utcnow(),'classifier_active':bool(active),'facebook_running':self.running,
                'threads_running':bool(self.threads.cancels),
                'catchup':self.runtime_recovery.status() if self.runtime_recovery else {'status':'SUPERVISOR_NOT_CONNECTED'}}

    def start(self, payload, mode="SEARCH", window_override=None, resume_report=None):
        if mode not in {"SEARCH", "CRAWL"}:
            raise ValueError("Chế độ thu thập không hợp lệ.")
        projects = load_projects(self.config_dir)
        selected_project = validate_project(payload.get('project_id'), projects)
        payload = dict(payload)
        if mode == 'SEARCH' and selected_project and not payload.get('keywords') and not payload.get('hashtags'):
            payload['keywords'] = selected_project['discovery_terms'][:3]
        terms, window = search_input(payload) if mode == "SEARCH" else (None, window_override or date_window(payload))
        registry = Registry(self.config_dir)
        if mode == "SEARCH":
            if registry.readiness(registry.sources["google_social_vincons"]):
                raise ValueError("Nguồn Google chưa sẵn sàng. Kiểm tra cấu hình và API key.")
            query = registry.queries["vincons_ecosystem"]
            if selected_project:
                terms['keywords'] = [term if project_fields({'caption': term}, {selected_project['project_id']: selected_project})['project_ids'] else selected_project['name'] + ' ' + term for term in terms['keywords']]
            query.update(discovery_terms=terms["keywords"], hashtags=terms["hashtags"])
            source_ids = ["google_social_vincons"]
        else:
            source_ids = [sid for sid in registry.watchlists["vincons_acquisition_v1"]["source_ids"]
                          if registry.sources[sid]["source_type"] == "FACEBOOK_GROUP" and not registry.readiness(registry.sources[sid])]
            if selected_project:
                source_ids = [sid for sid in source_ids if sid in selected_project['source_ids']]
            if resume_report:
                source_ids = list(resume_report['source_ids'])
            if not source_ids:
                raise ValueError("Chưa có group Facebook được xác minh cho phạm vi này. Bổ sung group dự án hoặc dùng tab Tìm kiếm.")
        with self.lock:
            if self.running:
                active = next((job for job in self.jobs.values() if job["status"] == "RUNNING"), None)
                raise SearchAlreadyRunning(active["job_id"] if active else None, active.get("mode", "SEARCH") if active else "SEARCH")
            self.running = True
            # A resumed durable run is still the same UI job. Generating a new
            # ID on every retry can evict the job a browser is still following.
            run_id = resume_report['crawl_run_id'] if resume_report else None
            identifier = (run_id.removeprefix('dashboard_') if run_id and re.fullmatch(r'dashboard_[a-f0-9]{32}', run_id)
                          else uuid.uuid5(uuid.NAMESPACE_URL, 'dashboard-resume:' + run_id).hex if run_id
                          else uuid.uuid4().hex)
            job = dict(job_id=identifier, mode=mode, status="RUNNING", rows=[], warnings=[],
                       window_start=window.start.isoformat(), window_end=window.end.isoformat(), source_count=len(source_ids), project_id=payload.get('project_id'))
            self.jobs.pop(identifier, None)
            self.jobs[identifier] = job
            while len(self.jobs) > 20:
                del self.jobs[next(iter(self.jobs))]

        def work():
            from engine.dashboard_conversations import warnings as crawl_warnings
            store = None
            update = {}
            run = None
            def progress(report):
                with self.lock:
                    job.update(crawl_run_id=report['crawl_run_id'],progress=dict(report.get('progress',{})),
                        updated_at=report.get('updated_at'),current_phase=report.get('current_phase'),
                        current_source=report.get('current_source'),
                        current_source_name=registry.sources.get(report.get('current_source'),{}).get('name'),
                        warnings=crawl_warnings(report))
            try:
                if mode == 'CRAWL':
                    from engine.dashboard_conversations import crawl, results
                    crawl_options={'schedule_context':payload['_schedule_context']} if '_schedule_context' in payload else {}
                    run = crawl(registry, self.conversation_db, source_ids, window, resume_report['crawl_run_id'] if resume_report else 'dashboard_' + identifier,progress_callback=progress,**crawl_options)
                    rows = results(self.conversation_db, window, registry.sources, projects, payload.get('project_id'), source_ids,report=run)
                    update = dict(status=run['status'], crawl_run_id=run['crawl_run_id'], rows=rows,
                        pipeline='RAW_V2_THREADS', coverage_limited=True, dropped=0,
                        pending_verification=run['unresolved_time'],
                        warnings=crawl_warnings(run),
                        source_outcomes=run['jobs'])
                    return
                store = AcquisitionStore(self.database)
                run = AcquisitionEngine(registry, store).run("vincons_acquisition_v1", window,
                                                            source_ids, 10, 120, 600)
                update = dict(status=run["status"], crawl_run_id=run["crawl_run_id"],
                              rows=search_output(self.database, run["crawl_run_id"], window, terms,
                                                {sid:source["name"] for sid,source in registry.sources.items()}, registry.sources, projects, payload.get('project_id')),
                              pending_verification=sum(j.get("counters", {}).get("queued", 0) + j.get("counters", {}).get("unknown_time", 0) for j in run["jobs"]),
                              warnings=[j.get("error_code") for j in run["jobs"] if j.get("error_code")],
                              dropped=sum(j.get("counters", {}).get("prefilter_drop", 0) for j in run["jobs"]))
                update["coverage_limited"] = any(j.get("coverage_limited") for j in run["jobs"])
                if update["pending_verification"] and update["status"] == "SUCCESS":
                    update["status"] = "PARTIAL"
            except Exception:
                # Saved raw and previously published progress survive a worker/read failure.
                update = dict(status="FAILED", warnings=list(dict.fromkeys(job.get('warnings',[])+["CRAWL_FAILED" if mode=='CRAWL' else "SEARCH_FAILED"])))
            finally:
                if store:
                    store.close()
                with self.lock:
                    job.update(update)
                    self.running = False
        threading.Thread(target=work, daemon=True).start()
        return dict(job)

    def get(self, identifier):
        with self.lock:
            return dict(self.jobs[identifier]) if identifier in self.jobs else None

    def active(self):
        with self.lock:
            return next((dict(job) for job in self.jobs.values() if job["status"] == "RUNNING"), None)


def make_handler(database, config_dir, service=None, conversation_db=None):
    service = service or SearchService(database, config_dir, enable_scheduler=True, conversation_db=conversation_db)
    from engine.classification_worker import DEFAULT_DB
    from engine.classification_service import ClassificationService
    raw_database = Path(conversation_db or service.conversation_db)
    classifier=ClassificationService(raw_database)
    from engine.dashboard_workspace import Workspace, WorkspaceError
    from engine.threads_service import ThreadsError
    workspace=Workspace(database,raw_database,config_dir,classifier,service)
    class Handler(BaseHTTPRequestHandler):
        def json_response(self, payload, status=200):
            self.respond(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in {"/api/search", "/api/crawl", "/api/schedule", "/api/library/review", "/api/classifications/run", "/api/reviews", "/api/classifications/retry",'/api/acquisition/runs','/api/acquisition/cancel','/api/acquisition/queries','/api/acquisition/schedule','/api/runtime/catchup'}:
                self.send_error(404)
                return
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if self.headers.get("Origin") not in expected or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.json_response(dict(error="Yêu cầu không hợp lệ."), 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= (262144 if path=='/api/reviews' else 8192):
                    raise ValueError("Dữ liệu nhập quá lớn hoặc rỗng.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Dữ liệu nhập không hợp lệ.")
                if path=='/api/acquisition/runs':
                    self.json_response(service.threads.start(payload),202)
                elif path=='/api/acquisition/cancel':
                    self.json_response(service.threads.cancel(payload.get('run_id')))
                elif path=='/api/acquisition/schedule':
                    self.json_response(service.threads.configure_schedule(payload))
                elif path=='/api/acquisition/queries':
                    from engine.threads_registry import ThreadsRegistry
                    try:ThreadsRegistry(config_dir).update_queries(payload.get('queries'),payload.get('expected_version'))
                    except ValueError as error:raise ThreadsError('QUERY_VERSION_CONFLICT' if str(error)=='QUERY_VERSION_CONFLICT' else 'INVALID_QUERY','Không lưu được truy vấn. Nạp lại và kiểm tra tên, dự án, trạng thái.',409 if str(error)=='QUERY_VERSION_CONFLICT' else 400) from None
                    self.json_response(service.threads.catalog())
                elif path == '/api/reviews':
                    self.json_response(workspace.save_reviews(payload))
                elif path == '/api/classifications/retry':
                    self.json_response(workspace.retry(payload))
                elif path == '/api/runtime/catchup':
                    self.json_response(service.recovery_tick())
                elif path == "/api/classifications/run":
                    self.json_response(classifier.start(),202)
                elif path == "/api/library/review":
                    if str(payload.get('record_id','')).startswith('v2:'):
                        from src.storage.conversations import ConversationStore
                        store = ConversationStore(raw_database)
                        try:
                            node_id = payload['record_id'][3:]
                            store.review(node_id, payload.get('status'), payload.get('note',''))
                            row = store.db.execute('SELECT payload FROM node_reviews WHERE node_id=?',(node_id,)).fetchone()
                            self.json_response(json.loads(row[0]))
                        finally:
                            store.close()
                        return
                    store = AcquisitionStore(database)
                    try:
                        self.json_response(store.review_content(payload.get("record_id"), payload.get("status"), payload.get("note", "")))
                    finally:
                        store.close()
                elif path == "/api/schedule":
                    self.json_response(service.configure_schedule(payload))
                else:
                    self.json_response(service.start(payload, "CRAWL" if path == "/api/crawl" else "SEARCH"), 202)
            except (WorkspaceError,ThreadsError) as exc:
                self.json_response({'error':str(exc),'code':exc.code,**exc.details},exc.status)
            except SearchAlreadyRunning as exc:
                self.json_response(dict(error=str(exc), code="SEARCH_RUNNING", job_id=exc.job_id, mode=exc.mode), 409)
            except ValueError as exc:
                safe_messages = {
                    "Mỗi nhóm nhận tối đa 3 truy vấn, mỗi truy vấn tối đa 150 ký tự.",
                    "Nhập ít nhất một keyword hoặc hashtag.",
                    "Khoảng ngày không hợp lệ.",
                    "Ngày bắt đầu phải trước ngày kết thúc; không chọn ngày tương lai.",
                    "Nguồn Google chưa sẵn sàng. Kiểm tra cấu hình và API key.",
                    "Dữ liệu nhập quá lớn hoặc rỗng.",
                    "Dữ liệu nhập không hợp lệ.",
                    "Chế độ thu thập không hợp lệ.",
                    "Chưa có group Facebook được bật và sẵn sàng crawl.",
                    "Chu kỳ crawl phải từ 5 đến 1440 phút.",
                    "Khoảng thời gian của lịch không hợp lệ.",
                    "Lookback phải từ 1 phút đến 30 ngày.",
                    "Trạng thái lịch crawl không hợp lệ.",
                    "Không lưu được lịch crawl.",
                    "Cần chọn từ 1 đến 4 khung giờ trong ngày.",
                    "Giờ phải có định dạng HH:MM.",
                    "Giờ bắt đầu phải trước giờ kết thúc trong cùng ngày.",
                    "Các khung giờ crawl không được chồng nhau.",
                    "Chu kỳ nhỏ nhất/lớn nhất phải từ 5 đến 1440 phút và đúng thứ tự.",
                }
                message = str(exc)
                if message == "Hashtag must be nonempty and have no spaces":
                    message = "Hashtag không được chứa khoảng trắng. Ví dụ: #VinCons."
                elif message not in safe_messages:
                    message = "Dữ liệu nhập hoặc cấu hình tìm kiếm không hợp lệ."
                self.json_response(dict(error=message), 400)
            except KeyError:
                self.json_response(dict(error="Kiểm tra keyword/hashtag, khoảng ngày hoặc lượt tìm kiếm đang chạy."), 400)
            except Exception:
                self.json_response(dict(error='Chưa xử lý được yêu cầu. Dữ liệu đã lưu được giữ; thử lại hoặc kiểm tra tiến trình ứng dụng.'),503)

        def do_GET(self):
            path = urlsplit(self.path).path
            params={key:values[0] for key,values in parse_qs(urlsplit(self.path).query).items()}
            if path=='/api/acquisition/catalog' or path=='/api/acquisition/runs' or path.startswith('/api/acquisition/runs/'):
                try:
                    if path=='/api/acquisition/catalog':self.json_response(service.threads.catalog())
                    elif path=='/api/acquisition/runs':self.json_response({'runs':service.threads.history()})
                    else:
                        run=service.threads.get(path.rsplit('/',1)[1])
                        if not run:raise ThreadsError('RUN_NOT_FOUND','Không tìm thấy lượt thu thập.',404)
                        self.json_response(run)
                except ThreadsError as exc:self.json_response({'error':str(exc),'code':exc.code,**exc.details},exc.status)
                return
            if path == '/api/runtime/status':
                try:self.json_response(service.runtime_status())
                except Exception:self.json_response({'code':'RUNTIME_BUSY','error':'Trạng thái vận hành đang bận; thử lại sau.'},503)
                return
            if path in {'/api/views','/api/views/version','/api/catalog','/api/health','/api/views/export.xlsx','/api/classifications/preview'} or path.startswith(('/api/records/','/api/threads/')):
                try:
                    if path=='/api/views':self.json_response(workspace.view(params))
                    elif path=='/api/views/version':self.json_response(workspace.data_version())
                    elif path=='/api/catalog':self.json_response(workspace.catalog())
                    elif path=='/api/health':self.json_response(workspace.health(lightweight=True) if params.get('lightweight')=='1' else workspace.health())
                    elif path=='/api/classifications/preview':self.json_response(workspace.preview())
                    elif path=='/api/views/export.xlsx':
                        self.respond(workspace.export(params.get('view_id','')),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='social-listening-report.xlsx')
                    elif path.startswith('/api/records/'):self.json_response(workspace.detail(path.rsplit('/',1)[1]))
                    else:self.json_response(workspace.thread(path.rsplit('/',1)[1],params))
                except WorkspaceError as exc:self.json_response({'error':str(exc),'code':exc.code,**exc.details},exc.status)
                except (ValueError,TypeError,KeyError):self.json_response({'error':'Điều kiện hoặc dữ liệu nhập không hợp lệ. Kiểm tra thời gian và lựa chọn.'},400)
                except Exception:self.json_response({'error':'Chưa đọc được dữ liệu. Thử lại hoặc kiểm tra tiến trình ứng dụng.'},503)
                return
            if path == "/api/library/export.xlsx":
                from engine.library_export import export_library
                try:
                    filters = {key: values[0] for key, values in parse_qs(urlsplit(self.path).query).items()}
                    body = export_library(database, filters, Registry(config_dir).sources, load_projects(config_dir),conversation_db=raw_database)
                    filename = "vincons-library-" + datetime.now(VN).strftime("%Y%m%d-%H%M%S") + ".xlsx"
                    self.respond(body, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
                except (ValueError, TypeError):
                    self.json_response(dict(error="Bộ lọc xuất Excel không hợp lệ."), 400)
                return
            if path == "/api/library":
                from engine.conversation_library import library
                try:
                    filters = {key: values[0] for key, values in parse_qs(urlsplit(self.path).query).items()}
                    self.json_response(library(database, raw_database, filters, Registry(config_dir).sources, projects=load_projects(config_dir)))
                except (ValueError, TypeError):
                    self.json_response(dict(error="Bộ lọc kho dữ liệu không hợp lệ."), 400)
                return
            if path == "/api/classifications":
                try:
                    registry=Registry(config_dir)
                    params={key:values[0] for key,values in parse_qs(urlsplit(self.path).query).items()}
                    rows=classifier.rows(refresh=params.get('refresh')=='1')
                    for row in rows:
                        row['groups']=[registry.sources.get(s,{}).get('name',s) for s in row['source_ids']]
                    from src.analysis.taxonomy import load_snapshot
                    taxonomy=load_snapshot(classifier.taxonomy_dir)
                    from engine.classification_view import query_rows
                    view=query_rows(rows,params) if params else {'rows':rows}
                    self.json_response({**view,'sources':[{'source_id':sid,'name':s['name']} for sid,s in registry.sources.items() if s['source_type']=='FACEBOOK_GROUP'],
                        'issues':[{'issue_id':i['issue_id'],'name':i['name'],
                            'project_ids':[p['project_id'] for p in taxonomy['profiles'].values() if i['issue_id'] in p['issue_priorities']]}
                            for i in taxonomy['catalog']['issues']],
                        'projects':[{'project_id':p['project_id'],'name':p['name']} for p in taxonomy['profiles'].values()],**classifier.status()})
                except ValueError:
                    self.json_response({'error':'Bộ lọc phân loại không hợp lệ. Kiểm tra khoảng ngày.'},400)
                except Exception:
                    self.json_response({'error':'Chưa đọc được kho phân loại.'},503)
                return
            if path == "/api/schedule":
                self.json_response(service.schedule_status())
                return
            if path == "/dashboard.js":
                self.respond(Path(__file__).with_name("dashboard.js").read_bytes(), "text/javascript; charset=utf-8")
                return
            if path in {"/dashboard_classification.js", "/dashboard.css", "/dashboard_workspace.js", "/dashboard_workspace.css",'/dashboard_threads.js'}:
                self.respond(Path(__file__).with_name(path[1:]).read_bytes(), "text/css; charset=utf-8" if path.endswith('.css') else "text/javascript; charset=utf-8")
                return
            if path == "/api/results":
                params = parse_qs(urlsplit(self.path).query)
                payload = {key:params[key][0] for key in ("start_date","end_date") if key in params}
                payload.update(keywords=[v.strip() for v in params.get("keywords",["VinCons"])[0].split(",") if v.strip()],
                               hashtags=[v.strip() for v in params.get("hashtags",[""])[0].split(",") if v.strip()])
                try:
                    mode = params.get("mode", ["SEARCH"])[0]
                    if mode not in {"SEARCH", "CRAWL"}:
                        raise ValueError("Chế độ thu thập không hợp lệ.")
                    terms,window=search_input(payload) if mode == "SEARCH" else (None, date_window(payload))
                    registry=Registry(config_dir)
                    if mode == 'CRAWL':
                        from engine.dashboard_conversations import results
                        self.json_response(dict(rows=results(raw_database,window,registry.sources,load_projects(config_dir),params.get('project_id',[''])[0]),pipeline='RAW_V2_THREADS'))
                        return
                    rows=search_output(database,window=window,terms=terms,
                        source_names={sid:s["name"] for sid,s in registry.sources.items()}, sources=registry.sources,
                        projects=load_projects(config_dir), project_id=params.get('project_id', [''])[0])
                    self.json_response(dict(rows=[row for row in rows if row["platform"] == "facebook"] if mode == "CRAWL" else rows))
                except (ValueError,KeyError):
                    self.json_response(dict(error="Khoảng ngày hoặc truy vấn không hợp lệ."),400)
                return
            if path == "/api/jobs/active":
                self.json_response(dict(job=service.active()))
                return
            if path.startswith("/api/jobs/"):
                job = service.get(path.rsplit("/", 1)[1])
                self.json_response(job or dict(code="JOB_NOT_FOUND",
                    error="Phiên theo dõi lượt chạy không còn khả dụng. Dữ liệu đã lưu vẫn có trong Kho dữ liệu và Lịch sử thu thập."), 200 if job else 404)
                return
            if path == "/api/options":
                registry = Registry(config_dir)
                self.json_response(dict(today=datetime.now(VN).date().isoformat(),
                                        projects=[p for p in load_projects(config_dir).values() if p['enabled']],
                                        keywords=list(dict.fromkeys(registry.queries["vincons_ecosystem"]["discovery_terms"] + ["VinCons kẹt xe", "VinCons phản ánh"])),
                                        hashtags=registry.queries["vincons_ecosystem"]["hashtags"],
                                        groups=[dict(source_id=sid, name=registry.sources[sid]["name"], url=registry.sources[sid]["url"],
                                                     ready=registry.readiness(registry.sources[sid]) is None)
                                                for sid in registry.watchlists["vincons_acquisition_v1"]["source_ids"]
                                                if registry.sources[sid]["source_type"] == "FACEBOOK_GROUP"]))
                return
            if path not in {"/", "/api/snapshot"}:
                self.send_error(404)
                return
            try:
                if path == "/":
                    body = Path(__file__).with_name("dashboard_workspace.html").read_bytes()
                    mime = "text/html; charset=utf-8"
                else:
                    body = json.dumps(snapshot(database, config_dir), ensure_ascii=False).encode("utf-8")
                    mime = "application/json; charset=utf-8"
            except Exception:
                self.send_error(503, "Local data unavailable")
                return
            self.respond(body, mime)

        def respond(self, body, mime, status=200, filename=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Browser navigation/refresh can close a polling response.

        def log_message(self, format, *args):
            pass
    Handler.acquisition_service = service
    return Handler


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=False

    def server_bind(self):
        if os.name=='nt':
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description="Local Google social search and video output")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "sessions/acquisition/acquisition.sqlite3")
    parser.add_argument("--config-dir", type=Path, default=PROJECT_ROOT / "config")
    from engine.classification_worker import DEFAULT_DB
    parser.add_argument('--conversation-db',type=Path,default=None,help='Optional override; defaults to the same --db')
    args = parser.parse_args()
    # Claim the port before constructing services or starting any scheduler.
    try:server = DashboardHTTPServer(("127.0.0.1", args.port), BaseHTTPRequestHandler)
    except OSError as error:
        parser.error(f"Không mở được cổng {args.port}. Nếu dashboard đang chạy, mở http://127.0.0.1:{args.port} thay vì chạy thêm một tiến trình. ({error.errno})")
    try:
        server.RequestHandlerClass=make_handler(args.db,args.config_dir,conversation_db=args.conversation_db)
        print(f"Dashboard: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service=getattr(server.RequestHandlerClass,'acquisition_service',None)
        if service:service.close()
        server.server_close()


if __name__ == "__main__":
    main()
