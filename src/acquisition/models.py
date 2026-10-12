"""Versioned acquisition types, fixed UTC windows and shared deadlines."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol
import time
import uuid


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return result.astimezone(timezone.utc)


class AdapterError(Exception):
    """Only fixed, non-sensitive error codes may leave an adapter."""
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.start >= self.end:
            raise ValueError("Expected an aware, nonempty [start, end) window")

    def status(self, published_at, precision):
        if not published_at or precision != "INSTANT":
            return "UNKNOWN"
        return "IN_WINDOW" if self.start <= parse_utc(published_at) < self.end else "OUT_OF_WINDOW"


class Deadline:
    def __init__(self, seconds=120, parent=None):
        self.end = min(time.monotonic() + seconds, parent.end if parent else float("inf"))

    def remaining(self):
        return max(0.0, self.end - time.monotonic())

    def check(self):
        if not self.remaining():
            raise AdapterError("BUDGET_EXHAUSTED", "TIME_BUDGET")

    def milliseconds(self, cap=30000):
        self.check()
        return max(1, min(cap, int(self.remaining() * 1000)))


@dataclass
class Candidate:
    platform: str
    source_url: str
    canonical_url: str
    source_id: str
    crawl_run_id: str
    discovered_via: str
    schema_version: str = "acquisition-candidate-v1"
    candidate_id: str = field(default_factory=lambda: "obs_" + uuid.uuid4().hex)
    candidate_kind: str = "CONTENT_ITEM"
    platform_item_id: str | None = None
    origin_source_ref: str | None = None
    target_source_id: str | None = None
    query_id: str | None = None
    query_type: str | None = None
    search_keyword: str | None = None
    effective_query: str | None = None
    title: str | None = None
    caption: str | None = None
    search_snippet: str | None = None
    hashtags: list = field(default_factory=list)
    author: dict = field(default_factory=lambda: dict(platform_author_id=None, display_name=None, profile_url=None))
    engagement: dict = field(default_factory=lambda: dict(views=None, likes=None, comments=None, shares=None))
    media_refs: list = field(default_factory=list)
    published_at: str | None = None
    publication_precision: str = "UNKNOWN"
    published_time_raw: str | None = None
    publication_date: str | None = None
    window_status: str = "UNKNOWN"
    discovered_at: str = field(default_factory=utcnow)
    collected_at: str = field(default_factory=utcnow)
    prefilter_decision: str | None = None
    rule_id: str | None = None
    drop_reason: str | None = None
    extraction_status: str = "DISCOVERED"
    missing_data_reasons: list = field(default_factory=list)
    evidence_provenance: list = field(default_factory=list)
    raw_text: str | None = None
    content_type: str | None = None
    position: int | None = None

    def __post_init__(self):
        if self.platform not in {"facebook", "tiktok", "youtube"} or self.candidate_kind not in {"CONTENT_ITEM", "SOURCE_CONTAINER"}:
            raise ValueError("Unsupported candidate platform/kind")
        if self.schema_version != "acquisition-candidate-v1" or not all(isinstance(value, str) and value for value in (self.candidate_id, self.source_id, self.crawl_run_id, self.source_url, self.canonical_url)):
            raise ValueError("Candidate IDs, version and URLs must be nonempty strings")
        if self.platform_item_id is not None and not isinstance(self.platform_item_id, str):
            raise ValueError("Native IDs must be strings")
        for value in self.engagement.values():
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Engagement must be null or nonnegative integer")
        if self.published_at:
            self.published_at = parse_utc(self.published_at).isoformat().replace("+00:00", "Z")

    def payload(self):
        return asdict(self)

    def rejection(self):
        return {key: getattr(self, key) for key in ("platform_item_id", "source_id", "source_url", "crawl_run_id", "collected_at", "rule_id", "drop_reason")}


@dataclass
class DiscoveryRequest:
    source: dict
    crawl_run_id: str
    window: Window
    deadline: Deadline
    mode: str
    max_candidates: int = 100
    query_id: str | None = None
    query_type: str | None = None
    search_keyword: str | None = None
    effective_query: str | None = None
    listing_seconds: int | None = None
    stall_limit: int = 3

    def __post_init__(self):
        if self.mode not in {"RECENT_SOURCE_ITEMS", "KEYWORD_SEARCH", "HASHTAG_SEARCH", "SOCIAL_LINK_DISCOVERY"}:
            raise ValueError("Unsupported acquisition mode")
        if type(self.max_candidates) is not int or self.max_candidates <= 0:
            raise ValueError("Candidate quota must be a positive integer")
        if self.listing_seconds is not None and (type(self.listing_seconds) is not int or not 1<=self.listing_seconds<=300):
            raise ValueError('Invalid listing budget')
        if type(self.stall_limit) is not int or not 1<=self.stall_limit<=20:
            raise ValueError('Invalid listing stall limit')


@dataclass
class AccessProbeResult:
    status: str
    error_code: str | None = None
    checked_at: str = field(default_factory=utcnow)
    observed_public: bool | None = None
    requires_login: bool | None = None
    sample_item_ids: list = field(default_factory=list)


@dataclass
class CandidateBatch:
    candidates: list[Candidate] = field(default_factory=list)
    status: str = "SUCCESS"
    error_code: str | None = None
    stop_reason: str = "ENUMERATED"
    coverage_limited: bool = False
    observed_order: str = "UNKNOWN"
    attempts: int = 1


@dataclass
class FetchContext:
    source: dict
    window: Window
    deadline: Deadline
    raw_first: bool = False


@dataclass
class FetchResult:
    candidate: Candidate
    status: str = "SUCCESS"
    error_code: str | None = None


class SourceAdapter(Protocol):
    def probe_access(self, source: dict) -> AccessProbeResult: ...
    def discover(self, request: DiscoveryRequest) -> CandidateBatch: ...
    def fetch_item(self, candidate: Candidate, context: FetchContext) -> FetchResult: ...
