"""Separate SQLite acquisition store, observation lineage, queue and budgets."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from src.acquisition.identity import identity, text_hash
from src.acquisition.models import utcnow


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class AcquisitionStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outcomes(run_id TEXT, job_id TEXT, payload TEXT, PRIMARY KEY(run_id,job_id));
          CREATE TABLE IF NOT EXISTS records(record_id TEXT PRIMARY KEY, payload TEXT NOT NULL, text_hash TEXT);
          CREATE TABLE IF NOT EXISTS content_reviews(record_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS content_review_history(id INTEGER PRIMARY KEY, record_id TEXT, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS content_relationships(left_id TEXT, right_id TEXT, kind TEXT, score REAL, PRIMARY KEY(left_id,right_id,kind));
          CREATE TABLE IF NOT EXISTS aliases(alias TEXT PRIMARY KEY, record_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS observations(candidate_id TEXT PRIMARY KEY, record_id TEXT, discovery_id TEXT, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS rejections(rejection_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS excluded_item_aliases(alias TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS queue(discovery_id TEXT PRIMARY KEY, identity TEXT UNIQUE, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS queue_aliases(alias TEXT PRIMARY KEY, discovery_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS review_history(id INTEGER PRIMARY KEY, discovery_id TEXT, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS registry_drafts(source_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS api_attempts(id INTEGER PRIMARY KEY, run_id TEXT, month TEXT, attempted_at TEXT);
          CREATE INDEX IF NOT EXISTS api_month ON api_attempts(month);
          CREATE TABLE IF NOT EXISTS job_locks(job_key TEXT PRIMARY KEY, expires REAL, owner TEXT);
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        if self.db.in_transaction:
            yield
            return
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def put_run(self, run_id, payload):
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (run_id, encode(payload)))

    def put_outcome(self, run_id, job_id, payload):
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?)", (run_id, job_id, encode(payload)))

    def reserve_request(self, run_id, run_cap=20, month_cap=200, now=None):
        stamp = now or utcnow()
        month = stamp[:7]
        self.db.execute("BEGIN IMMEDIATE")
        try:
            run_count = self.db.execute("SELECT count(*) FROM api_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
            month_count = self.db.execute("SELECT count(*) FROM api_attempts WHERE month=?", (month,)).fetchone()[0]
            if run_count >= run_cap or month_count >= month_cap:
                self.db.rollback()
                return False
            self.db.execute("INSERT INTO api_attempts(run_id,month,attempted_at) VALUES (?,?,?)", (run_id, month, stamp))
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    @contextmanager
    def job_lock(self, key, ttl=1200):
        owner = uuid.uuid4().hex
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("DELETE FROM job_locks WHERE expires<?", (time.time(),))
            self.db.execute("INSERT INTO job_locks VALUES (?,?,?)", (key, time.time()+ttl, owner))
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()
            yield False
            return
        try:
            yield True
        finally:
            with self.transaction():
                self.db.execute("DELETE FROM job_locks WHERE job_key=? AND owner=?", (key, owner))

    def find_record(self, candidate):
        records = self._record_ids(candidate)
        return records[0] if records else None

    def _record_ids(self, candidate):
        records = []
        for alias in self._aliases(candidate):
            row = self.db.execute("SELECT record_id FROM aliases WHERE alias=?", (alias,)).fetchone()
            if row and row[0] not in records:
                records.append(row[0])
        return records

    def _queue_ids(self, candidate):
        rows = []
        primary = self.db.execute("SELECT discovery_id FROM queue WHERE identity=?", (identity(candidate),)).fetchone()
        if primary:
            rows.append(primary[0])
        for alias in self._aliases(candidate):
            row = self.db.execute("SELECT discovery_id FROM queue_aliases WHERE alias=?", (alias,)).fetchone()
            if row and row[0] not in rows:
                rows.append(row[0])
        return rows

    def record_payload(self, record_id):
        row = self.db.execute("SELECT payload FROM records WHERE record_id=?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    @staticmethod
    def _aliases(candidate):
        urls = [candidate.canonical_url]
        if candidate.source_url != candidate.canonical_url:
            urls.append(candidate.source_url)
        return [identity(candidate)] + [f"{candidate.platform}:{candidate.candidate_kind}:url:{url}" for url in urls]

    def observation(self, candidate, record_id=None, discovery_id=None):
        fields = ("candidate_id", "source_id", "crawl_run_id", "query_id", "query_type", "search_keyword", "effective_query", "discovered_via", "target_source_id", "discovered_at", "collected_at", "evidence_provenance", "position", "window_status")
        payload = {key: getattr(candidate, key) for key in fields}
        with self.transaction():
            self.db.execute("""INSERT INTO observations VALUES (?,?,?,?)
              ON CONFLICT(candidate_id) DO UPDATE SET
                record_id=COALESCE(excluded.record_id, observations.record_id),
                discovery_id=COALESCE(excluded.discovery_id, observations.discovery_id),
                payload=excluded.payload""", (candidate.candidate_id, record_id, discovery_id, encode(payload)))

    def save_candidate(self, candidate):
        with self.transaction():
            return self._save_candidate(candidate)

    def _save_candidate(self, candidate):
        if candidate.prefilter_decision == "DROP" or candidate.candidate_kind != "CONTENT_ITEM" or self.item_exclusion(candidate):
            raise ValueError("Only eligible content items may be persisted")
        existing = self.find_record(candidate)
        record_id = existing or "item_" + uuid.uuid4().hex
        payload = candidate.payload()
        if existing:
            old = json.loads(self.db.execute("SELECT payload FROM records WHERE record_id=?", (existing,)).fetchone()[0])
            # Metadata-only rediscovery must not erase fetched evidence.
            for key in ("raw_text", "caption", "published_at", "publication_precision", "extraction_status", "media_refs"):
                if old.get(key) and (not payload.get(key) or (key == "extraction_status" and old[key] == "FETCHED")):
                    payload[key] = old[key]
        with self.transaction():
            # Resolve aliases that were stored before a native ID became known.
            for alias in self._aliases(candidate):
                other = self.db.execute("SELECT record_id FROM aliases WHERE alias=?", (alias,)).fetchone()
                if other and other[0] != record_id:
                    self.db.execute("UPDATE observations SET record_id=? WHERE record_id=?", (record_id, other[0]))
                    self.db.execute("UPDATE aliases SET record_id=? WHERE record_id=?", (record_id, other[0]))
                    self.db.execute("INSERT OR IGNORE INTO content_reviews SELECT ?,payload FROM content_reviews WHERE record_id=?", (record_id, other[0]))
                    self.db.execute("DELETE FROM content_reviews WHERE record_id=?", (other[0],))
                    self.db.execute("UPDATE content_review_history SET record_id=? WHERE record_id=?", (record_id, other[0]))
                    self.db.execute("DELETE FROM records WHERE record_id=?", (other[0],))
                    self.db.execute("DELETE FROM content_relationships WHERE left_id=? OR right_id=?", (other[0], other[0]))
            self.db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?)", (record_id, encode(payload), text_hash(payload.get("raw_text") or payload.get("caption"))))
            for alias in self._aliases(candidate):
                self.db.execute("INSERT OR REPLACE INTO aliases VALUES (?,?)", (alias, record_id))
            self.observation(candidate, record_id=record_id)
            self._relationships(record_id, payload)
        return record_id, not bool(existing)

    def _relationships(self, record_id, payload):
        text = payload.get("raw_text") or payload.get("caption") or ""
        digest = text_hash(text)
        if not digest:
            return
        tokens = set(text.casefold().split())
        for row in self.db.execute("SELECT record_id,payload,text_hash FROM records WHERE record_id<>? LIMIT 200", (record_id,)):
            other = json.loads(row[1])
            other_tokens = set((other.get("raw_text") or other.get("caption") or "").casefold().split())
            score = len(tokens & other_tokens) / len(tokens | other_tokens) if len(tokens) >= 5 and len(other_tokens) >= 5 else 0
            kind = "EXACT_TEXT" if row[2] == digest else "NEAR_TEXT" if score >= .85 else None
            if kind:
                left, right = sorted((record_id, row[0]))
                self.db.execute("INSERT OR REPLACE INTO content_relationships VALUES (?,?,?,?)", (left, right, kind, 1.0 if kind == "EXACT_TEXT" else score))

    def item_exclusion(self, candidate):
        for alias in self._aliases(candidate):
            row = self.db.execute("SELECT payload FROM excluded_item_aliases WHERE alias=?", (alias,)).fetchone()
            if row:
                return json.loads(row[0])
        return None

    def reject(self, candidate):
        if candidate.prefilter_decision != "DROP":
            raise ValueError("Expected DROP")
        key = hashlib.sha256((candidate.crawl_run_id + identity(candidate)).encode()).hexdigest()
        with self.transaction():
            if candidate.drop_reason == "RECRUITMENT":
                for alias in self._aliases(candidate):
                    self.db.execute("INSERT OR REPLACE INTO excluded_item_aliases VALUES (?,?)", (alias, encode(candidate.rejection())))
            for record_id in self._record_ids(candidate):
                self.db.execute("DELETE FROM content_reviews WHERE record_id=?", (record_id,))
                self.db.execute("DELETE FROM content_review_history WHERE record_id=?", (record_id,))
                self.db.execute("DELETE FROM records WHERE record_id=?", (record_id,))
                self.db.execute("DELETE FROM aliases WHERE record_id=?", (record_id,))
                self.db.execute("DELETE FROM observations WHERE record_id=?", (record_id,))
                self.db.execute("DELETE FROM content_relationships WHERE left_id=? OR right_id=?", (record_id, record_id))
            for discovery_id in self._queue_ids(candidate):
                self.db.execute("DELETE FROM queue WHERE discovery_id=?", (discovery_id,))
                self.db.execute("DELETE FROM queue_aliases WHERE discovery_id=?", (discovery_id,))
                self.db.execute("DELETE FROM observations WHERE discovery_id=?", (discovery_id,))
                # Earlier review snapshots can contain the formerly eligible snippet.
                # Clear-intent DROP retention overrides normal review-history retention.
                self.db.execute("DELETE FROM review_history WHERE discovery_id=?", (discovery_id,))
            self.db.execute("INSERT OR REPLACE INTO rejections VALUES (?,?)", (key, encode(candidate.rejection())))

    def review_content(self, record_id, status, note):
        from src.acquisition.prefilter import classify_payload
        if status not in {"UNREVIEWED", "RELEVANT", "IRRELEVANT", "NEEDS_REVIEW"} or not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Invalid content review")
        with self.transaction():
            candidate = self.record_payload(record_id)
            if not candidate or classify_payload(candidate).prefilter_decision == "DROP":
                raise ValueError("Content unavailable")
            from datetime import datetime, timezone
            payload = dict(status=status, note=note, updated_at=datetime.now(timezone.utc).isoformat())
            self.db.execute("INSERT OR REPLACE INTO content_reviews VALUES (?,?)", (record_id, encode(payload)))
            self.db.execute("INSERT INTO content_review_history(record_id,payload) VALUES (?,?)", (record_id, encode(payload)))
            return payload

    def enqueue(self, candidate, reason, proposed_source_type=None):
        with self.transaction():
            return self._enqueue(candidate, reason, proposed_source_type)

    def _enqueue(self, candidate, reason, proposed_source_type=None):
        if candidate.prefilter_decision == "DROP" or self.item_exclusion(candidate):
            raise ValueError("DROP cannot enter queue")
        key = identity(candidate)
        ids = self._queue_ids(candidate)
        if ids:
            entries = [self.queue_entry(identifier) for identifier in ids]
            rank = {"REJECTED": 0, "APPROVED": 1, "PENDING": 2}
            payload = min(entries, key=lambda entry: (rank[entry["status"]], entry["first_seen_at"]))
            discovery_id = payload["discovery_id"]
            payload["first_seen_at"] = min(entry["first_seen_at"] for entry in entries)
            for other in ids:
                if other != discovery_id:
                    self.db.execute("UPDATE observations SET discovery_id=? WHERE discovery_id=?", (discovery_id, other))
                    self.db.execute("UPDATE review_history SET discovery_id=? WHERE discovery_id=?", (discovery_id, other))
                    self.db.execute("UPDATE queue_aliases SET discovery_id=? WHERE discovery_id=?", (discovery_id, other))
                    self.db.execute("DELETE FROM queue WHERE discovery_id=?", (other,))
            payload["last_seen_at"] = candidate.discovered_at
            if not payload.get("platform_item_id") and candidate.platform_item_id:
                payload["platform_item_id"] = candidate.platform_item_id
                payload["canonical_url"] = candidate.canonical_url
            if not payload.get("origin_source_ref") and candidate.origin_source_ref:
                payload["origin_source_ref"] = candidate.origin_source_ref
        else:
            discovery_id = "dq_" + uuid.uuid4().hex
            payload = dict(schema_version="discovery-queue-entry-v1", discovery_id=discovery_id, entry_kind=candidate.candidate_kind, platform=candidate.platform, source_url=candidate.source_url, canonical_url=candidate.canonical_url, platform_item_id=candidate.platform_item_id, origin_source_ref=candidate.origin_source_ref, proposed_source_type=proposed_source_type, title=candidate.title, search_snippet=candidate.search_snippet, source_id=candidate.source_id, query_id=candidate.query_id, crawl_run_id=candidate.crawl_run_id, status="PENDING", reason=reason, first_seen_at=candidate.discovered_at, last_seen_at=candidate.discovered_at, approved_source_id=None, reviewed_by=None, reviewed_at=None, review_note=None, dispatch_state="NOT_READY")
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO queue VALUES (?,?,?)", (discovery_id, key, encode(payload)))
            for alias in self._aliases(candidate):
                self.db.execute("INSERT OR REPLACE INTO queue_aliases VALUES (?,?)", (alias, discovery_id))
            self.observation(candidate, discovery_id=discovery_id)
        return discovery_id

    def queue_entry(self, discovery_id):
        row = self.db.execute("SELECT payload FROM queue WHERE discovery_id=?", (discovery_id,)).fetchone()
        if not row:
            raise ValueError("Discovery ID not found")
        return json.loads(row[0])

    def queue_lineage(self, discovery_id):
        row = self.db.execute("SELECT payload FROM observations WHERE discovery_id=? ORDER BY rowid DESC LIMIT 1", (discovery_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def list_queue(self, status=None):
        entries = [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM queue")]
        return [entry for entry in entries if status is None or entry["status"] == status]

    def review(self, discovery_id, status, reviewer, note, source_id=None):
        with self.transaction():
            return self._review(discovery_id, status, reviewer, note, source_id)

    def _review(self, discovery_id, status, reviewer, note, source_id=None):
        if status not in {"PENDING", "APPROVED", "REJECTED"} or not reviewer.strip() or not note.strip():
            raise ValueError("Review requires status, reviewer and note")
        payload = self.queue_entry(discovery_id)
        if status != "PENDING" and payload["status"] != "PENDING":
            raise ValueError("Reopen before changing an existing decision")
        if status == "APPROVED" and not source_id:
            raise ValueError("Approval requires a resolved source ID")
        payload.update(status=status, reviewed_by=reviewer, reviewed_at=utcnow(), review_note=note, approved_source_id=source_id if status == "APPROVED" else None, dispatch_state="NOT_READY")
        with self.transaction():
            self.db.execute("UPDATE queue SET payload=? WHERE discovery_id=?", (encode(payload), discovery_id))
            self.db.execute("INSERT INTO review_history(discovery_id,payload) VALUES (?,?)", (discovery_id, encode(payload)))
        return payload

    def set_dispatch(self, discovery_id, state):
        payload = self.queue_entry(discovery_id)
        payload["dispatch_state"] = state
        with self.transaction():
            self.db.execute("UPDATE queue SET payload=? WHERE discovery_id=?", (encode(payload), discovery_id))

    def draft_sources(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM registry_drafts")]

    def save_draft(self, source):
        if source["enabled"] or source["verification_status"] != "PENDING_VERIFICATION":
            raise ValueError("New proposals must be draft and disabled")
        with self.transaction():
            self.db.execute("INSERT INTO registry_drafts VALUES (?,?)", (source["source_id"], encode(source)))

    def export_records(self):
        return [dict(record_id=row[0], candidate=json.loads(row[1])) for row in self.db.execute("SELECT record_id,payload FROM records")]
