"""Operator CLI for probes, verification, bounded acquisition and queue review."""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import uuid

from engine.acquisition import AcquisitionEngine, adapter_job
from engine.registry import Registry
from src.acquisition.identity import identify
from src.acquisition.models import Candidate, Deadline, DiscoveryRequest, FetchContext, Window, parse_utc, utcnow
from src.acquisition.prefilter import apply_prefilter
from src.browser.profiles import PROJECT_ROOT
from src.storage.acquisition import AcquisitionStore


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="SmartCity acquisition; no scheduler, media, ASR or LLM.")
    parser.add_argument("--config-dir", type=Path, default=PROJECT_ROOT / "config")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "sessions/acquisition/acquisition.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Validate configs offline; no platform requests.")
    sources = commands.add_parser("sources").add_subparsers(dest="action", required=True)
    sources.add_parser("list")
    probe = sources.add_parser("probe")
    probe.add_argument("source_id")
    probe.add_argument("--mode", choices=("KEYWORD_SEARCH", "HASHTAG_SEARCH"), default="KEYWORD_SEARCH")
    probe.add_argument("--query", default="VinCons")
    probe.add_argument("--item-url", help="Known YouTube item for explicit channel verification.")
    verify = sources.add_parser("verify", help="Probe, record public confirmation and login requirement; remains disabled.")
    verify.add_argument("source_id")
    verify.add_argument("--public", action="store_true", required=True)
    verify.add_argument("--requires-login", choices=("true", "false"), required=True)
    verify.add_argument("--item-url")
    for action in ("enable", "disable"):
        sources.add_parser(action).add_argument("source_id")
    promote = sources.add_parser("register-draft", help="Move an approved draft into editable YAML; remains disabled.")
    promote.add_argument("source_id")
    watchlists = commands.add_parser("watchlists").add_subparsers(dest="action", required=True)
    watchlists.add_parser("list")
    for action in ("enable", "disable"):
        watchlists.add_parser(action).add_argument("watchlist_id")
    membership = watchlists.add_parser("add-source")
    membership.add_argument("watchlist_id")
    membership.add_argument("source_id")
    run = commands.add_parser("run")
    run.add_argument("--watchlist", default="vincons_acquisition_v1")
    run.add_argument("--source-id", action="append")
    run.add_argument("--max-candidates", type=int)
    run.add_argument("--start")
    run.add_argument("--end")
    run.add_argument("--source-timeout", type=int, default=120)
    run.add_argument("--run-timeout", type=int, default=1200)
    discoveries = commands.add_parser("discoveries").add_subparsers(dest="action", required=True)
    listing = discoveries.add_parser("list")
    listing.add_argument("--status", choices=("PENDING", "APPROVED", "REJECTED"))
    listing.add_argument("--platform", choices=("facebook", "tiktok", "youtube"))
    listing.add_argument("--run-id")
    for action in ("approve", "reject", "reopen"):
        review = discoveries.add_parser(action)
        review.add_argument("discovery_id")
        review.add_argument("--reviewer", required=True)
        review.add_argument("--note", required=True)
        if action == "approve":
            review.add_argument("--source-id", required=True)
            review.add_argument("--create-source", action="store_true")
            review.add_argument("--origin-source-ref", help="Explicit manually resolved channel/group reference, with provenance in review note.")
    process = discoveries.add_parser("process")
    process.add_argument("discovery_id")
    process.add_argument("--watchlist", default="vincons_acquisition_v1")
    process.add_argument("--start", required=True)
    process.add_argument("--end", required=True)
    export = commands.add_parser("export", help="Acquisition JSON with all observations; no Excel/enrichment claims.")
    export.add_argument("--output", type=Path, required=True)
    return parser


def explicit_window(args):
    if bool(args.start) != bool(args.end):
        raise ValueError("Provide both --start and --end")
    return Window(parse_utc(args.start), parse_utc(args.end)) if args.start else None


