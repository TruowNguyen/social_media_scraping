"""Legacy legacy_schema behavior extracted without changing data policies."""

import datetime
from urllib.parse import urlparse, parse_qs
import re

_PLATFORM_CONTENT_TYPES = {
    "X": "tweet",
    "YouTube": "video",
    "Telegram": "message",
    "Reddit": "post",
    "TikTok": "video",
    "TruthSocial": "post",
}

_KNOWN_PLATFORMS = frozenset(_PLATFORM_CONTENT_TYPES)

_TITLED_PLATFORMS = frozenset({"YouTube", "Reddit"})

def _valid_source_id(platform: str, value) -> bool:
    value = str(value or "").strip()
    if platform == "X":
        return bool(re.fullmatch(r"\d+", value))
    if platform == "YouTube":
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", value))
    if platform == "Telegram":
        return bool(re.fullmatch(r"\d+", value))
    if platform == "Reddit":
        # Reddit submission IDs are base36, without the "t3_" type prefix.
        return bool(re.fullmatch(r"[a-z0-9]{4,13}", value))
    if platform == "TikTok":
        return bool(re.fullmatch(r"\d{6,25}", value))
    if platform == "TruthSocial":
        return bool(re.fullmatch(r"\d+", value))
    return bool(value and value.lower() not in {"n/a", "unknown", "none", "null"})

def _valid_author_id(platform: str, value) -> bool:
    value = str(value or "").strip().lstrip("@")
    if platform == "X":
        return bool(re.fullmatch(r"[A-Za-z0-9_]{1,15}", value))
    if platform == "YouTube":
        # Canonical YouTube channel IDs are UC + 22 URL-safe characters.
        return bool(re.fullmatch(r"UC[A-Za-z0-9_-]{22}", value))
    if platform == "Telegram":
        # Public Telegram usernames are 5-32 alphanumeric/underscore characters.
        return bool(re.fullmatch(r"[A-Za-z0-9_]{5,32}", value))
    if platform == "Reddit":
        # The subreddit is the trusted source, so it plays the author role
        # here the same way a channel does for Telegram/YouTube.
        return bool(re.fullmatch(r"[A-Za-z0-9_]{3,21}", value))
    if platform == "TikTok":
        # TikTok usernames allow dots as well as letters/digits/underscores.
        return bool(re.fullmatch(r"[A-Za-z0-9_.]{1,24}", value))
    if platform == "TruthSocial":
        return bool(re.fullmatch(r"[A-Za-z0-9_]{1,30}", value))
    return bool(value and value.lower() not in {"n/a", "unknown", "none", "null"})

def _valid_source_url(platform: str, url, author_id=None, source_id=None) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]

    if platform == "X":
        if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            return False
        m = re.fullmatch(r"/([A-Za-z0-9_]{1,15})/status/(\d+)/?", parsed.path)
        if not m:
            return False
        if author_id and m.group(1).casefold() != str(author_id).lstrip("@").casefold():
            return False
        if source_id and m.group(2) != str(source_id):
            return False
        return True

    if platform == "YouTube":
        if host in {"youtu.be", "www.youtu.be"}:
            found_id = parsed.path.strip("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            found_id = parse_qs(parsed.query).get("v", [None])[0]
            if not found_id and parsed.path.startswith(("/shorts/", "/live/")):
                parts = parsed.path.strip("/").split("/")
                found_id = parts[1] if len(parts) > 1 else None
        else:
            return False
        return bool(found_id and (not source_id or found_id == str(source_id)))

    if platform == "Reddit":
        if host not in {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}:
            return False
        m = re.match(r"/r/([A-Za-z0-9_]{3,21})/comments/([a-z0-9]{4,13})(?:/|$)", parsed.path)
        if not m:
            return False
        if author_id and m.group(1).casefold() != str(author_id).lstrip("@").casefold():
            return False
        if source_id and m.group(2) != str(source_id):
            return False
        return True

    if platform == "TikTok":
        if host not in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
            return False
        m = re.fullmatch(r"/@([A-Za-z0-9_.]{1,24})/video/(\d{6,25})/?", parsed.path)
        if not m:
            return False
        if author_id and m.group(1).casefold() != str(author_id).lstrip("@").casefold():
            return False
        if source_id and m.group(2) != str(source_id):
            return False
        return True

    if platform == "TruthSocial":
        if host not in {"truthsocial.com", "www.truthsocial.com"}:
            return False
        m = re.fullmatch(r"/@([A-Za-z0-9_]{1,30})/(?:posts/)?(\d+)/?", parsed.path)
        if not m:
            return False
        if author_id and m.group(1).casefold() != str(author_id).lstrip("@").casefold():
            return False
        if source_id and m.group(2) != str(source_id):
            return False
        return True

    if platform == "Telegram":
        if host not in {"t.me", "www.t.me"}:
            return False
        m = re.fullmatch(r"/([A-Za-z0-9_]{5,32})/(\d+)/?", parsed.path)
        if not m:
            return False
        if author_id and m.group(1).casefold() != str(author_id).lstrip("@").casefold():
            return False
        if source_id and m.group(2) != str(source_id):
            return False
        return True

    return parsed.scheme in {"http", "https"} and bool(host)

def _parse_quality_timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value == "N/A":
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
        except (ValueError, TypeError):
            pass
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, TypeError):
        return None

