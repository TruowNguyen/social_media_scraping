"""Legacy record_file behavior extracted without changing data policies."""

import bisect
import datetime
import json
import logging
import os

TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S UTC"

def parse_record_timestamp(value):
    """Parses a stored published_at string back into a datetime for sorting."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, TIMESTAMP_FMT).replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return None

class RecordFile:
    """One output JSON file, loaded on demand and kept sorted by published_at.

    Exists because keyword mode on the account-driven platforms (TikTok, Truth
    Social) walks accounts once but routes each post into the file of whichever
    keyword it matched, so a single pass has several output files open at the
    same time. Appending never overwrites prior runs: existing records are read
    back in, new ones are inserted in chronological position, and the file is
    only rewritten if something was actually added.
    """

    def __init__(self, path: str, logger=None):
        self.path = path
        self._logger = logger or logging.getLogger(__name__)
        self.records = []
        self.ids = set()
        self._sort_keys = []
        self.added = 0
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.records = json.load(f)
        except Exception as e:
            self._logger.error(f"Error loading {self.path}: {e}")
            self.records = []
            return
        for record in self.records:
            record_id = record.get("record_id")
            if record_id:
                self.ids.add(record_id)
            parsed = parse_record_timestamp((record.get("time_stamps") or {}).get("published_at"))
            self._sort_keys.append(parsed.timestamp() if parsed else 0.0)

    def has(self, record_id: str) -> bool:
        self._load()
        return record_id in self.ids

    def add(self, record: dict, published_dt=None):
        self._load()
        sort_key = published_dt.timestamp() if published_dt else 0.0
        index = bisect.bisect_right(self._sort_keys, sort_key)
        self.records.insert(index, record)
        self._sort_keys.insert(index, sort_key)
        record_id = record.get("record_id")
        if record_id:
            self.ids.add(record_id)
        self.added += 1

    def save(self) -> bool:
        """Writes the file if anything was added. Returns whether it wrote."""
        if not self.added:
            return False
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=4, ensure_ascii=False)
        self._logger.info(
            f"Appended {self.added} new sorted records to {self.path} (Total: {len(self.records)})."
        )
        return True