def probe_source(source, store, mode="KEYWORD_SEARCH", query="VinCons", item_url=None):
    deadline = Deadline()
    if source.get("query_scope"):
        mode, query = "HASHTAG_SEARCH", source["query_scope"]["search_keyword"]
    source = dict(source, probe_query=query, probe_query_type="HASHTAG" if mode == "HASHTAG_SEARCH" else "KEYWORD")
    with adapter_job(source, deadline, store) as adapter:
        if source["platform"] == "google":
            # A real one-page API probe, counted in the durable monthly ledger.
            from src.acquisition.google import google_query
            now = datetime.now(timezone.utc)
            request = DiscoveryRequest(source, "probe_"+uuid.uuid4().hex, Window(now-timedelta(minutes=180), now), deadline, "SOCIAL_LINK_DISCOVERY", max_candidates=1, query_id="probe_google", query_type="KEYWORD", search_keyword=query, effective_query=google_query("facebook", query))
            batch = adapter.discover(request)
            return dict(status="ACCESSIBLE" if batch.status in {"SUCCESS", "NO_NEW_DATA"} else batch.status, error_code=batch.error_code, checked_at=utcnow(), candidates_observed=len(batch.candidates), api_attempts=batch.attempts)
        if source["platform"] == "youtube":
            if not item_url:
                raise ValueError("YouTube verification requires --item-url")
            target = identify(item_url)
            if target.platform != "youtube" or target.kind != "CONTENT_ITEM":
                raise ValueError("Expected a YouTube video URL")
            now = datetime.now(timezone.utc)
            candidate = Candidate("youtube", target.url, target.url, source["source_id"], "probe_"+uuid.uuid4().hex, "GOOGLE_SERPAPI", platform_item_id=target.item_id, prefilter_decision="REVIEW")
            adapter.fetch_item(candidate, FetchContext(source, Window(now-timedelta(days=36500), now), deadline))
            return dict(status="ACCESSIBLE", checked_at=utcnow(), evidence="CHANNEL_MATCHED_ITEM_METADATA")
        if source["source_type"] == "TIKTOK_ACCOUNT":
            # Account sources are only for known target item fetch, not a search query gate.
            if not item_url:
                raise ValueError("TikTok account verification requires --item-url")
            target = identify(item_url)
            if target.platform != "tiktok" or target.kind != "CONTENT_ITEM":
                raise ValueError("Expected a TikTok video URL")
            now = datetime.now(timezone.utc)
            candidate = Candidate("tiktok", target.url, target.url, source["source_id"], "probe_"+uuid.uuid4().hex, "TIKTOK_KEYWORD_BROWSER", platform_item_id=target.item_id, prefilter_decision="REVIEW")
            adapter.fetch_item(candidate, FetchContext(source, Window(now-timedelta(days=36500), now), deadline))
            return dict(status="ACCESSIBLE", checked_at=utcnow(), evidence="CREATOR_MATCHED_ITEM_METADATA")
        first = asdict(adapter.probe_access(source))
        if source["source_type"] == "TIKTOK_SEARCH" and first["status"] == "ACCESSIBLE" and mode == "KEYWORD_SEARCH":
            # Verify both approved search capabilities separately.
            second_source = dict(source, probe_query_type="HASHTAG", probe_query="#VinCons")
            second = asdict(adapter.probe_access(second_source))
            return dict(first, hashtag_probe=second, status="ACCESSIBLE" if second["status"] == "ACCESSIBLE" else second["status"])
        return first