def _record_id_consistent(record: dict) -> bool:
    source = record.get("Source") or {}
    platform = source.get("platform")
    record_id = str(record.get("record_id") or "")
    author_id = str(source.get("author_id") or "").lstrip("@")
    source_id = str(source.get("Source_id") or "")
    if platform in _KNOWN_PLATFORMS:
        return record_id == f"{platform}_{author_id}_{source_id}"
    return bool(record_id)

def _engagement_checks(record: dict) -> list:
    engagement = record.get("Engagement")
    if not isinstance(engagement, dict):
        return [("valid_engagement", False)]
    checks = []
    for field in ("Views", "likes", "Comments", "shares"):
        value = engagement.get(field)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
        checks.append((f"valid_engagement_{field}", ok))
    return checks

def _media_checks(record: dict) -> list:
    media = record.get("media")
    source = record.get("Source") or {}
    if not isinstance(media, dict):
        return [("valid_media", False)]
    has_media = media.get("has_media")
    checks = [("valid_media_has_media", isinstance(has_media, bool))]
    if has_media is True:
        checks.append(("valid_media_type", bool(media.get("media_type"))))
        url = media.get("media_url")
        checks.append(("valid_media_url", isinstance(url, str) and url.startswith(("http://", "https://"))))
        if source.get("platform") == "YouTube":
            checks.append(("consistent_youtube_media_type", media.get("media_type") == "video"))
            checks.append(("consistent_youtube_media_url", media.get("media_url") == source.get("url")))
        if source.get("platform") == "Telegram":
            checks.append(("consistent_telegram_media_url", media.get("media_url") == source.get("url")))
        if source.get("platform") == "TikTok":
            checks.append(("consistent_tiktok_media_type", media.get("media_type") == "video"))
            checks.append(("consistent_tiktok_media_url", media.get("media_url") == source.get("url")))
    elif has_media is False:
        checks.append(("valid_media_type", media.get("media_type") is None))
        checks.append(("valid_media_url", media.get("media_url") is None))
    else:
        checks.extend([("valid_media_type", False), ("valid_media_url", False)])
    return checks

def _dedup_checks(record: dict) -> list:
    dedup = record.get("deduplication")
    if not isinstance(dedup, dict):
        return [("valid_deduplication", False)]
    content_hash = dedup.get("content_hash")
    is_duplicate = dedup.get("is_duplicate")
    group_id = dedup.get("duplicate_group_id")
    original = dedup.get("original_record_id")
    record_id = record.get("record_id")
    return [
        ("valid_content_hash", isinstance(content_hash, str) and bool(re.fullmatch(r"[0-9a-fA-F]{32}", content_hash))),
        ("valid_duplicate_flag", isinstance(is_duplicate, bool)),
        ("valid_duplicate_group_id", bool(group_id)),
        ("valid_original_record_id", (is_duplicate is True and bool(original)) or (is_duplicate is False and original is None)),
        ("consistent_duplicate_group", (is_duplicate is True and bool(group_id)) or (is_duplicate is False and group_id == record_id)),
    ]

