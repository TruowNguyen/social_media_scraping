"""
TikTok account scraper.

Walks a list of trusted TikTok accounts, and for each recent video extracts
the spoken content with the same two-tier strategy yt-scraper.py uses:
TikTok's own auto-generated captions first, falling back to local Whisper
transcription of the audio track only when no captions exist. Records are
written into the shared schema used by the other scrapers.

TikTok has no free search API, so -- like tel-scraper.py -- discovery is
account-driven rather than keyword-driven: every recent video from a trusted
account is collected and relevance is left to the asset-mapping stage.

Prerequisites:
  1. python -m pip install -r requirements.txt
  2. ffmpeg on PATH (needed by the Whisper fallback's audio postprocessing).
  3. tiktok-accounts.txt with one account username per line.
"""

import os
import re
import time
import random
import tempfile
import datetime

import yt_dlp

from src.filtering import dedup as dedup_utils
from src.observability.logging import setup_logging
from src.resilience.retry import with_retry
from src.resilience.rate_limit import RateLimiter
from src.domain.language import detect_language, language_allowed
from src.config.paths import KEYWORDS_DIR, SOURCES_DIR
from src.domain.legacy_schema import build_quality
from src.media.transcription import get_whisper_model, transcribe_audio
from src.analysis.legacy_text import analyze_text
from src.config.env import get_scrape_mode, env_int, env_float, env_set, env_range
from src.discovery.keyword_matching import keyword_matches
from src.storage.record_file import RecordFile

# Silence huggingface hub warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = setup_logging("tiktok-scraper", log_file="tiktok-scraper.log")

# Every constant below is overridable from .env (see .env.example): the bare
# name applies to all scrapers, a "TT_"-prefixed name applies to this one only.
MAX_VIDEOS_PER_ACCOUNT = env_int("MAX_VIDEOS_PER_ACCOUNT", 30, prefix="TT")
MAX_PAST_MINUTES = env_int("MAX_PAST_MINUTES", 30 * 24 * 60, prefix="TT")  # default 30 days
MAX_VIDEO_DURATION_SECONDS = env_int("MAX_VIDEO_DURATION_SECONDS", 1800, prefix="TT")  # cap on the Whisper fallback

FETCH_MIN_INTERVAL = env_float("FETCH_MIN_INTERVAL", 2.0, prefix="TT")             # Seconds between video calls, enforced globally
ACCOUNT_DELAY_RANGE = env_range("ACCOUNT_DELAY_RANGE", (5.0, 10.0), prefix="TT")   # Jittered pause between accounts

LANGUAGE_MIN_CONFIDENCE = env_float("LANGUAGE_MIN_CONFIDENCE", 0.70, prefix="TT")
ALLOWED_LANGUAGES = env_set("ALLOWED_LANGUAGES", {"en", "fa"}, prefix="TT")

KEYWORDS_FILE = os.path.join(KEYWORDS_DIR, "tiktok-keywords.txt")
ACCOUNTS_FILE = os.path.join(SOURCES_DIR, "tiktok-accounts.txt")
OUTPUT_DIR = "tiktok-videos/"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S UTC"

_fetch_rate_limiter = RateLimiter(FETCH_MIN_INTERVAL)

# Cue timing lines are the only reliable structural marker in a WebVTT file.
_VTT_TIMING_RE = re.compile(r"-->")
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def load_trusted_accounts(filepath: str = ACCOUNTS_FILE) -> list:
    """
    Loads trusted TikTok usernames from a file.

    Like tel-channels.txt and unlike the X/YouTube lists, this file has no
    auto-created defaults: news outlets' TikTok handles are not reliably
    guessable and impersonator accounts are common, so a wrong guess would
    silently scrape the wrong account instead of failing.
    """
    if not os.path.exists(filepath):
        logger.error(
            f"File '{filepath}' not found. Create it with one TikTok username "
            f"per line (e.g. 'reuters'), '#' for comments."
        )
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        accounts = [
            line.strip().lstrip("@")
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    seen = set()
    unique = []
    for account in accounts:
        key = account.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(account)
    return unique


def _format_timestamp(epoch) -> str:
    if not epoch:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).strftime(TIMESTAMP_FMT)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _vtt_to_text(vtt: str) -> str:
    """
    Flattens a WebVTT caption file into one line of plain text.

    Auto-generated captions repeat each line across consecutive cues as the
    caption box scrolls, so consecutive repeats are collapsed; without that
    the transcript comes out several times longer than what was said.
    """
    lines = []
    for line in vtt.splitlines():
        line = _VTT_TAG_RE.sub("", line).strip()
        if not line or _VTT_TIMING_RE.search(line):
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")) or line.isdigit():
            continue
        if not lines or lines[-1] != line:
            lines.append(line)
    return " ".join(lines).strip()


