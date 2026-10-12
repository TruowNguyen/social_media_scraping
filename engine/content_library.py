"""Read retained acquisition evidence without starting a crawl or changing storage."""
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.acquisition.prefilter import classify_payload, normalize
from src.acquisition.identity import identify, source_references
from src.acquisition.projects import project_fields, selected_match, validate_project

STATUSES = {"UNREVIEWED", "RELEVANT", "IRRELEVANT", "NEEDS_REVIEW"}


def library(database, filters=None, sources=None, *, paginate=True, projects=None):
    filters, sources = filters or {}, sources or {}
    projects = projects or {}
    validate_project(filters.get('project_id'), projects, allow_unknown=True)
    page = int(filters.get("page", 1))
    if page < 1 or filters.get("review", "") not in STATUSES | {""}:
        raise ValueError("Invalid library filter")
    basis = filters.get("date_basis", "collected_at")
    if basis not in {"collected_at", "latest_collected_at", "published_at"}:
        raise ValueError("Invalid date basis")
    vn = timezone(timedelta(hours=7))
    bounds = [datetime.combine(date.fromisoformat(filters[key]), datetime.min.time(), vn)
              if filters.get(key) else None for key in ("start_date", "end_date")]
    if all(bounds) and bounds[0] > bounds[1]:
        raise ValueError("Invalid dates")
    if bounds[1]:
        bounds[1] += timedelta(days=1)
    output = dict(rows=[], total=0, page=page, page_size=20, sources=[], runs=[])
    database = Path(database)
    if not database.exists():
        return output
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        db.execute("BEGIN")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'records' not in tables or 'observations' not in tables:
            return output
        reviews = {r[0]: json.loads(r[1]) for r in db.execute("SELECT * FROM content_reviews")} if "content_reviews" in tables else {}
        observations = {}
        for record_id, payload in db.execute("SELECT record_id,payload FROM observations WHERE record_id IS NOT NULL"):
            observations.setdefault(record_id, []).append(json.loads(payload))
        rows, source_ids, run_ids = [], set(), set()
        for record_id, payload in db.execute("SELECT record_id,payload FROM records"):
            item = json.loads(payload)
            if item.get("prefilter_decision") == "DROP" or classify_payload(item).prefilter_decision == "DROP":
                continue
            obs = observations.get(record_id, [])
            runs = sorted({o.get("crawl_run_id") for o in obs if o.get("crawl_run_id")})
            sid = item.get("source_id")
            source_ids.add(sid) if sid else None
            run_ids.update(runs)
            review = reviews.get(record_id, dict(status="UNREVIEWED", note="", updated_at=None))
            resolved_sid = sid
            target = identify(item.get("canonical_url") or item.get("source_url") or "")
            if item.get("platform") == "facebook" and target.origin:
                matches = [key for key, source in sources.items() if source.get("source_type") == "FACEBOOK_GROUP" and target.origin in source_references(source)]
                if len(matches) == 1:
                    resolved_sid = matches[0]
                    source_ids.add(resolved_sid)
            group = sources.get(resolved_sid, {}).get("name", target.origin or sid or "")
            project = project_fields(dict(item, context_source_id=resolved_sid), projects)
            if not selected_match(project, filters.get('project_id')):
                continue
            if filters.get("source_id") and filters["source_id"] != resolved_sid:
                continue
            if filters.get("platform") and filters["platform"] != item.get("platform"):
                continue
            if filters.get("review") and filters["review"] != review["status"]:
                continue
            if filters.get("run_id") and filters["run_id"] not in runs:
                continue
            text = " ".join(str(item.get(k) or "") for k in ("title", "caption", "raw_text", "hashtags", "canonical_url")) + " " + group
            if filters.get("keyword") and normalize(filters["keyword"]) not in normalize(text):
                continue
            dates = [o.get("collected_at") or o.get("discovered_at") for o in obs]
            dates = [d for d in dates if d] + ([item["collected_at"]] if item.get("collected_at") else [])
            if any(bounds):
                values = dates if basis == "collected_at" else [max(dates, default=None)] if basis == "latest_collected_at" else [item.get("published_at")]
                if basis == "published_at" and item.get("publication_precision") != "INSTANT":
                    continue
                def inside(value):
                    try:
                        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        return stamp.tzinfo is not None and (not bounds[0] or stamp >= bounds[0]) and (not bounds[1] or stamp < bounds[1])
                    except (ValueError, AttributeError):
                        return False
                if not any(inside(value) for value in values):
                    continue
            rows.append(dict(record_id=record_id, url=item.get("canonical_url") or item.get("source_url"),
                             platform=item.get("platform"), group=group, group_url=sources.get(resolved_sid, {}).get("url"),
                             source_id=sid, title=item.get("title"), text=item.get("raw_text") or item.get("caption") or "",
                             published_at=item.get("published_at"), publication_precision=item.get("publication_precision"),
                             collected_at=max(dates, default=None), extraction_status=item.get("extraction_status"),
                             missing_data_reasons=item.get("missing_data_reasons", []), observation_count=len(obs),
                             run_ids=runs, review=review, **project))
        rows.sort(key=lambda r: r["collected_at"] or "", reverse=True)
        output.update(total=len(rows), rows=rows[(page - 1)*20:page*20] if paginate else rows,
                      sources=[dict(source_id=sid, name=sources.get(sid, {}).get("name", sid)) for sid in sorted(source_ids)],
                      runs=sorted(run_ids, reverse=True))
        return output
    finally:
        db.close()