def _asset_checks(record: dict) -> list:
    mentions = record.get("asset_mention")
    if not isinstance(mentions, list) or not mentions:
        return [("valid_asset_mention", False)]
    # Canonical null placeholder means "no asset identified" and is valid.
    if len(mentions) == 1 and isinstance(mentions[0], dict) and all(
        mentions[0].get(k) is None
        for k in ("mentioned_text", "canonical_name", "Symbol", "asset_class", "asset_id", "confidence")
    ):
        return [("valid_asset_mention", True)]

    checks = []
    for idx, item in enumerate(mentions):
        if not isinstance(item, dict):
            checks.append((f"valid_asset_mention_{idx}", False))
            continue
        resolved = bool(item.get("canonical_name") and item.get("Symbol") and item.get("asset_class") and item.get("asset_id"))
        confidence = item.get("confidence")
        # ``confidence is None`` is the documented degraded mode of
        # _load_asset_nli_model (model/deps unavailable), not a defect in this
        # record -- an environment condition must not mark every asset-bearing
        # record incomplete. A present value still has to be in range.
        confidence_ok = confidence is None or (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and 0.0 <= float(confidence) <= 1.0
        )
        # An unresolved cashtag is still a valid observed mention, but the
        # resolution/confidence checks expose that it is not a complete asset mapping.
        checks.append((f"asset_{idx}_observed", bool(item.get("mentioned_text") or resolved)))
        checks.append((f"asset_{idx}_resolved", resolved))
        checks.append((f"asset_{idx}_confidence", confidence_ok if resolved else confidence is None))
    return checks

def _sentiment_checks(record: dict) -> list:
    sentiment = record.get("sentiment")
    if not isinstance(sentiment, dict):
        return [("valid_sentiment", False)]
    label = sentiment.get("label")
    confidence = sentiment.get("confidence")
    # label=None/confidence=None is the documented degraded mode of
    # analyze_sentiment (model unavailable), the same rule already applied to
    # asset confidence -- an environment condition, not a defect in this record.
    if label is None and confidence is None:
        return [("valid_sentiment", True)]
    return [(
        "valid_sentiment",
        label in {"positive", "neutral", "negative"}
        and isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0.0 <= float(confidence) <= 1.0,
    )]

def _sentiment_category_score(record: dict, checks: list) -> float:
    """Mirrors _asset_category_score: the boolean check and the model's own
    confidence value have equal standing, and a null (model-unavailable)
    sentiment stays a perfect score in this dimension."""
    sentiment = record.get("sentiment") if isinstance(record.get("sentiment"), dict) else {}
    confidence = sentiment.get("confidence")
    values = [100.0 if passed else 0.0 for _, passed in checks]
    if sentiment.get("label") is not None and isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        values.append(max(0.0, min(1.0, float(confidence))) * 100.0)
    return sum(values) / len(values) if values else 100.0

def _category_score(checks: list) -> float:
    if not checks:
        return 100.0
    return 100.0 * sum(1 for _, passed in checks if passed) / len(checks)

def _extraction_category_score(checks: list, reliability=None) -> float:
    """Score extraction quality from boolean checks plus optional reliability.

    Reliability is folded into this dimension rather than appended as a
    dimension of its own, and a platform that does not report it counts as
    fully reliable. Both parts are needed for the score to mean the same thing
    everywhere: otherwise a platform that reports reliability is scored over a
    different number of values than one that does not, and two records with
    identical defects get different scores purely because of which scraper
    produced them.
    """
    values = [100.0 if passed else 0.0 for _, passed in checks]
    try:
        rel = 1.0 if reliability is None else max(0.0, min(1.0, float(reliability)))
    except (TypeError, ValueError):
        rel = 1.0
    values.append(rel * 100.0)
    return sum(values) / len(values) if values else 100.0

def _asset_category_score(record: dict, checks: list) -> float:
    """Score asset-field quality from structure plus model certainty.

    Boolean schema/resolution checks and model-generated confidence values have
    equal standing inside the asset dimension. A canonical all-null placeholder
    (no asset identified) remains a perfect asset-field state.
    """
    mentions = record.get("asset_mention")
    if (
        isinstance(mentions, list)
        and len(mentions) == 1
        and isinstance(mentions[0], dict)
        and all(mentions[0].get(k) is None for k in ("mentioned_text", "canonical_name", "Symbol", "asset_class", "asset_id", "confidence"))
    ):
        return 100.0

    values = [100.0 if passed else 0.0 for _, passed in checks]
    if isinstance(mentions, list):
        for item in mentions:
            if not isinstance(item, dict):
                continue
            resolved = bool(item.get("canonical_name") and item.get("Symbol") and item.get("asset_class") and item.get("asset_id"))
            confidence = item.get("confidence")
            if resolved and isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                values.append(max(0.0, min(1.0, float(confidence))) * 100.0)
    return sum(values) / len(values) if values else 0.0

