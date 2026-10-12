"""One-page SerpApi discovery with persistent, pre-request quota reservations."""
import os
import requests
from src.acquisition.identity import identify, resolve_redirects
from src.acquisition.models import AccessProbeResult, AdapterError, Candidate, CandidateBatch


def google_query(platform, term):
    domains = {"facebook": "facebook.com/groups", "tiktok": "tiktok.com", "youtube": "youtube.com"}
    escaped = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'site:{domains[platform]} "{escaped}"'


class GoogleSocialAdapter:
    def __init__(self, reserve_request, http=None):
        self.reserve_request = reserve_request
        self.http = http or requests

    def probe_access(self, source):
        from datetime import datetime, timedelta, timezone
        import uuid
        from src.acquisition.models import Deadline, DiscoveryRequest, Window
        now = datetime.now(timezone.utc)
        term = source.get("probe_query", "VinCons")
        request = DiscoveryRequest(source, "probe_"+uuid.uuid4().hex, Window(now-timedelta(minutes=180), now), Deadline(120), "SOCIAL_LINK_DISCOVERY", max_candidates=1, effective_query=google_query("facebook", term))
        batch = self.discover(request)
        return AccessProbeResult("ACCESSIBLE" if batch.status in {"SUCCESS", "NO_NEW_DATA"} else batch.status, batch.error_code)

    def discover(self, request):
        key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if not key:
            return CandidateBatch(status="AUTH_REQUIRED", error_code="SERPAPI_KEY_MISSING", attempts=0)
        batch = CandidateBatch(observed_order="RELEVANCE", coverage_limited=True, stop_reason="ONE_PAGE_LIMIT", attempts=0)
        for attempt in range(2):
            try:
                request.deadline.check()
                if not self.reserve_request(request.crawl_run_id):
                    raise AdapterError("BUDGET_EXHAUSTED", "LOCAL_REQUEST_QUOTA")
                batch.attempts += 1
                params = {"engine": "google", "api_key": key, "q": request.effective_query, "gl": "vn", "hl": "vi", "start": 0}
                if request.source.get("search_date_filter") == "WINDOW":
                    # Google filters by calendar date, not an exact publication
                    # timestamp. Native-platform verification remains required.
                    params["tbs"] = ("cdr:1,cd_min:" + request.window.start.strftime("%m/%d/%Y")
                                     + ",cd_max:" + request.window.end.strftime("%m/%d/%Y"))
                response = self.http.get("https://serpapi.com/search.json", params=params, timeout=min(25, request.deadline.remaining()), allow_redirects=False)
                if response.status_code in {401, 403}:
                    raise AdapterError("AUTH_REQUIRED", "SERPAPI_INVALID_KEY")
                if response.status_code == 429:
                    raise AdapterError("RATE_LIMITED", "SERPAPI_RATE_LIMIT")
                if response.status_code >= 500:
                    if attempt == 0:
                        continue
                    raise AdapterError("SOURCE_UNAVAILABLE", "SERPAPI_SERVER_ERROR")
                if response.status_code != 200:
                    raise AdapterError("EXTRACTION_FAILED", "SERPAPI_HTTP_ERROR")
                data = response.json()
                if not isinstance(data, dict):
                    raise AdapterError("EXTRACTION_FAILED", "SERPAPI_RESPONSE_INVALID")
                if data.get("error"):
                    error = str(data["error"]).casefold()
                    if any(token in error for token in ("quota", "run out", "searches left", "plan", "limit")):
                        raise AdapterError("BUDGET_EXHAUSTED", "SERPAPI_PROVIDER_QUOTA")
                    if "key" in error:
                        raise AdapterError("AUTH_REQUIRED", "SERPAPI_INVALID_KEY")
                    if "hasn't returned any results" in error:
                        return CandidateBatch(status="NO_NEW_DATA", stop_reason="EXPLICIT_EMPTY_PROVIDER", attempts=batch.attempts)
                    raise AdapterError("EXTRACTION_FAILED", "SERPAPI_PROVIDER_ERROR")
                rows = data.get("organic_results")
                if not isinstance(rows, list):
                    raise AdapterError("EXTRACTION_FAILED", "SERPAPI_ORGANIC_RESULTS_MISSING")
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("link"), str):
                        raise AdapterError("EXTRACTION_FAILED", "SERPAPI_RESULT_INVALID")
                    if any(row.get(key) is not None and not isinstance(row[key], str) for key in ("title", "snippet")) or (row.get("position") is not None and (type(row["position"]) is not int or row["position"] < 1)):
                        raise AdapterError("EXTRACTION_FAILED", "SERPAPI_RESULT_INVALID")
                    try:
                        target = identify(row["link"])
                    except ValueError:
                        continue
                    original_target_url = target.url
                    if not target.item_id and target.kind == "CONTENT_ITEM" and target.origin is None:
                        from urllib.parse import urlsplit
                        if urlsplit(target.url).hostname in {"vm.tiktok.com", "vt.tiktok.com", "fb.watch"}:
                            try:
                                target = resolve_redirects(target.url, request.deadline, self.http)
                            except (ValueError, requests.RequestException):
                                pass  # Remains unresolved; cannot pass target source gate.
                    candidate = Candidate(target.platform, original_target_url, target.url, request.source["source_id"], request.crawl_run_id, "GOOGLE_SERPAPI", candidate_kind=target.kind, platform_item_id=target.item_id, origin_source_ref=target.origin, title=row.get("title"), search_snippet=row.get("snippet"), query_id=request.query_id, query_type=request.query_type, search_keyword=request.search_keyword, effective_query=request.effective_query, position=row.get("position"), evidence_provenance=["SEARCH_SNIPPET"], missing_data_reasons=["PLATFORM_CONTENT_UNVERIFIED", "PUBLICATION_TIME_UNRESOLVED"])
                    batch.candidates.append(candidate)
                    if len(batch.candidates) >= request.max_candidates:
                        batch.stop_reason = "ITEM_LIMIT"
                        return batch
                if not batch.candidates:
                    batch.status, batch.stop_reason = "NO_NEW_DATA", "NO_ALLOWED_RESULTS"
                return batch
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 0 and request.deadline.remaining() > 1:
                    continue
                batch.status, batch.error_code = "SOURCE_UNAVAILABLE", "SERPAPI_NETWORK_ERROR"
            except AdapterError as error:
                batch.status, batch.error_code = ("PARTIAL" if batch.candidates else error.status), error.code
                batch.stop_reason = error.code
                return batch
            except (ValueError, requests.RequestException):
                batch.status, batch.error_code = "EXTRACTION_FAILED", "SERPAPI_RESPONSE_INVALID"
                batch.stop_reason = batch.error_code
                return batch
        return batch

    def fetch_item(self, candidate, context):
        raise AdapterError("SKIPPED", "GOOGLE_IS_DISCOVERY_ONLY")