@with_retry(max_attempts=3, base_delay=5.0, exceptions=(Exception,))
def list_account_videos(username: str) -> list:
    """
    Lists an account's most recent video IDs without fetching each video.

    extract_flat keeps this to a single cheap request per account; the full
    per-video extraction only runs for videos not already stored.
    """
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': MAX_VIDEOS_PER_ACCOUNT,
        'socket_timeout': 20,
        'retries': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.tiktok.com/@{username}", download=False)

    entries = info.get('entries', []) or []
    return [entry.get('id') for entry in entries if entry.get('id')]


@with_retry(max_attempts=2, base_delay=4.0, exceptions=(Exception,))
def fetch_video(video_url: str) -> tuple:
    """
    Fetches one video's metadata and, in the same request, its captions.

    yt-dlp writes any available subtitle track to disk while it extracts the
    metadata, so tier 1 of the text strategy costs no extra round trip.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            # TikTok labels its auto-captions with codes like "eng-US", so both
            # spellings are requested. Anything else is left to Whisper, which
            # translates non-English audio rather than transcribing it verbatim.
            'subtitleslangs': ['en.*', 'eng.*'],
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
            'socket_timeout': 20,
            'retries': 3,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

        caption_text = None
        for filename in sorted(os.listdir(tmpdir)):
            if filename.endswith(".vtt"):
                with open(os.path.join(tmpdir, filename), "r", encoding="utf-8", errors="replace") as f:
                    caption_text = _vtt_to_text(f.read())
                if caption_text:
                    break

    return info, caption_text


def extract_video_text(video_url: str, info: dict, caption_text: str) -> tuple:
    """
    Returns (text, is_complete, extraction_errors) for one video.

    Tier 1 is TikTok's own captions, tier 2 is local Whisper transcription.
    If both fail the video's caption/description is kept instead so the post
    is not lost, but the record is flagged as an incomplete extraction --
    the spoken content genuinely was not captured.
    """
    if caption_text:
        return caption_text, True, []

    video_id = info.get('id') or ''
    logger.info(f"Captions unavailable for {video_id}. Falling back to audio Whisper transcription...")
    transcript = transcribe_audio(
        video_url,
        video_id,
        duration=info.get('duration') or 0,
        max_duration=MAX_VIDEO_DURATION_SECONDS,
        logger=logger,
    )
    if transcript:
        return transcript, True, []

    description = (info.get('description') or info.get('title') or '').strip()
    if description:
        return description, False, ["no captions and no transcript available; stored the video description instead"]

    return None, False, ["no captions, transcript, or description available"]


def _extract_media_info(video_url: str) -> dict:
    """
    TikTok's own media URLs are short-lived signed CDN links, so the post URL
    doubles as media_url (pipeline_utils validates that consistency).
    """
    return {"has_media": True, "media_type": "video", "media_url": video_url}


def _build_engagement(info: dict) -> dict:
    return {
        "Views": info.get('view_count') or 0,
        "likes": info.get('like_count') or 0,
        "Comments": info.get('comment_count') or 0,
        "shares": info.get('repost_count') or 0,
    }


def _build_record(info: dict, username: str, video_id: str, video_url: str, raw_text: str,
                  lang: str, duplication_info: dict, collected_at: str,
                  complete_raw_text: bool, extraction_errors: list,
                  context_terms=None) -> dict:
    """Assembles one video into the shared cross-platform record schema."""
    display_name = (info.get('uploader') or info.get('channel') or username).strip()
    sentiment, asset_mention = analyze_text(
        raw_text,
        lang,
        asset_text=((info.get('description') or '') + "\n" + raw_text).strip(),
        context_terms=context_terms or [],
    )
    record = {
        "record_id": f"TikTok_{username}_{video_id}",
        "Source": {
            "platform": "TikTok",
            "Source_type": "Social_media",
            "Source_name": display_name,
            "Source_id": video_id,
            "url": video_url,
            "author_name": display_name,
            "author_id": username
        },
        "Content": {
            "Content_type": "video",
            "title": "N/A",
            "raw_text": raw_text,
            "Clean_text": "",
            "language": lang
        },
        "time_stamps": {
            "published_at": _format_timestamp(info.get('timestamp')),
            "collected_at": collected_at,
            # TikTok exposes no edit/modification timestamp, so per the shared
            # schema rule this stays null rather than repeating collected_at.
            "updated_at": None
        },
        "asset_mention": asset_mention,
        "sentiment": sentiment,
        "Engagement": _build_engagement(info),
        "media": _extract_media_info(video_url),
        "deduplication": duplication_info
    }
    record["quality"] = build_quality(
        record,
        complete_raw_text=complete_raw_text,
        extraction_errors=extraction_errors,
    )
    return record


def scrape_account(username: str, lsh, hash_by_id, keywords=None, output_dir: str = OUTPUT_DIR):
    """Scrapes one account's recent videos into the right output file(s).

    Account-only mode (``keywords`` empty) keeps every video inside the time
    window in ``tiktok_<account>.json``. Keyword mode walks exactly the same
    trusted-account listings -- TikTok has no free search API, so the trusted
    accounts ARE the search space -- and files each video under the first
    keyword its description/transcript matches, in ``tiktok_<keyword>.json``.
    A video matching no keyword is dropped in that mode.
    """
    os.makedirs(output_dir, exist_ok=True)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=MAX_PAST_MINUTES)

    if keywords:
        buckets = {
            keyword: RecordFile(
                os.path.join(output_dir, f"tiktok_{keyword.replace(' ', '_').lower()}.json"), logger
            )
            for keyword in keywords
        }
    else:
        safe_account = username.replace(" ", "_").lower()
        buckets = {None: RecordFile(os.path.join(output_dir, f"tiktok_{safe_account}.json"), logger)}

    try:
        video_ids = list_account_videos(username)
    except Exception as e:
        logger.error(f"Could not list videos for '@{username}': {type(e).__name__}: {str(e).splitlines()[0]}")
        return None

    new_video_ids = [
        vid for vid in video_ids
        if not any(bucket.has(f"TikTok_{username}_{vid}") for bucket in buckets.values())
    ]
    if not new_video_ids:
        logger.info(f"All discovered videos for '@{username}' are already scraped.")
        return None

    logger.info(f"Found {len(new_video_ids)} new candidate video(s) for '@{username}'.")

    skipped_unsupported_lang = 0
    skipped_no_keyword = 0
    skipped_out_of_window = 0
    skipped_no_text = 0
    duplicates_kept = 0
    collected_at = datetime.datetime.now(datetime.timezone.utc).strftime(TIMESTAMP_FMT)

    for video_id in new_video_ids:
        _fetch_rate_limiter.wait()
        video_url = f"https://www.tiktok.com/@{username}/video/{video_id}"

        try:
            info, caption_text = fetch_video(video_url)
        except Exception as e:
            logger.warning(f"Failed fetching {video_url}: {str(e).splitlines()[0]}")
            continue

        published_dt = None
        timestamp = info.get('timestamp')
        if timestamp:
            published_dt = datetime.datetime.fromtimestamp(float(timestamp), datetime.timezone.utc)
            # NOT a break: an account's pinned videos are listed first and can
            # be years old, so the first out-of-window video is no proof the
            # rest are older. Breaking here ended the whole account after one
            # old pin and was why a 30-video listing produced a single record.
            if published_dt < cutoff:
                skipped_out_of_window += 1
                continue

        text, complete_raw_text, extraction_errors = extract_video_text(video_url, info, caption_text)
        raw_text = (text or "").replace("\n", " ").strip()
        if not raw_text:
            skipped_no_text += 1
            continue

        matched_keyword = None
        if keywords:
            haystack = " ".join(filter(None, [info.get('description'), info.get('title'), raw_text]))
            matched_keyword = next((kw for kw in keywords if keyword_matches(haystack, kw)), None)
            if matched_keyword is None:
                skipped_no_keyword += 1
                continue

        lang, confidence = detect_language(raw_text)
        if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
            skipped_unsupported_lang += 1
            continue

        record_id = f"TikTok_{username}_{video_id}"
        # A duplicate is TAGGED, not dropped: the account is a trusted source
        # and the run is meant to collect everything it posted in the window.
        # deduplication.is_duplicate stays on the record so a downstream stage
        # can still collapse cross-platform repeats of the same story.
        duplication_info = dedup_utils.check_and_register(record_id, raw_text, lsh, hash_by_id)
        if duplication_info.get("is_duplicate"):
            duplicates_kept += 1

        record = _build_record(info, username, video_id, video_url, raw_text, lang,
                               duplication_info, collected_at, complete_raw_text, extraction_errors,
                               context_terms=[matched_keyword] if matched_keyword else [])

        buckets[matched_keyword].add(record, published_dt)

    if skipped_unsupported_lang:
        logger.info(f"Filtered out {skipped_unsupported_lang} unsupported-language video(s) for '@{username}'.")
    if skipped_no_keyword:
        logger.info(f"Filtered out {skipped_no_keyword} video(s) matching no keyword for '@{username}'.")
    if skipped_out_of_window:
        logger.info(f"Skipped {skipped_out_of_window} video(s) older than {MAX_PAST_MINUTES} minute(s) for '@{username}'.")
    if skipped_no_text:
        logger.info(f"Skipped {skipped_no_text} video(s) with no caption, transcript or description for '@{username}'.")
    if duplicates_kept:
        logger.info(f"Kept {duplicates_kept} video(s) flagged as cross-source duplicates for '@{username}'.")

    written = [bucket.path for bucket in buckets.values() if bucket.save()]
    if not written:
        logger.info(f"No new unique videos to append for '@{username}'.")
    return written or None


def load_keywords(filepath: str = KEYWORDS_FILE) -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
