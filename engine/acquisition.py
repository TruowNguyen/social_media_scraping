"""Manual acquisition orchestration, source isolation and approval routing."""
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
import hashlib
import time
import uuid

from engine.registry import Registry
from src.acquisition.browser import browser_job
from src.acquisition.browser_adapters import FacebookGroupAdapter, TikTokSearchAdapter
from src.acquisition.google import GoogleSocialAdapter, google_query
from src.acquisition.identity import identify, hashtag_query, identity
from src.acquisition.models import AdapterError, Candidate, Deadline, DiscoveryRequest, FetchContext, Window, utcnow
from src.acquisition.prefilter import apply_prefilter
from src.acquisition.youtube import YouTubeItemAdapter


@contextmanager
def adapter_job(source, deadline, store):
    platform = source["platform"]
    if platform in {"facebook", "tiktok"}:
        with browser_job(platform, deadline) as page:
            yield FacebookGroupAdapter(page, deadline) if platform == "facebook" else TikTokSearchAdapter(page, deadline)
    elif platform == "google":
        yield GoogleSocialAdapter(store.reserve_request)
    elif platform == "youtube":
        yield YouTubeItemAdapter()
    else:
        raise AdapterError("SKIPPED", "UNSUPPORTED_SOURCE")


def query_jobs(source, query_sets):
    if source["source_type"] == "FACEBOOK_GROUP":
        yield dict(mode="RECENT_SOURCE_ITEMS")
    elif source["source_type"] in {"TIKTOK_SEARCH", "GOOGLE_SEARCH"}:
        scope = source.get("query_scope")
        if scope:
            query_sets = [dict(query_set_id=source["source_id"], discovery_terms=[], hashtags=[scope["search_keyword"]])]
        for query_set in query_sets:
            for query_type, terms in (("KEYWORD", query_set["discovery_terms"]), ("HASHTAG", query_set["hashtags"])):
                for term in terms:
                    targets = ("facebook", "tiktok", "youtube") if source["platform"] == "google" else ("tiktok",)
                    for target in targets:
                        mode = "SOCIAL_LINK_DISCOVERY" if source["platform"] == "google" else "HASHTAG_SEARCH" if query_type == "HASHTAG" else "KEYWORD_SEARCH"
                        effective = google_query(target, term) if source["platform"] == "google" else hashtag_query(term) if query_type == "HASHTAG" else term
                        query_id = "q_" + hashlib.sha256((query_set["query_set_id"] + query_type + target + term).encode()).hexdigest()[:20]
                        yield dict(mode=mode, query_id=query_id, query_type=query_type, search_keyword=term, effective_query=effective)