def draft_from_entry(entry, source_id):
    ref = entry.get("origin_source_ref")
    source_type = entry.get("proposed_source_type")
    if not ref or source_type not in {"FACEBOOK_GROUP", "TIKTOK_ACCOUNT", "TIKTOK_SEARCH", "YOUTUBE_CHANNEL"}:
        raise ValueError("Resolve a supported group/account/channel before creating a draft")
    urls = {"FACEBOOK_GROUP": f"https://www.facebook.com/groups/{ref}", "TIKTOK_ACCOUNT": f"https://www.tiktok.com/@{ref}", "TIKTOK_SEARCH": f"https://www.tiktok.com/tag/{ref}", "YOUTUBE_CHANNEL": f"https://www.youtube.com/{ref}" if ref.startswith("@") else f"https://www.youtube.com/channel/{ref}"}
    source = dict(source_id=source_id, platform=entry["platform"], source_type=source_type, name=ref, url=urls[source_type], enabled=False, access_type="UNKNOWN", access_verified=False, requires_login=None, verification_status="PENDING_VERIFICATION", submitted_on=utcnow()[:10], project=None, location=None)
    source["platform_group_ref" if source_type == "FACEBOOK_GROUP" else "platform_source_ref"] = ref
    if source_type == "TIKTOK_SEARCH":
        source["query_scope"] = dict(query_type="HASHTAG", search_keyword="#"+ref)
    return source


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    store = AcquisitionStore(args.db)
    try:
        registry = Registry(args.config_dir, store.draft_sources())
        if args.command == "validate":
            output(dict(status="VALID", sources=len(registry.sources), watchlists=len(registry.watchlists), live_verified=False))
        elif args.command == "sources":
            if args.action == "list":
                output([dict(source_id=s["source_id"], platform=s["platform"], name=s["name"], enabled=s["enabled"], verification_status=s["verification_status"], gate=registry.readiness(s)) for s in registry.sources.values()])
            elif args.action in {"probe", "verify"}:
                source = registry.sources[args.source_id]
                result = probe_source(source, store, getattr(args, "mode", "KEYWORD_SEARCH"), getattr(args, "query", "VinCons"), args.item_url)
                if args.action == "verify" and result["status"] == "ACCESSIBLE":
                    registry.update("sources", args.source_id, dict(access_type="PUBLIC", access_verified=True, access_verification_method="PROJECT_ADAPTER_PROBE_AND_OPERATOR_CONFIRMATION", access_verified_on=utcnow()[:10], verification_status="VERIFIED", requires_login=args.requires_login == "true"))
                    result["enabled"] = source["enabled"]
                output(result)
                return 0 if result["status"] == "ACCESSIBLE" else 2
            elif args.action == "register-draft":
                source = next((s for s in store.draft_sources() if s["source_id"] == args.source_id), None)
                if not source:
                    raise ValueError("Draft source not found")
                document = registry.documents["acquisition.yaml"]
                if not any(row["source_id"] == source["source_id"] for row in document["sources"]):
                    document["sources"].append(source)
                    registry._write("acquisition.yaml", document)
                with store.db:
                    store.db.execute("DELETE FROM registry_drafts WHERE source_id=?", (args.source_id,))
                output(dict(source_id=args.source_id, enabled=False, verification_status="PENDING_VERIFICATION"))
            else:
                registry.update("sources", args.source_id, dict(enabled=args.action == "enable"))
                output(dict(source_id=args.source_id, enabled=args.action == "enable"))
        elif args.command == "watchlists":
            if args.action == "list":
                output(list(registry.watchlists.values()))
            elif args.action == "add-source":
                if args.source_id not in registry.sources:
                    raise ValueError("Unknown source ID")
                source_ids = list(dict.fromkeys(registry.watchlists[args.watchlist_id]["source_ids"] + [args.source_id]))
                registry.update("watchlists", args.watchlist_id, dict(source_ids=source_ids))
                output(dict(watchlist_id=args.watchlist_id, source_ids=source_ids))
            else:
                registry.update("watchlists", args.watchlist_id, dict(enabled=args.action == "enable", status="ACTIVE" if args.action == "enable" else "DRAFT"))
                output(dict(watchlist_id=args.watchlist_id, enabled=args.action == "enable"))
        elif args.command == "run":
            report = AcquisitionEngine(registry, store).run(args.watchlist, explicit_window(args), args.source_id, args.max_candidates, args.source_timeout, args.run_timeout)
            output(report)
            return 0 if report["status"] == "SUCCESS" else 2
        elif args.command == "discoveries":
            if args.action == "list":
                entries = store.list_queue(args.status)
                output([e for e in entries if (not args.platform or e["platform"] == args.platform) and (not args.run_id or e["crawl_run_id"] == args.run_id)])
            elif args.action == "process":
                output(AcquisitionEngine(registry, store).process_discovery(args.discovery_id, args.watchlist, explicit_window(args)))
            else:
                status = {"approve": "APPROVED", "reject": "REJECTED", "reopen": "PENDING"}[args.action]
                source_id = getattr(args, "source_id", None)
                if status == "APPROVED":
                    entry = store.queue_entry(args.discovery_id)
                    if entry["status"] != "PENDING":
                        raise ValueError("Reopen before changing an existing decision")
                    if args.origin_source_ref:
                        if entry["origin_source_ref"] and entry["origin_source_ref"] != args.origin_source_ref:
                            raise ValueError("Existing origin reference cannot be overwritten")
                        entry["origin_source_ref"] = args.origin_source_ref
                        if entry["platform"] == "youtube":
                            entry["proposed_source_type"] = "YOUTUBE_CHANNEL"
                    source = registry.sources.get(source_id)
                    if not source and args.create_source:
                        source = draft_from_entry(entry, source_id)
                        store.save_draft(source)
                    if not source or not registry.matches_entry(entry, source):
                        raise ValueError("Approval source must match resolved platform/origin")
                    with store.db:
                        store.db.execute("UPDATE queue SET payload=? WHERE discovery_id=?", (json.dumps(entry, ensure_ascii=False), args.discovery_id))
                output(store.review(args.discovery_id, status, args.reviewer, args.note, source_id))
        elif args.command == "export":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            observations = [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM observations")]
            args.output.write_text(json.dumps(dict(schema_version="acquisition-export-v1", records=store.export_records(), observations=observations), ensure_ascii=False, indent=2), encoding="utf-8")
            output(dict(output=str(args.output), records=len(store.export_records()), observations=len(observations)))
    except (ValueError, KeyError) as error:
        # Validation errors contain field names/IDs, never provider payloads.
        output(dict(status="INVALID_CONFIG_OR_REQUEST", error=str(error)))
        return 2
    except Exception as error:
        from src.acquisition.models import AdapterError
        output(dict(status=error.status if isinstance(error, AdapterError) else "FAILED", error_code=error.code if isinstance(error, AdapterError) else "OPERATION_FAILED"))
        return 2
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
