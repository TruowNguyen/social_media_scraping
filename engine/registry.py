"""Safe config loading and curator gates; no automatic enablement."""
from pathlib import Path
import os
import tempfile
import yaml
from src.acquisition.identity import identify, hashtag_query, source_references

SUPPORTED = {"FACEBOOK_GROUP": "facebook", "TIKTOK_SEARCH": "tiktok", "GOOGLE_SEARCH": "google", "TIKTOK_ACCOUNT": "tiktok", "YOUTUBE_CHANNEL": "youtube", "THREADS_SEARCH": "threads"}


def require_bool(value, field):
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")


def positive(value, field):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


class Registry:
    def __init__(self, directory, drafts=()):
        self.directory = Path(directory)
        self.documents = {}
        versions = {"sources.yaml": "source-registry-config-v1", "watchlists.yaml": "watchlist-config-v1", "keywords.yaml": "keyword-config-v1", "exclusions.yaml": "exclusion-config-v2", "acquisition.yaml": "acquisition-config-v1"}
        for filename, version in versions.items():
            path = self.directory / filename
            if filename == "acquisition.yaml" and not path.exists():
                continue
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("schema_version") != version:
                raise ValueError(f"Unsupported schema: {filename}")
            self.documents[filename] = document
        extra = self.documents.get("acquisition.yaml", {})
        configured_sources = self.documents["sources.yaml"]["sources"] + extra.get("sources", [])
        # If promotion was interrupted after the atomic YAML write, YAML is authoritative.
        configured_ids = {row["source_id"] for row in configured_sources}
        self.sources = self._index(configured_sources + [row for row in drafts if row["source_id"] not in configured_ids], "source_id")
        self.watchlists = self._index(self.documents["watchlists.yaml"]["watchlists"] + extra.get("watchlists", []), "watchlist_id")
        self.queries = self._index(self.documents["keywords.yaml"]["query_sets"], "query_set_id")
        self.exclusions = self._index(self.documents["exclusions.yaml"]["exclusion_sets"], "exclusion_set_id")
        from engine.threads_registry import ThreadsRegistry
        self.sources.update(ThreadsRegistry(self.directory).sources())
        self.validate()

    @staticmethod
    def _index(rows, key):
        result = {}
        if not isinstance(rows, list):
            raise ValueError("Expected a list")
        for row in rows:
            identifier = row.get(key) if isinstance(row, dict) else None
            if not isinstance(identifier, str) or not identifier.strip() or identifier in result:
                raise ValueError(f"Missing/duplicate {key}")
            result[identifier] = row
        return result

    def validate(self):
        for source in self.sources.values():
            if not isinstance(source.get("name"), str) or not source["name"].strip():
                raise ValueError("Source name must be a nonempty display label")
            if any(key in source for key in ("api_key", "password", "cookies", "cookie", "token", "session_token")):
                raise ValueError("Credentials must use environment/profile references")
            if SUPPORTED.get(source.get("source_type")) != source.get("platform"):
                raise ValueError("Unsupported platform/source type")
            for key in ("enabled", "access_verified"):
                require_bool(source.get(key), key)
            if source.get("requires_login") is not None:
                require_bool(source["requires_login"], "requires_login")
            if source.get("access_type") not in {"UNKNOWN", "PUBLIC", "AUTHORIZED"} or source.get("verification_status") not in {"PENDING_VERIFICATION", "VERIFIED", "REJECTED"}:
                raise ValueError("Invalid access/verification enum")
            if source["source_type"] in {"FACEBOOK_GROUP", "TIKTOK_ACCOUNT", "YOUTUBE_CHANNEL"}:
                target = identify(source["url"])
                reference = source.get("platform_group_ref") if source["platform"] == "facebook" else source.get("platform_source_ref")
                if not isinstance(reference, str) or target.origin != reference or target.source_type != source["source_type"]:
                    raise ValueError("Source URL/reference mismatch")
            if source["source_type"] == "GOOGLE_SEARCH" and (source.get("credential_ref") != "env:SERPAPI_API_KEY" or source.get("url") != "https://serpapi.com/search.json"):
                raise ValueError("Google requires the official endpoint and env credential reference")
            if "search_date_filter" in source and (source["source_type"] != "GOOGLE_SEARCH" or source["search_date_filter"] not in {"OFF", "WINDOW"}):
                raise ValueError("Invalid Google search_date_filter")
            if source.get("query_scope"):
                scope = source["query_scope"]
                if source["source_type"] != "TIKTOK_SEARCH" or scope.get("query_type") != "HASHTAG" or hashtag_query(scope.get("search_keyword", "")) != source.get("platform_source_ref"):
                    raise ValueError("Invalid approved hashtag query scope")
            for key in ("verified_source_refs", "verified_url_aliases"):
                refs = source.get(key, [])
                if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs) or len(refs) != len(set(refs)):
                    raise ValueError("Invalid verified alias list")
            for url in source.get("verified_url_aliases", []):
                target = identify(url)
                if target.platform != source["platform"] or target.kind != "SOURCE_CONTAINER" or target.source_type != source["source_type"]:
                    raise ValueError("Verified alias does not match source platform/type")
            if source["enabled"] and self.readiness(source, require_enabled=False):
                raise ValueError("Enabled source is not verified/ready")
        for query in self.queries.values():
            for key in ("discovery_terms", "hashtags"):
                if not isinstance(query.get(key), list) or any(not isinstance(x, str) or not x.strip() for x in query[key]):
                    raise ValueError("Invalid discovery query")
            for tag in query["hashtags"]:
                hashtag_query(tag)
        for watchlist in self.watchlists.values():
            require_bool(watchlist.get("enabled"), "watchlist enabled")
            for key, collection in (("source_ids", self.sources), ("query_set_ids", self.queries)):
                refs = watchlist.get(key)
                if not isinstance(refs, list) or len(refs) != len(set(refs)) or any(ref not in collection for ref in refs):
                    raise ValueError(f"Invalid {key} reference")
            exclusions = self.exclusions.get(watchlist.get("exclusion_set_id"))
            if not exclusions:
                raise ValueError("Unknown exclusion set")
            rules = self._index(exclusions["rules"], "rule_id")
            if exclusions.get("mode") != "EXCLUDE_CLEAR_INTENT" or exclusions.get("hard_drop_on_keyword") is not False:
                raise ValueError("Unsupported exclusion semantics")
            for rule_id in watchlist.get("prefilter_rule_ids", []):
                rule = rules.get(rule_id)
                if not rule or rule.get("enabled") is not True:
                    raise ValueError("Missing/disabled prefilter rule")
                if rule_id != "NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE":
                    raise ValueError("Unsupported prefilter rule")
            if "NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE" not in watchlist.get("prefilter_rule_ids", []):
                raise ValueError("Required exclusion rule missing")
            policy = rules["NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"].get("on_match", {})
            if policy.get("action") != "DROP" or any(policy.get(key) is not False for key in ("fetch_full_content", "fetch_comments", "download_media", "call_llm", "store_raw_content", "export_to_signals")):
                raise ValueError("Unsafe/unsupported exclusion retention policy")
            if policy.get("retain_rejection_metadata_only") is not True or set(policy.get("rejection_metadata_fields", [])) != {"platform_item_id", "source_id", "source_url", "crawl_run_id", "collected_at", "rule_id", "drop_reason"}:
                raise ValueError("Rejections must retain exactly the seven audit fields")
            if set(rules["NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"].get("excluded_intents", [])) != {"SALES_MARKETING", "RECRUITMENT", "REAL_ESTATE_LISTING", "BUY_SELL", "GOODS_EXCHANGE", "RENTAL", "LOAN_DEBT"}:
                raise ValueError("Unsupported exclusion intent set")
            retrieval = watchlist.get("retrieval", {})
            for key in ("lookback_minutes", "max_items_per_source"):
                positive(retrieval.get(key), key)
            if retrieval.get("include_comments") is not False:
                raise ValueError("Comments are outside acquisition v1")
            if retrieval.get("require_keyword_match") is not False:
                raise ValueError("Acquisition v1 watchlists use broad collection; downstream checks relevance")

    @staticmethod
    def readiness(source, require_enabled=True):
        if require_enabled and not source.get("enabled"):
            return "SOURCE_DISABLED"
        if source.get("verification_status") != "VERIFIED" or not source.get("access_verified"):
            return "SOURCE_UNVERIFIED"
        if source.get("access_type") != "PUBLIC":
            return "PUBLIC_ACCESS_REQUIRED"
        if type(source.get("requires_login")) is not bool:
            return "LOGIN_REQUIREMENT_UNKNOWN"
        return None

    def resolve_target(self, candidate, watchlist):
        expected = {"facebook": "FACEBOOK_GROUP", "tiktok": "TIKTOK_ACCOUNT", "youtube": "YOUTUBE_CHANNEL"}[candidate.platform]
        matches = []
        for source_id in watchlist["source_ids"]:
            source = self.sources[source_id]
            refs = source_references(source)
            if source["source_type"] == expected and candidate.origin_source_ref and candidate.origin_source_ref in refs:
                matches.append(source)
        return matches[0] if len(matches) == 1 else None

    def matches_entry(self, entry, source):
        expected = {"facebook": "FACEBOOK_GROUP", "tiktok": "TIKTOK_ACCOUNT", "youtube": "YOUTUBE_CHANNEL"}.get(entry["platform"])
        if entry.get("proposed_source_type") == "TIKTOK_SEARCH":
            expected = "TIKTOK_SEARCH"
            if source["source_type"] == "TIKTOK_SEARCH" and not source.get("query_scope"):
                return entry.get("origin_source_ref") in {hashtag_query(tag) for query in self.queries.values() for tag in query["hashtags"]}
        return source["source_type"] == expected and entry.get("origin_source_ref") in source_references(source) and entry.get("origin_source_ref") is not None

    def update(self, collection, identifier, changes):
        key = "source_id" if collection == "sources" else "watchlist_id"
        for filename, document in self.documents.items():
            for row in document.get(collection, []):
                if row[key] == identifier:
                    previous = row.copy()
                    row.update(changes)
                    try:
                        self.validate()
                        self._write(filename, document)
                    except Exception:
                        row.clear()
                        row.update(previous)
                        raise
                    return
        raise ValueError("Draft sources must be registered in YAML before verification")

    def _write(self, filename, document):
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".registry-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                yaml.safe_dump(document, stream, allow_unicode=True, sort_keys=False)
            os.replace(temporary, self.directory / filename)
        finally:
            Path(temporary).unlink(missing_ok=True)