def build_quality(
    record: dict,
    complete_raw_text: bool = True,
    extraction_errors=None,
    extraction_reliability=None,
) -> dict:
    """Evaluate record quality on a 0-100 scale without arbitrary field weights.

    Validation is grouped into independent quality dimensions (identity,
    content, timestamps, engagement/media, deduplication, and asset mapping).
    Every check inside a dimension has equal standing. The overall score is the
    harmonic mean of the dimension scores, which prevents one weak dimension
    from being hidden by many unrelated good fields. A perfect record is 100.

    ``updated_at=None`` is explicitly valid. It means no edit timestamp was
    available, which is different from missing required publication/collection
    timestamps.
    """
    extraction_errors = [str(e) for e in (extraction_errors or []) if str(e).strip()]
    source = record.get("Source") or {}
    content = record.get("Content") or {}
    stamps = record.get("time_stamps") or {}
    platform = source.get("platform")

    published = _parse_quality_timestamp(stamps.get("published_at"))
    collected = _parse_quality_timestamp(stamps.get("collected_at"))
    updated_raw = stamps.get("updated_at")
    updated = _parse_quality_timestamp(updated_raw) if updated_raw is not None else None
    updated_valid = updated_raw is None or (
        updated is not None
        and (published is None or updated >= published)
        and (collected is None or updated <= collected)
    )

    identity = [
        ("valid_platform", platform in _KNOWN_PLATFORMS),
        ("valid_source_type", source.get("Source_type") == "Social_media"),
        ("valid_source_id", _valid_source_id(platform, source.get("Source_id"))),
        ("valid_author_id", _valid_author_id(platform, source.get("author_id"))),
        ("valid_author_name", bool(str(source.get("author_name") or "").strip()) and str(source.get("author_name")).strip().lower() not in {"n/a", "unknown"}),
        ("valid_source_name", bool(str(source.get("Source_name") or "").strip()) and str(source.get("Source_name")).strip().lower() not in {"n/a", "unknown"}),
        ("consistent_source_author_name", source.get("Source_name") == source.get("author_name")),
        ("valid_url", _valid_source_url(platform, source.get("url"), source.get("author_id"), source.get("Source_id"))),
        ("consistent_record_id", _record_id_consistent(record)),
    ]

    expected_type = _PLATFORM_CONTENT_TYPES.get(platform)
    content_checks = [
        ("complete_raw_text", bool(complete_raw_text and isinstance(content.get("raw_text"), str) and content.get("raw_text").strip())),
        ("valid_content_type", bool(expected_type and content.get("Content_type") == expected_type)),
        ("valid_language", bool(content.get("language") and content.get("language") not in {"unknown", "N/A"})),
    ]
    if platform in _TITLED_PLATFORMS:
        content_checks.append(("valid_title", bool(str(content.get("title") or "").strip()) and content.get("title") != "N/A"))
    # No translated_text check: the pipeline does not translate, so a record
    # carries only its original text in its own language.

    timestamp_checks = [
        ("valid_published_at", published is not None),
        ("valid_collected_at", collected is not None),
        ("valid_timestamp_order", published is not None and collected is not None and published <= collected),
        ("valid_updated_at", updated_valid),
    ]

    asset_checks = _asset_checks(record)
    sentiment_checks = _sentiment_checks(record)
    extraction_checks = [
        ("extraction_has_text", isinstance(content.get("raw_text"), str) and bool(content.get("raw_text").strip())),
        ("extraction_complete", bool(complete_raw_text)),
        ("no_extraction_errors", not extraction_errors),
    ]
    categories = {
        "identity": identity,
        "content": content_checks,
        "timestamps": timestamp_checks,
        "extraction": extraction_checks,
        "engagement_media": _engagement_checks(record) + _media_checks(record),
        "deduplication": _dedup_checks(record),
        "assets": asset_checks,
        "sentiment": sentiment_checks,
    }

    scores = []
    for name, checks in categories.items():
        if name == "assets":
            scores.append(_asset_category_score(record, checks))
        elif name == "sentiment":
            scores.append(_sentiment_category_score(record, checks))
        elif name == "extraction":
            scores.append(_extraction_category_score(checks, extraction_reliability))
        else:
            scores.append(_category_score(checks))

    if any(score <= 0 for score in scores):
        quality_score = 0.0
    else:
        quality_score = len(scores) / sum(1.0 / score for score in scores)
    quality_score = round(quality_score, 2)
    if quality_score == 100.0:
        quality_score = 100

    all_checks = [check for checks in categories.values() for check in checks]
    missing_fields = [name for name, passed in all_checks if not passed]
    is_complete = not missing_fields and not extraction_errors

    return {
        "is_complete": is_complete,
        "missing_fields": missing_fields,
        "extraction_errors": extraction_errors,
        "quality_score": quality_score,
    }
