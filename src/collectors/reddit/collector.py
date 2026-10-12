"""
Reddit submission scraper.

Searches a list of trusted subreddits for each configured keyword and writes
the matching submissions into the shared record schema used by the other
scrapers (dedup, language gate, asset mapping, quality scoring all come from
the shared modules).

Prerequisites:
  1. python -m pip install -r requirements.txt
  2. Get a client id/secret for the Data API (the classic REST API PRAW
     talks to -- NOT developers.reddit.com/Devvit, which is a separate
     platform for apps that run inside Reddit itself, not for external
     scripts reading data). Since Reddit's Responsible Builder Policy
     (Nov 2025), reddit.com/prefs/apps no longer issues keys instantly --
     request access via the form linked from Reddit's Data API wiki
     (search "Reddit Data API Wiki"), category "developer"/"researcher".
     Credentials from before Nov 2025 still work unchanged. Put them in
     .env (loaded automatically by pipeline_utils.py):
       REDDIT_CLIENT_ID=...
       REDDIT_CLIENT_SECRET=...
  3. reddit-keywords.txt with one search keyword per line.

The app is used read-only, so no Reddit account password is involved and no
write scope is ever requested. The unauthenticated reddit.com/*.json
endpoints (no credentials needed) were retired in 2026 -- this script never
used them, so that retirement doesn't affect it.
"""

import os
import json
import time
import bisect
import random
import datetime

from src.filtering import dedup as dedup_utils
from src.observability.logging import setup_logging
from src.resilience.retry import with_retry
from src.domain.language import detect_language, language_allowed
from src.config.paths import KEYWORDS_DIR, SOURCES_DIR
from src.domain.legacy_schema import build_quality
from src.analysis.legacy_text import analyze_text
from src.config.env import get_scrape_mode, env_int, env_float, env_set, env_range, env_str

logger = setup_logging("reddit-scraper", log_file="reddit-scraper.log")

# Every constant below is overridable from .env (see .env.example): the bare
# name applies to all scrapers, an "RD_"-prefixed name applies to this one only.
MAX_RESULTS_PER_KEYWORD = env_int("MAX_RESULTS_PER_KEYWORD", 50, prefix="RD")
MAX_PAST_MINUTES = env_int("MAX_PAST_MINUTES", 30 * 24 * 60, prefix="RD")  # default 30 days

# Account-only mode reads a subreddit's /new listing directly instead of
# searching it, so this is the "collect everything recent" cap rather than a
# relevance-ranked result count.
MAX_POSTS_PER_SUBREDDIT = env_int("MAX_POSTS_PER_SUBREDDIT", 100, prefix="RD")

SEARCH_DELAY_RANGE = env_range("SEARCH_DELAY_RANGE", (3.0, 6.0), prefix="RD")  # Jittered pause between keyword searches
LANGUAGE_MIN_CONFIDENCE = env_float("LANGUAGE_MIN_CONFIDENCE", 0.70, prefix="RD")
ALLOWED_LANGUAGES = env_set("ALLOWED_LANGUAGES", {"en", "fa"}, prefix="RD")

KEYWORDS_FILE = os.path.join(KEYWORDS_DIR, "reddit-keywords.txt")
SUBREDDITS_FILE = os.path.join(SOURCES_DIR, "reddit-subreddits.txt")
OUTPUT_DIR = "reddit-posts/"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S UTC"

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = env_str("REDDIT_USER_AGENT", "python:social-media-scraping:1.0 (read-only research)")

try:
    import praw
    import prawcore
except ImportError:
    logger.error("praw is not installed. Run: python -m pip install -r requirements.txt")
    exit(1)


def load_trusted_subreddits(filepath: str = SUBREDDITS_FILE) -> list:
    """Loads trusted subreddit names from a file or falls back to defaults."""
    default_subreddits = ["worldnews", "news", "business", "economics", "investing", "energy"]
    if not os.path.exists(filepath):
        logger.warning(f"'{filepath}' not found. Creating default file.")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(default_subreddits))
        return default_subreddits

    with open(filepath, "r", encoding="utf-8") as f:
        subreddits = [
            line.strip().lstrip("/").removeprefix("r/").strip("/")
            for line in f
            if line.strip() and not line.startswith("#")
        ]

    if not subreddits:
        logger.warning(f"No subreddits found in '{filepath}'. Using default trusted subreddits.")
        return default_subreddits

    return subreddits