class AcquisitionEngine:
    def __init__(self, registry, store, factory=adapter_job, raw_store=None):
        self.registry, self.store, self.factory = registry, store, factory
        self.raw_store = raw_store

    def run(self, watchlist_id, window=None, source_ids=None, max_candidates=None, source_seconds=120, run_seconds=1200):
        if not 0 < source_seconds <= 120 or not 0 < run_seconds <= 1200:
            raise ValueError("Pilot time budgets must be <=120/job and <=1200/run")
        watchlist = self.registry.watchlists[watchlist_id]
        if not watchlist["enabled"]:
            raise ValueError("Watchlist is disabled; explicitly enable after verification")
        end = datetime.now(timezone.utc)
        window = window or Window(end - timedelta(minutes=watchlist["retrieval"]["lookback_minutes"]), end)
        run_id = "run_" + uuid.uuid4().hex
        run_deadline = Deadline(run_seconds)
        run = dict(crawl_run_id=run_id, status="RUNNING", started_at=utcnow(), window_start=window.start.isoformat(), window_end=window.end.isoformat(), config_snapshot=self.registry.documents, jobs=[])
        self.store.put_run(run_id, run)
        ids = source_ids or watchlist["source_ids"]
        if any(source_id not in watchlist["source_ids"] for source_id in ids):
            raise ValueError("Requested source outside watchlist")
        for source_id in ids:
            source = self.registry.sources[source_id]
            reason = self.registry.readiness(source)
            if reason:
                outcome = dict(job_id=source_id, source_id=source_id, status="SKIPPED", error_code=reason, counters={})
                run["jobs"].append(outcome)
                self.store.put_outcome(run_id, source_id, outcome)
                continue
            jobs = list(query_jobs(source, [self.registry.queries[x] for x in watchlist["query_set_ids"]]))
            for index, query in enumerate(jobs):
                job_id = source_id + ":" + query.get("query_id", "recent")
                cap = 100 if source["platform"] == "facebook" else 50 if source["platform"] == "tiktok" else 100
                cap = min(cap, watchlist["retrieval"]["max_items_per_source"], max_candidates or cap)
                if type(cap) is not int or cap <= 0:
                    raise ValueError("Candidate cap must be positive")
                deadline = Deadline(source_seconds, run_deadline)
                request = DiscoveryRequest(source, run_id, window, deadline, max_candidates=cap, **query)
                outcome = self.run_job(request, watchlist, job_id)
                run["jobs"].append(outcome)
                self.store.put_outcome(run_id, job_id, outcome)
                self.store.put_run(run_id, run)
                if outcome["status"] in {"AUTH_REQUIRED", "ACCESS_DENIED", "RATE_LIMITED", "BUDGET_EXHAUSTED"} or outcome.get("error_code") in {"LOGIN_REQUIRED", "SESSION_EXPIRED", "CAPTCHA", "LOCAL_REQUEST_QUOTA", "SERPAPI_PROVIDER_QUOTA", "SERPAPI_INVALID_KEY"}:
                    outcome["queries_not_attempted"] = len(jobs) - index - 1
                    self.store.put_outcome(run_id, job_id, outcome)
                    break
        active = [job for job in run["jobs"] if job.get("error_code") != "SOURCE_DISABLED"]
        success = [job for job in active if job["status"] in {"SUCCESS", "NO_NEW_DATA"}]
        run["status"] = "SUCCESS" if active and len(success) == len(active) else "PARTIAL" if success or any(job.get("counters", {}).get("persisted", 0) for job in active) else "FAILED"
        if not active or all(job["status"] == "SKIPPED" for job in active):
            run["error_code"] = "NO_ELIGIBLE_SOURCE"
        run["finished_at"] = utcnow()
        run.pop("config_snapshot")
        # Keep the stored snapshot; output stays compact and contains no content.
        snapshot = dict(run, config_snapshot=self.registry.documents)
        self.store.put_run(run_id, snapshot)
        return run

    def run_job(self, request, watchlist, job_id):
        counters = dict(discovered=0, unique=0, new=0, existing=0, persisted=0, out_of_window=0, unknown_time=0, prefilter_pass=0, prefilter_drop=0, prefilter_review=0, queued=0, fetch_success=0, fetch_failed=0, api_attempts=0)
        outcome = dict(job_id=job_id, source_id=request.source["source_id"], query_id=request.query_id, query_type=request.query_type, search_keyword=request.search_keyword, effective_query=request.effective_query, status="SUCCESS", counters=counters, coverage_limited=False, media="NOT_RUN", llm="NOT_RUN", comments="NOT_RUN")
        started = time.monotonic()
        key = job_id + request.window.start.isoformat() + request.window.end.isoformat()
        try:
            with self.store.job_lock(key) as acquired:
                if not acquired:
                    raise AdapterError("SKIPPED", "SOURCE_WINDOW_IN_USE")
                request.deadline.check()
                with self.factory(request.source, request.deadline, self.store) as adapter:
                    probe_source = dict(request.source, probe_query=request.search_keyword or "VinCons", probe_query_type=request.query_type or "KEYWORD")
                    probe = adapter.probe_access(probe_source) if request.source["platform"] != "google" else None
                    if probe and probe.status != "ACCESSIBLE":
                        raise AdapterError(probe.status, probe.error_code or "ACCESS_PROBE_FAILED")
                    batch = adapter.discover(request)
                    outcome.update(status=batch.status, error_code=batch.error_code, coverage_limited=batch.coverage_limited, observed_order=batch.observed_order, stop_reason=batch.stop_reason, attempts=batch.attempts)
                    counters["api_attempts"] = batch.attempts if request.source["platform"] == "google" else 0
                    seen = set()
                    terminal_error = None
                    for candidate in batch.candidates:
                        counters["discovered"] += 1
                        if identity(candidate) in seen:
                            continue
                        seen.add(identity(candidate))
                        counters["unique"] += 1
                        if terminal_error:
                            # Retain eligible discovery metadata, without another fetch after auth/block.
                            self.prefilter_and_retain(candidate, counters)
                            continue
                        try:
                            self.process_candidate(candidate, request, watchlist, adapter, counters)
                        except AdapterError as error:
                            terminal_error = error
                            outcome.update(status="PARTIAL" if counters["persisted"] or counters["queued"] else error.status, error_code=error.code, coverage_limited=True, stop_reason=error.code)
                    if counters["fetch_failed"] and outcome["status"] in {"SUCCESS", "NO_NEW_DATA"}:
                        outcome["status"] = "PARTIAL"
                    if outcome["status"] == "SUCCESS" and not counters["new"] and not counters["queued"] and not counters["prefilter_drop"]:
                        outcome["status"] = "NO_NEW_DATA"
        except AdapterError as error:
            outcome.update(status="PARTIAL" if counters["persisted"] or counters["queued"] else error.status, error_code=error.code, coverage_limited=True)
        except Exception:
            outcome.update(status="PARTIAL" if counters["persisted"] else "EXTRACTION_FAILED", error_code="ACQUISITION_JOB_FAILED", coverage_limited=True)
        outcome["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return outcome

    def filter(self, candidate, counters):
        decision = apply_prefilter(candidate)
        exclusion = self.store.item_exclusion(candidate)
        if exclusion:
            decision = candidate.prefilter_decision = "DROP"
            candidate.rule_id = exclusion["rule_id"]
            candidate.drop_reason = exclusion["drop_reason"]
        counters["prefilter_" + decision.lower()] += 1
        if decision == "DROP":
            self.store.reject(candidate)
            return False
        return True

    def prefilter_and_retain(self, candidate, counters):
        if self.raw_store is not None and candidate.platform == 'facebook' and candidate.candidate_kind == 'CONTENT_ITEM':
            result = self.raw_store.ingest_candidate(candidate, 'source-stopped')
            counters['persisted'] += 1
            counters['new' if result['new'] else 'existing'] += 1
            return
        if not self.filter(candidate, counters):
            return
        if candidate.discovered_via == "GOOGLE_SERPAPI":
            self.store.enqueue(candidate, "SOURCE_NOT_READY", identify(candidate.canonical_url).source_type)
            counters["queued"] += 1
        elif candidate.window_status != "OUT_OF_WINDOW":
            candidate.extraction_status = "METADATA_ONLY"
            candidate.missing_data_reasons.append("FETCH_STOPPED_BY_SOURCE_ERROR")
            self.persist(candidate, counters)

    def persist(self, candidate, counters):
        if candidate.window_status == "UNKNOWN":
            counters["unknown_time"] += 1
            candidate.prefilter_decision = "REVIEW"
        _, new = self.store.save_candidate(candidate)
        counters["new" if new else "existing"] += 1
        counters["persisted"] += 1

    def process_candidate(self, candidate, request, watchlist, adapter, counters):
        if self.raw_store is not None and request.source['source_type'] == 'FACEBOOK_GROUP':
            self.process_raw_candidate(candidate, request, adapter, counters)
            return
        if not self.filter(candidate, counters):
            return
        if candidate.candidate_kind == "SOURCE_CONTAINER":
            self.store.enqueue(candidate, "CONTAINER_DISCOVERY", identify(candidate.canonical_url).source_type)
            counters["queued"] += 1
            return
        if candidate.window_status == "OUT_OF_WINDOW":
            counters["out_of_window"] += 1
            return
        existing = self.store.find_record(candidate)
        stored = self.store.record_payload(existing) if existing else None
        if stored:
            retained = Candidate(**{key: value for key, value in stored.items() if key in {field.name for field in fields(Candidate)}})
            if apply_prefilter(retained) == "DROP":
                retained.crawl_run_id = candidate.crawl_run_id
                self.store.reject(retained)
                counters["prefilter_drop"] += 1
                return
        if existing and (candidate.discovered_via == "GOOGLE_SERPAPI" or stored.get("extraction_status") == "FETCHED"):
            self.store.observation(candidate, record_id=existing)
            counters["existing"] += 1
            return
        if candidate.discovered_via == "GOOGLE_SERPAPI":
            target = self.registry.resolve_target(candidate, watchlist)
            if not target or self.registry.readiness(target):
                reason = "SOURCE_NOT_READY" if target else "UNKNOWN_ORIGIN_SOURCE" if not candidate.origin_source_ref else "UNAPPROVED_SOURCE"
                self.store.enqueue(candidate, reason, identify(candidate.canonical_url).source_type)
                counters["queued"] += 1
                return
            candidate.target_source_id = target["source_id"]
            try:
                if request.source["source_id"] == target["source_id"]:
                    fetched = adapter.fetch_item(candidate, FetchContext(target, request.window, request.deadline))
                else:
                    with self.factory(target, request.deadline, self.store) as target_adapter:
                        fetched = target_adapter.fetch_item(candidate, FetchContext(target, request.window, request.deadline))
            except AdapterError as error:
                self.store.enqueue(candidate, "SOURCE_NOT_READY", target["source_type"])
                counters["queued"] += 1
                counters["fetch_failed"] += 1
                raise AdapterError(error.status, "TARGET_" + error.code) from None
        else:
            try:
                fetched = adapter.fetch_item(candidate, FetchContext(request.source, request.window, request.deadline))
            except AdapterError as error:
                counters["fetch_failed"] += 1
                candidate.extraction_status = "METADATA_ONLY"
                candidate.missing_data_reasons.append(error.code)
                self.persist(candidate, counters)
                if error.status in {"AUTH_REQUIRED", "ACCESS_DENIED", "RATE_LIMITED", "BUDGET_EXHAUSTED"}:
                    raise
                return
        counters["fetch_success"] += 1
        candidate = fetched.candidate
        # Expanded text can reveal a previously hidden intent. Purge raw on DROP.
        if apply_prefilter(candidate) == "DROP":
            counters["prefilter_drop"] += 1
            self.store.reject(candidate)
            return
        candidate.window_status = request.window.status(candidate.published_at, candidate.publication_precision)
        if candidate.window_status == "OUT_OF_WINDOW":
            counters["out_of_window"] += 1
            return
        self.persist(candidate, counters)

    def process_raw_candidate(self, candidate, request, adapter, counters):
        if candidate.candidate_kind != 'CONTENT_ITEM':
            return
        # Durable discovery before network fetch; includes old parent posts as context.
        first = self.raw_store.ingest_candidate(candidate, 'discovery')
        counters['new' if first['new'] else 'existing'] += 1
        counters['persisted'] += 1
        try:
            fetched = adapter.fetch_item(candidate, FetchContext(request.source, request.window, request.deadline, raw_first=True))
            candidate = fetched.candidate
            counters['fetch_success'] += 1
        except AdapterError:
            counters['fetch_failed'] += 1
            # Raw discovery already committed; source outcome must disclose fetch failure.
            raise
        saved = self.raw_store.ingest_candidate(candidate, 'fetch')
        retained = self.raw_store.get(saved['node_id'])
        candidate.raw_text = retained['raw_text']
        decision = apply_prefilter(candidate)
        self.raw_store.filter_saved(saved['node_id'],
            {'prefilter_decision': decision, 'rule_id': candidate.rule_id, 'drop_reason': candidate.drop_reason},
            'legacy-rules-on-saved-raw-v1')
        counters['prefilter_' + decision.lower()] += 1
        if candidate.window_status == 'OUT_OF_WINDOW':
            counters['out_of_window'] += 1

    def process_discovery(self, discovery_id, watchlist_id, window):
        key = discovery_id + window.start.isoformat() + window.end.isoformat()
        with self.store.job_lock(key) as acquired:
            if not acquired:
                raise AdapterError("SKIPPED", "SOURCE_WINDOW_IN_USE")
            return self._process_discovery(discovery_id, watchlist_id, window)

    def _process_discovery(self, discovery_id, watchlist_id, window):
        entry = self.store.queue_entry(discovery_id)
        watchlist = self.registry.watchlists[watchlist_id]
        if entry["status"] != "APPROVED" or not watchlist["enabled"]:
            raise ValueError("Approved entry and enabled watchlist required")
        if entry["entry_kind"] != "CONTENT_ITEM":
            raise ValueError("Containers cannot be fetched as posts")
        source = self.registry.sources.get(entry["approved_source_id"])
        if not source or source["source_id"] not in watchlist["source_ids"] or self.registry.readiness(source):
            raise ValueError("Target source is not ready/in watchlist")
        lineage = self.store.queue_lineage(discovery_id)
        candidate = Candidate(entry["platform"], entry["source_url"], entry["canonical_url"], entry["source_id"], "run_"+uuid.uuid4().hex, "GOOGLE_SERPAPI", platform_item_id=entry["platform_item_id"], origin_source_ref=entry["origin_source_ref"], target_source_id=source["source_id"], title=entry["title"], search_snippet=entry["search_snippet"], query_id=lineage.get("query_id") or entry["query_id"], query_type=lineage.get("query_type"), search_keyword=lineage.get("search_keyword"), effective_query=lineage.get("effective_query"), evidence_provenance=["SEARCH_SNIPPET"])
        if not self.registry.matches_entry(entry, source):
            raise ValueError("Source identity mismatch")
        counters = dict(prefilter_pass=0, prefilter_drop=0, prefilter_review=0, queued=0, persisted=0, new=0, existing=0, unknown_time=0, out_of_window=0, fetch_success=0, fetch_failed=0)
        deadline = Deadline()
        report = dict(crawl_run_id=candidate.crawl_run_id, discovery_id=discovery_id, status="RUNNING", started_at=utcnow(), window_start=window.start.isoformat(), window_end=window.end.isoformat(), acquisition_source_id=candidate.source_id, target_source_id=source["source_id"])
        self.store.put_run(candidate.crawl_run_id, report)
        self.store.set_dispatch(discovery_id, "READY")
        try:
            request = DiscoveryRequest(source, candidate.crawl_run_id, window, deadline, "SOCIAL_LINK_DISCOVERY")
            with self.factory(source, deadline, self.store) as adapter:
                self.process_candidate(candidate, request, watchlist, adapter, counters)
            state = "OUT_OF_WINDOW" if counters["out_of_window"] else "FETCHED" if counters["persisted"] or counters["existing"] else "FAILED"
            if counters["prefilter_drop"]:
                report.update(status="SUCCESS", finished_at=utcnow(), counters=counters)
                self.store.put_run(candidate.crawl_run_id, report)
                return dict(discovery_id=discovery_id, status="DROPPED", counters=counters)
            self.store.set_dispatch(discovery_id, state)
            report.update(status="SUCCESS" if state in {"FETCHED", "OUT_OF_WINDOW"} else "FAILED", finished_at=utcnow(), counters=counters)
            self.store.put_run(candidate.crawl_run_id, report)
            return dict(discovery_id=discovery_id, status=state, counters=counters)
        except Exception as error:
            self.store.set_dispatch(discovery_id, "FAILED")
            report.update(status="FAILED", finished_at=utcnow(), error_code=error.code if isinstance(error, AdapterError) else "QUEUE_PROCESS_FAILED", counters=counters)
            self.store.put_run(candidate.crawl_run_id, report)
            raise
