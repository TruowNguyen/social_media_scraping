"""Reclassify persisted recruitment; remove content and retain rejection audit only."""
import argparse
from dataclasses import fields
from pathlib import Path

from src.acquisition.models import Candidate
from src.acquisition.prefilter import apply_prefilter
from src.storage.acquisition import AcquisitionStore
from src.browser.profiles import PROJECT_ROOT


def stored_candidate(payload):
    allowed = {field.name for field in fields(Candidate)}
    values = {key: value for key, value in payload.items() if key in allowed}
    values["schema_version"] = "acquisition-candidate-v1"
    values.setdefault("candidate_kind", payload.get("entry_kind", "CONTENT_ITEM"))
    values.setdefault("discovered_via", "STORED_CONTENT_CLEANUP")
    return Candidate(**values)


def purge_recruitment(store, *, apply=False):
    result = dict(records_removed=0, queue_removed=0, missing_content=0, applied=apply)
    with store.transaction():
        records = store.export_records()
        queue = store.list_queue()
        for kind, entries in (("records", records), ("queue", queue)):
            for entry in entries:
                candidate = stored_candidate(entry["candidate"] if kind == "records" else entry)
                if kind == "records" and not (candidate.raw_text or candidate.caption or candidate.title):
                    result["missing_content"] += 1
                apply_prefilter(candidate)
                if candidate.prefilter_decision == "DROP" and candidate.drop_reason == "RECRUITMENT":
                    result[kind + "_removed"] += 1
                    if apply:
                        store.reject(candidate)
    return result


def main():
    parser = argparse.ArgumentParser(description="Purge stored recruitment evidence; dry-run unless --apply")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "sessions/acquisition/acquisition.sqlite3")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        parser.error("Database does not exist")
    store = AcquisitionStore(args.db)
    try:
        import json
        print(json.dumps(purge_recruitment(store, apply=args.apply)))
    finally:
        store.close()


if __name__ == "__main__": main()