def _format_timestamp(epoch) -> str:
    """Renders a Reddit epoch value in the shared schema's UTC string format."""
    if not epoch:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).strftime(TIMESTAMP_FMT)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _parse_published_at(value):
    """Parses a stored published_at string back into a datetime for sorting."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, TIMESTAMP_FMT).replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


def _insert_sorted(records_list: list, timestamps_list: list, record: dict, dt_val):
    """Inserts a record into the list maintaining chronological order via binary search."""
    sort_key = dt_val.timestamp() if dt_val else 0.0
    idx = bisect.bisect_right(timestamps_list, sort_key)
    records_list.insert(idx, record)
    timestamps_list.insert(idx, sort_key)


def _extract_media_info(submission) -> dict:
    """
    Maps a submission's attachment onto the shared media schema.

    Reddit posts are either self (text) posts, link posts, or posts carrying
    Reddit-hosted media; post_hint is Reddit's own classification of which.
    """
    if getattr(submission, "is_self", False):
        return {"has_media": False, "media_type": None, "media_url": None}

    hint = getattr(submission, "post_hint", None)
    media_type = {
        "image": "photo",
        "hosted:video": "video",
        "rich:video": "video",
        "link": "link",
    }.get(hint)

    if media_type is None:
        media_type = "video" if getattr(submission, "is_video", False) else "link"

    media_url = getattr(submission, "url", None)
    if not (isinstance(media_url, str) and media_url.startswith(("http://", "https://"))):
        return {"has_media": False, "media_type": None, "media_url": None}

    return {"has_media": True, "media_type": media_type, "media_url": media_url}


def _build_engagement(submission) -> dict:
    """
    Reddit reports a net score (upvotes minus downvotes), which can go
    negative; the schema's engagement counts must not, so it is clamped.
    """
    score = getattr(submission, "score", 0) or 0
    comments = getattr(submission, "num_comments", 0) or 0
    views = getattr(submission, "view_count", None) or 0
    return {
        "Views": max(0, int(views)),
        "likes": max(0, int(score)),
        "Comments": max(0, int(comments)),
        "shares": 0,
    }


@with_retry(max_attempts=3, base_delay=5.0, exceptions=(prawcore.exceptions.RequestException, prawcore.exceptions.ServerError))
def search_submissions(reddit, subreddits: list, keyword: str) -> list:
    """
    Searches every trusted subreddit at once.

    Reddit accepts a "sub1+sub2+..." multireddit path, so all trusted
    subreddits are covered by a single search call per keyword rather than
    one call per subreddit per keyword.
    """
    logger.info(f"Searching r/{'+'.join(subreddits)} for: {keyword}...")
    multireddit = reddit.subreddit("+".join(subreddits))
    return list(multireddit.search(keyword, sort="new", time_filter="month", limit=MAX_RESULTS_PER_KEYWORD))


@with_retry(max_attempts=3, base_delay=5.0, exceptions=(prawcore.exceptions.RequestException, prawcore.exceptions.ServerError))
def list_new_submissions(reddit, subreddit_name: str) -> list:
    """Lists one subreddit's newest submissions, unfiltered.

    /new is chronological, so the time-window cut in _merge_submissions is all
    the filtering account-only mode does.
    """
    logger.info(f"Listing r/{subreddit_name}/new...")
    return list(reddit.subreddit(subreddit_name).new(limit=MAX_POSTS_PER_SUBREDDIT))


def _build_record(submission, subreddit_name: str, raw_text: str, lang: str,
                  duplication_info: dict, collected_at: str, keyword: str) -> dict:
    """Assembles one submission into the shared cross-platform record schema."""
    permalink = f"https://www.reddit.com{getattr(submission, 'permalink', '')}"
    edited = getattr(submission, "edited", False)
    sentiment, asset_mention = analyze_text(
        raw_text,
        lang,
        asset_text=(str(getattr(submission, "title", "") or "") + "\n" + raw_text).strip(),
        context_terms=[keyword] if keyword else [],
    )
    record = {
        "record_id": f"Reddit_{subreddit_name}_{submission.id}",
        "Source": {
            "platform": "Reddit",
            "Source_type": "Social_media",
            "Source_name": f"r/{subreddit_name}",
            "Source_id": submission.id,
            "url": permalink,
            "author_name": f"r/{subreddit_name}",
            "author_id": subreddit_name
        },
        "Content": {
            "Content_type": "post",
            "title": getattr(submission, "title", "N/A") or "N/A",
            "raw_text": raw_text,
            "Clean_text": "",
            "language": lang
        },
        "time_stamps": {
            "published_at": _format_timestamp(getattr(submission, "created_utc", None)),
            "collected_at": collected_at,
            # Reddit reports an edit epoch (and literal False when never
            # edited), so this field carries a real value where one exists.
            "updated_at": _format_timestamp(edited) if edited else None
        },
        "asset_mention": asset_mention,
        "sentiment": sentiment,
        "Engagement": _build_engagement(submission),
        "media": _extract_media_info(submission),
        "deduplication": duplication_info
    }
    record["quality"] = build_quality(record, complete_raw_text=True, extraction_errors=[])
    return record


def _merge_submissions(submissions, master_file: str, keyword, lsh, hash_by_id, label: str):
    """Filters, dedups and merges a batch of submissions into one output file.

    Shared by both discovery modes so keyword mode and subreddit-only mode
    produce byte-identical records for the same submission -- only the batch
    of submissions handed in, and the file they land in, differ.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=MAX_PAST_MINUTES)

    existing_records = []
    existing_ids = set()
    existing_timestamps = []

    if os.path.exists(master_file):
        try:
            with open(master_file, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
                for rec in existing_records:
                    rec_id = rec.get("record_id")
                    if rec_id:
                        existing_ids.add(rec_id)
                    dt_obj = _parse_published_at(rec.get("time_stamps", {}).get("published_at"))
                    existing_timestamps.append(dt_obj.timestamp() if dt_obj else 0.0)
        except Exception as e:
            logger.error(f"Error loading {master_file}: {e}")
            existing_records, existing_ids, existing_timestamps = [], set(), []

    added_count = 0
    skipped_unsupported_lang = 0
    collected_at = datetime.datetime.now(datetime.timezone.utc).strftime(TIMESTAMP_FMT)

    for submission in submissions:
        published_dt = None
        created = getattr(submission, "created_utc", None)
        if created:
            published_dt = datetime.datetime.fromtimestamp(float(created), datetime.timezone.utc)
            if published_dt < cutoff:
                continue

        subreddit_name = str(getattr(submission, "subreddit", "") or "")
        if not subreddit_name:
            continue

        record_id = f"Reddit_{subreddit_name}_{submission.id}"
        if record_id in existing_ids:
            continue

        # Link posts carry no body, so the title is the only text they have --
        # that is a complete post, not a truncated extraction.
        body = (getattr(submission, "selftext", "") or "").strip()
        title = (getattr(submission, "title", "") or "").strip()
        raw_text = (f"{title} {body}" if body else title).replace("\n", " ").strip()
        if not raw_text:
            continue

        lang, confidence = detect_language(raw_text)
        if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
            skipped_unsupported_lang += 1
            continue

        duplication_info = dedup_utils.check_and_register(record_id, raw_text, lsh, hash_by_id)
        if duplication_info.get("is_duplicate"):
            continue

        record = _build_record(submission, subreddit_name, raw_text, lang,
                               duplication_info, collected_at, keyword)

        _insert_sorted(existing_records, existing_timestamps, record, published_dt)
        existing_ids.add(record_id)
        added_count += 1

    if skipped_unsupported_lang:
        logger.info(f"Filtered out {skipped_unsupported_lang} unsupported-language submission(s) for '{label}'.")

    if added_count:
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(existing_records, f, indent=4, ensure_ascii=False)
        logger.info(f"Appended {added_count} new sorted submissions to {master_file} (Total: {len(existing_records)}).")
    else:
        logger.info(f"No new unique submissions to append for '{label}'.")

    return master_file


def search_and_scrape_reddit(reddit, keyword: str, subreddits: list, lsh, hash_by_id, output_dir: str = OUTPUT_DIR):
    """Keyword mode: one search across the trusted subreddits into that keyword's file."""
    os.makedirs(output_dir, exist_ok=True)
    safe_keyword = keyword.replace(" ", "_").lower()
    master_file = os.path.join(output_dir, f"reddit_{safe_keyword}.json")

    try:
        submissions = search_submissions(reddit, subreddits, keyword)
    except prawcore.exceptions.ResponseException as e:
        logger.error(f"Reddit API rejected the search for '{keyword}': {e}. Check REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET.")
        return None
    except Exception as e:
        logger.error(f"Search failed for '{keyword}': {type(e).__name__}: {e}")
        return None

    logger.info(f"Found {len(submissions)} candidate submissions for '{keyword}'.")
    return _merge_submissions(submissions, master_file, keyword, lsh, hash_by_id, keyword)


def scrape_subreddit(reddit, subreddit_name: str, lsh, hash_by_id, output_dir: str = OUTPUT_DIR):
    """
    Account-only mode: every recent submission in one trusted subreddit, with
    no keyword filtering or candidate selection. The subreddit plays the author
    role in this schema, so this is the exact counterpart of the account-only
    mode the other scrapers use, and relevance is left to the asset stage.
    """
    os.makedirs(output_dir, exist_ok=True)
    safe_name = subreddit_name.replace(" ", "_").lower()
    master_file = os.path.join(output_dir, f"reddit_{safe_name}.json")

    try:
        submissions = list_new_submissions(reddit, subreddit_name)
    except prawcore.exceptions.ResponseException as e:
        logger.error(f"Reddit API rejected the listing for 'r/{subreddit_name}': {e}. Check REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET.")
        return None
    except Exception as e:
        logger.error(f"Listing failed for 'r/{subreddit_name}': {type(e).__name__}: {e}")
        return None

    logger.info(f"Found {len(submissions)} recent submission(s) in 'r/{subreddit_name}'.")
    return _merge_submissions(submissions, master_file, None, lsh, hash_by_id, f"r/{subreddit_name}")
