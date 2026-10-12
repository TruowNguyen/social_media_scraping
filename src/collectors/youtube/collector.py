import os
import re
import time
import random
import json
import bisect
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from youtube_transcript_api import YouTubeTranscriptApi
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

# Silence huggingface hub warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = setup_logging("yt-scraper", log_file="yt-scraper.log")

# Every constant below is overridable from .env (see .env.example): the bare
# name applies to all scrapers, a "YT_"-prefixed name applies to this one only.
MAX_RESULTS_PER_KEYWORD = env_int("MAX_RESULTS_PER_KEYWORD", 30, prefix="YT")
MAX_PAST_MINUTES = env_int("MAX_PAST_MINUTES", 30 * 24 * 60, prefix="YT")  # default 30 days
MAX_VIDEO_DURATION_SECONDS = env_int("MAX_VIDEO_DURATION_SECONDS", 3600, prefix="YT")  # skips 24/7 live broadcasts

# Account-only mode lists a channel's uploads tab directly instead of
# searching, so this is the "collect everything recent" cap rather than a
# relevance-ranked result count.
MAX_VIDEOS_PER_CHANNEL = env_int("MAX_VIDEOS_PER_CHANNEL", 50, prefix="YT")

# Placeholder used when yt-dlp cannot resolve the canonical UC... channel ID.
# record_id and author_id must use the SAME value or _record_id_consistent
# fails on top of _valid_author_id, charging two identity checks for one
# missing field. author_id is a string field in the schema, so it must not
# be null either.
UNRESOLVED_CHANNEL_ID = "unknown"

FETCH_MAX_WORKERS = env_int("FETCH_MAX_WORKERS", 4, prefix="YT")               # Concurrent audio/metadata workers
FETCH_MIN_INTERVAL = env_float("FETCH_MIN_INTERVAL", 1.0, prefix="YT")         # Seconds between video calls enforced globally
SEARCH_DELAY_RANGE = env_range("SEARCH_DELAY_RANGE", (8.0, 14.0), prefix="YT")  # Pacing delay between keyword searches
SEARCH_MAX_RETRIES = env_int("SEARCH_MAX_RETRIES", 3, prefix="YT")

LANGUAGE_MIN_CONFIDENCE = env_float("LANGUAGE_MIN_CONFIDENCE", 0.70, prefix="YT")
ALLOWED_LANGUAGES = env_set("ALLOWED_LANGUAGES", {"en", "fa"}, prefix="YT")

_fetch_rate_limiter = RateLimiter(FETCH_MIN_INTERVAL)

def load_trusted_channels(filepath: str = os.path.join(SOURCES_DIR, "yt-channels.txt")) -> list:
    default_channels = ["Reuters", "Bloomberg", "CNBC", "BBC", "CNN", "Al Jazeera"]
    if not os.path.exists(filepath):
        logger.warning(f"'{filepath}' not found. Creating default file.")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(default_channels))
        return default_channels

    with open(filepath, "r", encoding="utf-8") as f:
        channels = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    return channels if channels else default_channels


def extract_video_id(video_url: str) -> str:
    if "v=" in video_url:
        return video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    elif "youtube.com/live/" in video_url:
        return video_url.split("youtube.com/live/")[1].split("?")[0]
    return video_url.strip()


@with_retry(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def fetch_video_metadata(video_url: str) -> dict:
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'socket_timeout': 15,
        'retries': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    raw_timestamp = info.get('timestamp')
    if raw_timestamp:
        dt = datetime.datetime.fromtimestamp(raw_timestamp, datetime.timezone.utc)
        upload_datetime = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        dt = None
        upload_datetime = info.get('upload_date', 'N/A')

    modified_timestamp = info.get('modified_timestamp')
    if modified_timestamp:
        try:
            modified_dt = datetime.datetime.fromtimestamp(modified_timestamp, datetime.timezone.utc)
            updated_at = modified_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError, OSError, OverflowError):
            updated_at = None
    else:
        updated_at = None

    # yt-dlp exposes both uploader_id and channel_id. For a stable author
    # identifier we want YouTube's canonical channel ID (normally UC...).
    channel_id = info.get('channel_id')
    if not channel_id:
        for channel_url in (info.get('channel_url'), info.get('uploader_url')):
            if not channel_url:
                continue
            match = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})", channel_url)
            if match:
                channel_id = match.group(1)
                break

    return {
        "title": info.get('title', 'N/A'),
        "channel": info.get('channel') or info.get('uploader') or 'N/A',
        "channel_id": channel_id,
        "channel_handle": info.get('uploader_id'),
        "upload_datetime": upload_datetime,
        "updated_at": updated_at,
        "created_dt": dt,
        "duration": info.get('duration') or 0,
        "is_live": info.get('is_live', False),
        "view_count": info.get('view_count', 0) or 0,
        "like_count": info.get('like_count', 0) or 0,
        "comment_count": info.get('comment_count', 0) or 0
    }


