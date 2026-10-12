"""
Runnable self-check for the shared record schema.

Builds one minimal, fully-valid record per supported platform and asserts that
build_quality scores it 100 with nothing missing, then asserts that each
platform-specific identity check actually rejects a wrong value. This is the
smallest thing that fails if a platform is added to one validator but forgotten
in another (the failure mode the per-platform branches in pipeline_utils are
most prone to).

It also covers the shared run-configuration layer every scraper now reads its
constants through (env overrides, discovery-mode selection, keyword matching,
the append-and-resort output file, and the fa/en analysis routing), since a
silent regression there changes what every scraper collects.

Run: python -m tests.contract.legacy_schema
"""

import os
import json
import tempfile

import src.config.env as config_env
import src.discovery.keyword_matching as keyword_matching
import src.domain.language as language
import src.storage.record_file as record_file
from src.analysis import legacy_text as analysis
from src.domain.legacy_schema import build_quality

NO_ASSET = [{
    "mentioned_text": None, "canonical_name": None, "Symbol": None,
    "asset_class": None, "asset_id": None, "confidence": None,
}]

PUBLISHED = "2026-08-20 10:00:00 UTC"
COLLECTED = "2026-08-20 12:00:00 UTC"

# platform -> (author_id, source_id, url, content_type, media)
PLATFORMS = {
    "X": ("Reuters", "1799999999999999999",
          "https://x.com/Reuters/status/1799999999999999999", "tweet",
          {"has_media": False, "media_type": None, "media_url": None}),
    "YouTube": ("UCabcdefghijklmnopqrstuv", "dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video",
                {"has_media": True, "media_type": "video",
                 "media_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
    "Telegram": ("reuters", "4242", "https://t.me/reuters/4242", "message",
                 {"has_media": False, "media_type": None, "media_url": None}),
    "Reddit": ("worldnews", "1abc2de",
               "https://www.reddit.com/r/worldnews/comments/1abc2de/some_slug/", "post",
               {"has_media": True, "media_type": "link",
                "media_url": "https://example.com/article"}),
    "TikTok": ("reuters", "7300000000000000001",
               "https://www.tiktok.com/@reuters/video/7300000000000000001", "video",
               {"has_media": True, "media_type": "video",
                "media_url": "https://www.tiktok.com/@reuters/video/7300000000000000001"}),
    "TruthSocial": ("realDonaldTrump", "109999999999999999",
                    "https://truthsocial.com/@realDonaldTrump/posts/109999999999999999", "post",
                    {"has_media": False, "media_type": None, "media_url": None}),
}


def make_record(platform, author_id, source_id, url, content_type, media):
    record_id = f"{platform}_{author_id}_{source_id}"
    return {
        "record_id": record_id,
        "Source": {
            "platform": platform,
            "Source_type": "Social_media",
            "Source_name": "Example Source",
            "Source_id": source_id,
            "url": url,
            "author_name": "Example Source",
            "author_id": author_id,
        },
        "Content": {
            "Content_type": content_type,
            "title": "Example headline",
            "raw_text": "Oil prices moved on the latest supply report.",
            "Clean_text": "",
            "language": "en",
        },
        "time_stamps": {
            "published_at": PUBLISHED,
            "collected_at": COLLECTED,
            "updated_at": None,
        },
        "asset_mention": NO_ASSET,
        "sentiment": {"label": None, "confidence": None},
        "Engagement": {"Views": 10, "likes": 2, "Comments": 1, "shares": 0},
        "media": media,
        "deduplication": {
            "content_hash": "0" * 32,
            "is_duplicate": False,
            "duplicate_group_id": record_id,
            "original_record_id": None,
        },
    }


def check_config_helpers():
    """The .env-driven config layer: precedence, parsing, and bad-value fallback."""
    os.environ["SELFCHECK_WINDOW"] = "90"
    os.environ["YT_SELFCHECK_WINDOW"] = "1440"
    assert config_env.env_int("SELFCHECK_WINDOW", 30) == 90
    assert config_env.env_int("SELFCHECK_WINDOW", 30, prefix="YT") == 1440
    assert config_env.env_int("SELFCHECK_WINDOW", 30, prefix="TT") == 90, "prefix must fall back to the bare name"
    assert config_env.env_int("SELFCHECK_ABSENT", 30) == 30

    os.environ["SELFCHECK_WINDOW"] = "not-a-number"
    assert config_env.env_int("SELFCHECK_WINDOW", 30) == 30, "a malformed value must fall back, not crash a cron run"

    os.environ["SELFCHECK_LANGS"] = "EN, fa "
    assert config_env.env_set("SELFCHECK_LANGS", {"en"}) == {"en", "fa"}
    os.environ["SELFCHECK_DELAY"] = "3,6"
    assert config_env.env_range("SELFCHECK_DELAY", (1.0, 2.0)) == (3.0, 6.0)
    os.environ["SELFCHECK_DELAY"] = "6,3"
    assert config_env.env_range("SELFCHECK_DELAY", (1.0, 2.0)) == (1.0, 2.0), "min > max must be rejected"
    os.environ["SELFCHECK_FLAG"] = "off"
    assert config_env.env_bool("SELFCHECK_FLAG", True) is False

    # Discovery mode must be settable with no terminal input at all.
    os.environ["SCRAPE_MODE"] = "accounts"
    assert config_env.get_scrape_mode() == "accounts"
    os.environ["TT_SCRAPE_MODE"] = "keyword"
    assert config_env.get_scrape_mode(prefix="TT") == "keyword"
    del os.environ["SCRAPE_MODE"], os.environ["TT_SCRAPE_MODE"]

    assert keyword_matching.keyword_matches("Prices of crude oil rose", "oil prices")
    assert not keyword_matching.keyword_matches("Gold hit a record", "oil prices")
    assert not keyword_matching.keyword_matches("anything", ""), "an empty keyword must not match everything"
    print("config helpers: ok")


def check_record_file():
    """RecordFile must append to prior runs and keep the file chronological."""
    older = make_record("X", *PLATFORMS["X"])
    newer = make_record("X", *PLATFORMS["X"])
    newer["record_id"] = newer["record_id"] + "2"
    older["time_stamps"]["published_at"] = "2026-08-20 10:00:00 UTC"
    newer["time_stamps"]["published_at"] = "2026-08-21 10:00:00 UTC"
    stamp = record_file.parse_record_timestamp

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.json")
        first = record_file.RecordFile(path)
        first.add(newer, stamp(newer["time_stamps"]["published_at"]))
        assert first.save() is True

        # A second run appends without losing or reordering the first run's data.
        second = record_file.RecordFile(path)
        assert second.has(newer["record_id"]), "existing records must be seen by the next run"
        second.add(older, stamp(older["time_stamps"]["published_at"]))
        assert second.save() is True

        stored = json.load(open(path, encoding="utf-8"))
        assert [r["record_id"] for r in stored] == [older["record_id"], newer["record_id"]], stored
        assert record_file.RecordFile(path).save() is False, "an empty run must not rewrite the file"
    print("record file: ok")


def check_fa_analysis_routing():
    """A non-English record is analysed in its OWN language -- never translated.

    Nothing in the pipeline translates any more, so this checks that a Persian
    record is scored by the multilingual sentiment model on its original text,
    that an English one still goes to FinBERT, and that a Persian record's
    asset mentions actually come back. The last part is the bug this replaced:
    the English-only NLI model used to contradict real mentions in Persian
    text and delete them.
    """
    original_sentiment = analysis.analyze_sentiment
    original_assets = analysis.extract_asset_mentions
    seen = {}
    try:
        def fake_sentiment(text, lang="en"):
            seen["sentiment_input"] = text
            seen["sentiment_lang"] = lang
            return {"label": "positive", "confidence": 0.9}

        def fake_assets(text, context_terms=None, lang="en", **kwargs):
            seen["asset_input"] = text
            seen["asset_lang"] = lang
            return []

        analysis.analyze_sentiment = fake_sentiment
        analysis.extract_asset_mentions = fake_assets

        sentiment, _ = analysis.analyze_text("قیمت نفت بالا رفت", "fa")
        assert seen["sentiment_input"] == "قیمت نفت بالا رفت", seen
        assert seen["asset_input"] == "قیمت نفت بالا رفت", seen
        assert seen["sentiment_lang"] == "fa" and seen["asset_lang"] == "fa", seen
        assert sentiment["label"] == "positive"

        seen.clear()
        analysis.analyze_text("Oil prices rose", "en")
        assert seen["asset_input"] == "Oil prices rose", seen
        assert seen["sentiment_lang"] == "en", seen
    finally:
        analysis.analyze_sentiment = original_sentiment
        analysis.extract_asset_mentions = original_assets

    # Model routing: English -> FinBERT, anything else -> the multilingual model.
    assert analysis._sentiment_model_for("en") == analysis._SENTIMENT_MODEL_NAME
    assert analysis._sentiment_model_for("fa") == analysis._MULTILINGUAL_SENTIMENT_MODEL_NAME

    # The reported bug: a Persian post naming USDT must come back WITH assets.
    # No model is stubbed here -- the NLI model is skipped for non-Latin text,
    # so this runs on alias matching alone and needs no download.
    fa_assets = analysis.extract_asset_mentions(
        "قیمت تتر امروز بالا رفت و USDT گران شد. طلا هم رشد کرد.", lang="fa")
    symbols = {a["Symbol"] for a in fa_assets}
    assert "USDT" in symbols, fa_assets
    assert "XAU" in symbols, fa_assets
    # Unicode word boundaries: "طلایی" (golden, the colour) is not "طلا" (gold).
    assert not any(a["Symbol"] == "XAU" for a in
                   analysis.extract_asset_mentions("رنگ طلایی زیباست", lang="fa"))

    # A non-Latin record must not normalize to an empty dedup key -- that made
    # every Persian post an exact duplicate of every other one.
    from src.filtering import dedup as dedup_utils
    assert dedup_utils._normalize_text("قیمت نفت بالا رفت").strip(), "Persian text normalized away"
    assert (dedup_utils._normalize_text("قیمت نفت") != dedup_utils._normalize_text("قیمت طلا"))

    # The language gate drops a post only when the detector is CONFIDENT it is
    # some other language; an unsure verdict on a short post is kept.
    assert language.language_allowed("en", 0.99, {"en", "fa"}, 0.70)
    assert language.language_allowed("de", 0.40, {"en", "fa"}, 0.70), "unsure verdict must be kept"
    assert not language.language_allowed("de", 0.95, {"en", "fa"}, 0.70)

    print("fa/en analysis routing: ok")


def main():
    original_model_name = analysis._ASSET_NLI_MODEL_NAME
    try:
        analysis._ASSET_NLI_MODEL_NAME = "none"
        assert analysis._load_asset_nli_model() is None
    finally:
        analysis._ASSET_NLI_MODEL_NAME = original_model_name
    for platform, fields in PLATFORMS.items():
        record = make_record(platform, *fields)
        quality = build_quality(record)
        assert quality["quality_score"] == 100, f"{platform}: {quality}"
        assert quality["is_complete"], f"{platform}: {quality['missing_fields']}"

        # A URL pointing at another account must fail the identity checks, not
        # be waved through by a generic http(s) fallback.
        broken = make_record(platform, *fields)
        broken["Source"]["url"] = "https://example.com/not-the-post"
        assert "valid_url" in build_quality(broken)["missing_fields"], f"{platform}: URL check is not platform-aware"

        # record_id must stay derived from platform + author + native id.
        broken = make_record(platform, *fields)
        broken["record_id"] = "wrong_id"
        assert "consistent_record_id" in build_quality(broken)["missing_fields"], f"{platform}: record_id check missing"

        # An unknown Content_type must be rejected per platform.
        broken = make_record(platform, *fields)
        broken["Content"]["Content_type"] = "something_else"
        assert "valid_content_type" in build_quality(broken)["missing_fields"], f"{platform}: content type check missing"

        print(f"{platform}: ok")

    unknown = make_record("Facebook", "someone", "123", "https://example.com/p/123", "post",
                          {"has_media": False, "media_type": None, "media_url": None})
    assert "valid_platform" in build_quality(unknown)["missing_fields"], "unregistered platform must fail"
    print("unregistered platform rejected: ok")

    check_config_helpers()
    check_record_file()
    check_fa_analysis_routing()


if __name__ == "__main__":
    main()