def search_youtube_videos(keyword: str, trusted_channels: list, max_results: int = 15) -> list:
    logger.info(f"Searching live feed for: {keyword}...")
    today = datetime.datetime.now(datetime.timezone.utc)
    past_date = today - datetime.timedelta(minutes=MAX_PAST_MINUTES)
    date_filter = f"after:{past_date.strftime('%Y-%m-%d')}"

    search_query = f"ytsearch30:{keyword} news {date_filter}"
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': True,
        'socket_timeout': 15,
        'retries': 3,
    }

    entries = []
    for attempt in range(1, SEARCH_MAX_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get('entries', []) or []
            break
        except Exception as e:
            wait_time = random.uniform(10.0, 20.0) * attempt
            if attempt < SEARCH_MAX_RETRIES:
                logger.warning(f"yt-dlp search failed for '{keyword}' ({e}). Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"yt-dlp search exhausted attempts for '{keyword}': {e}")
                entries = []
        finally:
            time.sleep(random.uniform(*SEARCH_DELAY_RANGE))

    trusted_lower = [c.lower() for c in trusted_channels]
    valid_entries = []
    for entry in entries:
        uploader = (entry.get('uploader') or entry.get('channel') or '').lower()
        title = (entry.get('title') or '').lower()
        if trusted_channels:
            if any(tc in uploader or tc in title for tc in trusted_lower):
                valid_entries.append(entry.get('id'))
        else:
            valid_entries.append(entry.get('id'))

    if not valid_entries:
        valid_entries = [entry.get('id') for entry in entries if entry.get('id')]

    logger.info(f"Found {len(valid_entries[:max_results])} candidate video entries for '{keyword}'.")
    return valid_entries[:max_results]


@with_retry(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def resolve_channel_id(channel_name: str) -> tuple:
    """
    Resolves a trusted channel's plain configured name to its canonical
    UC... channel ID via one cheap search hit, reusing fetch_video_metadata's
    existing channel_id extraction rather than duplicating it.

    Account-only mode needs a real channel ID to list a channel's uploads tab
    directly; yt-channels.txt only stores free-text display names (matched by
    substring in keyword mode), so this is the resolution step that bridges
    the two. ponytail: trusts the first search hit for that name, the same
    trust boundary keyword mode's substring match already relies on; upgrade
    path is letting yt-channels.txt carry an explicit channel ID/URL per line
    if a name ever resolves to the wrong channel.
    """
    ydl_opts = {
        'quiet': True, 'skip_download': True, 'no_warnings': True,
        'extract_flat': True, 'socket_timeout': 15, 'retries': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{channel_name} news", download=False)
    entries = info.get('entries', []) or []
    video_id = entries[0].get('id') if entries else None
    if not video_id:
        return None, None

    meta = fetch_video_metadata(f"https://www.youtube.com/watch?v={video_id}")
    return meta.get('channel_id'), meta.get('channel')


@with_retry(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def list_channel_uploads(channel_id: str, max_results: int = MAX_VIDEOS_PER_CHANNEL) -> list:
    """Lists a channel's most recent uploads directly (no keyword, no candidate ranking)."""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': max_results,
        'socket_timeout': 15,
        'retries': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/videos", download=False)
    entries = info.get('entries', []) or []
    return [entry.get('id') for entry in entries if entry.get('id')][:max_results]


def extract_video_text(video_url: str, duration: int = 0) -> str:
    video_id = extract_video_id(video_url)
    ytt_api = YouTubeTranscriptApi()

    # Tier 1: Instant Subtitle API
    try:
        transcript_list = ytt_api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB', 'en-CA'])
            transcript_data = transcript.fetch().to_raw_data()
        except Exception:
            translatable = next((t for t in transcript_list if t.is_translatable), None)
            if translatable:
                transcript_data = translatable.translate('en').fetch().to_raw_data()
            else:
                transcript_data = None

        if transcript_data:
            return " ".join([item['text'].replace('\n', ' ') for item in transcript_data])
    except Exception as e:
        logger.debug(f"Subtitle fetch failed for {video_id}: {str(e).splitlines()[0] if str(e) else type(e).__name__}")

    # Tier 2: Whisper Audio Fallback
    logger.info(f"Subtitles unavailable for {video_id}. Falling back to audio Whisper transcription...")
    return transcribe_audio(
        video_url,
        video_id,
        duration=duration,
        max_duration=MAX_VIDEO_DURATION_SECONDS,
        # Forcing the android client sidesteps YouTube's current
        # signature/PO-token checks that were causing blanket 403s on the
        # web client's adaptive audio streams.
        extra_opts={
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip'
            },
        },
        logger=logger,
    )


def _process_single_video(video_id: str) -> tuple:
    _fetch_rate_limiter.wait()
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        meta = fetch_video_metadata(video_url)
        if meta.get('is_live'):
            logger.info(f"Skipping {video_id}: Active live stream.")
            return video_id, video_url, None, None

        text = extract_video_text(video_url, duration=meta.get('duration', 0))
        return video_id, video_url, meta, text
    except Exception as e:
        logger.warning(f"Failed processing video {video_id}: {e}")
        return video_id, video_url, None, None


def _insert_sorted(records_list: list, timestamps_list: list, record: dict, dt_val: datetime.datetime):
    sort_key = dt_val.timestamp() if dt_val else 0.0
    idx = bisect.bisect_right(timestamps_list, sort_key)
    records_list.insert(idx, record)
    timestamps_list.insert(idx, sort_key)


def _load_existing_videos(master_file: str) -> tuple:
    existing_records, existing_ids, existing_timestamps = [], set(), []
    if os.path.exists(master_file):
        try:
            with open(master_file, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
                for rec in existing_records:
                    rec_id = rec.get("record_id")
                    if rec_id:
                        existing_ids.add(rec_id)
                    pub_str = rec.get("time_stamps", {}).get("published_at")
                    try:
                        dt_obj = datetime.datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S UTC")
                    except Exception:
                        dt_obj = None
                    existing_timestamps.append(dt_obj.timestamp() if dt_obj else 0.0)
        except Exception as e:
            logger.error(f"Error loading {master_file}: {e}")
            existing_records, existing_ids, existing_timestamps = [], set(), []
    return existing_records, existing_ids, existing_timestamps


def _fetch_and_write_videos(candidate_ids: list, master_file: str, context_terms: list,
                            lsh, hash_by_id, log_label: str) -> str:
    """
    Shared fetch/filter/write core for both keyword mode and account-only
    mode -- they differ only in how ``candidate_ids`` are discovered and what
    context_terms feed asset detection.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=MAX_PAST_MINUTES)
    existing_records, existing_ids, existing_timestamps = _load_existing_videos(master_file)

    # Match on the exact "_{video_id}" suffix rather than a raw substring
    # check -- a plain `vid in existing_id` could false-positive if the
    # video ID happens to appear inside another record's channel_id.
    new_candidate_ids = [
        vid for vid in candidate_ids
        if not any(existing_id.endswith(f"_{vid}") for existing_id in existing_ids)
    ]
    if not new_candidate_ids:
        logger.info(f"All discovered videos for '{log_label}' are already scraped.")
        return master_file

    fetched_results = []
    with ThreadPoolExecutor(max_workers=FETCH_MAX_WORKERS) as executor:
        future_to_id = {executor.submit(_process_single_video, vid): vid for vid in new_candidate_ids}
        for future in as_completed(future_to_id):
            vid, vurl, meta, text = future.result()
            if meta and text:
                fetched_results.append((vid, vurl, meta, text))

    added_count = 0
    skipped_unsupported_lang = 0

    for vid, vurl, meta, text in fetched_results:
        clean_text = text.replace("\n", " ").strip()
        if not clean_text:
            continue

        created_dt = meta.get("created_dt")
        if created_dt is not None and created_dt < cutoff:
            continue

        lang, confidence = detect_language(clean_text)
        if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
            skipped_unsupported_lang += 1
            continue

        channel_id = meta.get("channel_id") or UNRESOLVED_CHANNEL_ID
        channel_name = meta.get("channel") or "Unknown"
        record_id = f"YouTube_{channel_id}_{vid}"

        if record_id in existing_ids:
            continue

        duplication_info = dedup_utils.check_and_register(record_id, clean_text, lsh, hash_by_id)
        if duplication_info.get("is_duplicate"):
            continue

        collected_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

        asset_evidence_text = (str(meta.get("title") or "") + "\n" + clean_text).strip()
        sentiment, asset_mention = analyze_text(
            clean_text, lang, asset_text=asset_evidence_text, context_terms=context_terms)

        record = {
            "record_id": record_id,
            "Source": {
                "platform": "YouTube",
                "Source_type": "Social_media",
                "Source_name": channel_name,
                "Source_id": vid,
                "url": vurl,
                "author_name": channel_name,
                "author_id": channel_id
            },
            "Content": {
                "Content_type": "video",
                "title": meta.get("title", "N/A"),
                "raw_text": clean_text,
                "Clean_text": "",
                "language": lang
            },
            "time_stamps": {
                "published_at": meta.get("upload_datetime", "N/A"),
                "collected_at": collected_at,
                "updated_at": meta.get("updated_at")
            },
            "asset_mention": asset_mention,
            "sentiment": sentiment,
            "Engagement": {
                "Views": meta.get("view_count", 0),
                "likes": meta.get("like_count", 0),
                "Comments": meta.get("comment_count", 0),
                "shares": 0
            },
            "media": {
                "has_media": True,
                "media_type": "video",
                "media_url": vurl
            },
            "deduplication": duplication_info
        }
        record["quality"] = build_quality(record, complete_raw_text=True, extraction_errors=[])

        _insert_sorted(existing_records, existing_timestamps, record, created_dt)
        existing_ids.add(record_id)
        added_count += 1

    if skipped_unsupported_lang:
        logger.info(f"Filtered out {skipped_unsupported_lang} unsupported-language video(s) for '{log_label}'.")

    if added_count > 0:
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(existing_records, f, indent=4, ensure_ascii=False)
        logger.info(f"Appended {added_count} new sorted videos to {master_file} (Total: {len(existing_records)}).")
    else:
        logger.info(f"No new unique videos to append for '{log_label}'.")

    return master_file


def search_and_scrape_youtube(keyword: str, trusted_channels: list, lsh, hash_by_id, output_dir: str = "yt-transcripts/"):
    """Keyword mode: yt-dlp search results scoped to the trusted channels."""
    os.makedirs(output_dir, exist_ok=True)
    safe_keyword = keyword.replace(" ", "_").lower()
    master_file = os.path.join(output_dir, f"youtube_{safe_keyword}.json")

    candidate_ids = search_youtube_videos(keyword, trusted_channels, max_results=MAX_RESULTS_PER_KEYWORD)
    if not candidate_ids:
        logger.info(f"No video candidates found for '{keyword}'.")
        return None

    return _fetch_and_write_videos(candidate_ids, master_file, context_terms=[keyword],
                                   lsh=lsh, hash_by_id=hash_by_id, log_label=keyword)


def scrape_channel_videos(channel_name: str, lsh, hash_by_id, output_dir: str = "yt-transcripts/"):
    """
    Account-only mode: every recent upload from one trusted channel, no
    keyword filtering or candidate ranking. Relevance is left entirely to
    the asset-mapping stage.
    """
    os.makedirs(output_dir, exist_ok=True)
    channel_id, resolved_name = resolve_channel_id(channel_name)
    if not channel_id:
        logger.error(f"Could not resolve a channel ID for '{channel_name}'. Skipping.")
        return None

    safe_name = channel_name.replace(" ", "_").lower()
    master_file = os.path.join(output_dir, f"youtube_{safe_name}.json")

    candidate_ids = list_channel_uploads(channel_id, max_results=MAX_VIDEOS_PER_CHANNEL)
    if not candidate_ids:
        logger.info(f"No recent uploads found for '{resolved_name or channel_name}'.")
        return None

    return _fetch_and_write_videos(candidate_ids, master_file, context_terms=[],
                                   lsh=lsh, hash_by_id=hash_by_id,
                                   log_label=resolved_name or channel_name)
