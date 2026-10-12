"""
Telegram channel scraper.

Polls a list of trusted Telegram channels for messages published inside a
configurable recent time window and writes them into the shared record schema
used by twtr-scraper.py and yt-scraper.py (dedup, language gate, asset
mapping, quality scoring all come from the shared modules).

This is a single-shot script: it scrapes the window once and exits. Run it
periodically from cron or a systemd timer rather than looping internally.

Prerequisites:
  1. python -m pip install -r requirements.txt
  2. Create an application at https://my.telegram.org to get api_id/api_hash,
     then put them in .env (loaded automatically by pipeline_utils.py):
       TELEGRAM_API_ID=...
       TELEGRAM_API_HASH=...
  3. Create tel-channels.txt with one public channel username per line.

The first run performs an interactive phone-number + login-code sign-in and
stores the result in a local <session>.session file, so every later run
(including unattended cron runs) authenticates without prompting.
"""

import os
import json
import bisect
import random
import asyncio
import datetime

from src.filtering import dedup as dedup_utils
from src.observability.logging import setup_logging
from src.domain.language import detect_language, language_allowed
from src.config.paths import KEYWORDS_DIR, SOURCES_DIR, SESSIONS_DIR
from src.domain.legacy_schema import build_quality
from src.analysis.legacy_text import analyze_text
from src.config.env import env_int, env_float, env_set, env_bool, env_range, env_str

logger = setup_logging("tel-scraper", log_file="tel-scraper.log")

# How far back each run looks. Named MAX_PAST_MINUTES like every other
# scraper's window so one .env value can set them all; keep it comfortably
# larger than the interval your scheduler invokes the script at so nothing
# falls between runs.
# Every constant below is overridable from .env (see .env.example): the bare
# name applies to all scrapers, a "TEL_"-prefixed name applies to this one only.
MAX_PAST_MINUTES = env_int("MAX_PAST_MINUTES", 1440, prefix="TEL")

LANGUAGE_MIN_CONFIDENCE = env_float("LANGUAGE_MIN_CONFIDENCE", 0.70, prefix="TEL")
# Most trusted Telegram channels post in Persian, not English, so both are
# kept rather than filtering the majority of messages out as "non-English".
ALLOWED_LANGUAGES = env_set("ALLOWED_LANGUAGES", {"en", "fa"}, prefix="TEL")
CHANNEL_DELAY_RANGE = env_range("CHANNEL_DELAY_RANGE", (3.0, 6.0), prefix="TEL")  # Jittered pause between channels
MAX_MESSAGES_PER_CHANNEL = env_int("MAX_MESSAGES_PER_CHANNEL", 500, prefix="TEL")  # Safety cap per channel per run

# Re-scan the whole window (instead of only messages newer than the newest one
# already saved) so edits to already-collected posts are picked up and the
# stored record is refreshed. Set to False for the cheapest possible append-only
# run at the cost of never seeing an edit.
REFRESH_EDITED_MESSAGES = env_bool("REFRESH_EDITED_MESSAGES", True, prefix="TEL")

# Telethon transparently sleeps through flood waits shorter than this; longer
# ones surface as FloodWaitError and are handled by _with_flood_retry.
FLOOD_SLEEP_THRESHOLD = env_int("FLOOD_SLEEP_THRESHOLD", 60, prefix="TEL")
FLOOD_WAIT_BUFFER = env_int("FLOOD_WAIT_BUFFER", 5, prefix="TEL")  # Extra seconds added to a server-dictated wait
MAX_FLOOD_RETRIES = env_int("MAX_FLOOD_RETRIES", 3, prefix="TEL")

TELEGRAM_SESSION_NAME = env_str("TELEGRAM_SESSION_NAME", os.path.join(SESSIONS_DIR, "tel-scraper"))
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH")

CHANNELS_FILE = os.path.join(SOURCES_DIR, "tel-channels.txt")
OUTPUT_DIR = "tel-transcripts/"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S UTC"

try:
    from telethon import TelegramClient
    from telethon.errors import (
        ChannelPrivateError,
        FloodWaitError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telethon.tl.types import (
        DocumentAttributeAudio,
        DocumentAttributeVideo,
        MessageMediaDocument,
        MessageMediaPhoto,
        MessageMediaWebPage,
    )
except ImportError:
    logger.error("telethon is not installed. Run: python -m pip install -r requirements.txt")
    exit(1)


def load_trusted_channels(filepath: str = CHANNELS_FILE) -> list:
    """
    Loads trusted channel usernames from a file.

    Unlike the X/YouTube account lists this file has no auto-created defaults:
    Telegram usernames for news outlets are not reliably guessable, and a wrong
    guess would silently scrape the wrong channel rather than fail.
    """
    if not os.path.exists(filepath):
        logger.error(
            f"File '{filepath}' not found. Create it with one public channel "
            f"username per line (e.g. 'reuters'), '#' for comments."
        )
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        channels = [
            line.strip().lstrip("@")
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    # Preserve file order while dropping accidental repeats.
    seen = set()
    unique = []
    for channel in channels:
        key = channel.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(channel)
    return unique


def _format_timestamp(dt_val) -> str:
    """Renders a Telegram datetime in the shared schema's UTC string format."""
    if dt_val is None:
        return None
    return dt_val.astimezone(datetime.timezone.utc).strftime(TIMESTAMP_FMT)


def _parse_published_at(value):
    """Parses a stored published_at string back into a datetime for sorting."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.datetime.strptime(value, TIMESTAMP_FMT)
        return dt.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


def _insert_sorted(records_list: list, timestamps_list: list, record: dict, dt_val):
    """
    Inserts a record into the list maintaining chronological order via binary search.
    """
    sort_key = dt_val.timestamp() if dt_val else 0.0
    idx = bisect.bisect_right(timestamps_list, sort_key)
    records_list.insert(idx, record)
    timestamps_list.insert(idx, sort_key)


def _extract_media_info(message, post_url: str) -> dict:
    """
    Maps a Telegram message's attachment onto the shared media schema.

    Telegram does not expose a stable public direct-media URL, so the post's own
    t.me link doubles as media_url (pipeline_utils validates that consistency).
    """
    media = getattr(message, "media", None)
    if not media:
        return {"has_media": False, "media_type": None, "media_url": None}

    if isinstance(media, MessageMediaPhoto):
        media_type = "photo"
    elif isinstance(media, MessageMediaWebPage):
        media_type = "webpage"
    elif isinstance(media, MessageMediaDocument):
        attributes = getattr(getattr(media, "document", None), "attributes", None) or []
        if any(isinstance(a, DocumentAttributeVideo) for a in attributes):
            media_type = "video"
        elif any(isinstance(a, DocumentAttributeAudio) for a in attributes):
            media_type = "audio"
        else:
            media_type = "document"
    else:
        media_type = "other"

    return {"has_media": True, "media_type": media_type, "media_url": post_url}


def _reaction_total(message) -> int:
    """Sums every reaction bucket on a message into a single 'likes' count."""
    results = getattr(getattr(message, "reactions", None), "results", None) or []
    total = 0
    for result in results:
        count = getattr(result, "count", 0)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            total += count
    return total


def _build_engagement(message) -> dict:
    replies = getattr(getattr(message, "replies", None), "replies", 0)
    return {
        "Views": getattr(message, "views", None) or 0,
        "likes": _reaction_total(message),
        "Comments": replies if isinstance(replies, int) and not isinstance(replies, bool) else 0,
        "shares": getattr(message, "forwards", None) or 0,
    }


async def _with_flood_retry(operation, description: str):
    """
    Runs an awaitable factory, honouring the wait Telegram dictates on a flood.

    pipeline_utils.with_retry backs off on a fixed schedule; Telegram instead
    tells us exactly how long to wait, so that value is used directly.
    """
    for attempt in range(1, MAX_FLOOD_RETRIES + 1):
        try:
            return await operation()
        except FloodWaitError as e:
            wait_seconds = int(getattr(e, "seconds", 0)) + FLOOD_WAIT_BUFFER
            if attempt == MAX_FLOOD_RETRIES:
                logger.error(f"Flood wait of {wait_seconds}s on {description} exhausted retries. Skipping.")
                raise
            logger.warning(
                f"Rate limited on {description}; sleeping {wait_seconds}s "
                f"(attempt {attempt}/{MAX_FLOOD_RETRIES})."
            )
            await asyncio.sleep(wait_seconds)
    return None


async def _collect_messages(client, entity, min_id: int, cutoff) -> list:
    """
    Pulls messages newest-first, stopping at the time-window boundary.

    iter_messages yields newest first, so the first message older than the
    cutoff means every remaining one is older too and iteration can stop.
    """
    collected = []
    async for message in client.iter_messages(entity, min_id=min_id, limit=MAX_MESSAGES_PER_CHANNEL):
        published = getattr(message, "date", None)
        if published is None:
            continue
        if published.astimezone(datetime.timezone.utc) < cutoff:
            break
        collected.append(message)
    return collected


def _build_record(message, channel_username: str, channel_title: str, clean_text: str,
                  lang: str, duplication_info: dict, collected_at: str) -> dict:
    """Assembles one message into the shared cross-platform record schema."""
    post_url = f"https://t.me/{channel_username}/{message.id}"
    sentiment, asset_mention = analyze_text(clean_text, lang)
    record = {
        "record_id": f"Telegram_{channel_username}_{message.id}",
        "Source": {
            "platform": "Telegram",
            "Source_type": "Social_media",
            "Source_name": channel_title,
            "Source_id": str(message.id),
            "url": post_url,
            "author_name": channel_title,
            "author_id": channel_username
        },
        "Content": {
            "Content_type": "message",
            "title": "N/A",
            "raw_text": clean_text,
            "Clean_text": "",
            "language": lang
        },
        "time_stamps": {
            "published_at": _format_timestamp(message.date),
            "collected_at": collected_at,
            # Telegram genuinely reports edits, so unlike X/YouTube this field
            # carries a real value instead of always being null.
            "updated_at": _format_timestamp(getattr(message, "edit_date", None))
        },
        "asset_mention": asset_mention,
        "sentiment": sentiment,
        "Engagement": _build_engagement(message),
        "media": _extract_media_info(message, post_url),
        "deduplication": duplication_info
    }
    record["quality"] = build_quality(record, complete_raw_text=True, extraction_errors=[])
    return record


async def scrape_channel(client, channel_username: str, lsh, hash_by_id, output_dir: str = OUTPUT_DIR):
    """
    Scrapes one channel's recent window and merges it into that channel's file.
    """
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(minutes=MAX_PAST_MINUTES)

    safe_channel = channel_username.replace(" ", "_").lower()
    master_file = os.path.join(output_dir, f"telegram_{safe_channel}.json")

    # Load existing records and create fast lookup structures
    existing_records = []
    existing_ids = set()
    existing_timestamps = []
    records_by_id = {}
    last_seen_id = 0

    if os.path.exists(master_file):
        try:
            with open(master_file, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
                for rec in existing_records:
                    rec_id = rec.get("record_id")
                    if rec_id:
                        existing_ids.add(rec_id)
                        records_by_id[rec_id] = rec
                    source_id = rec.get("Source", {}).get("Source_id")
                    if str(source_id).isdigit():
                        last_seen_id = max(last_seen_id, int(source_id))
                    # Extract timestamp for maintaining sorted insertion
                    pub_str = rec.get("time_stamps", {}).get("published_at")
                    dt_obj = _parse_published_at(pub_str)
                    existing_timestamps.append(dt_obj.timestamp() if dt_obj else 0.0)
        except Exception as e:
            logger.error(f"Error reading {master_file}: {e}")
            existing_records = []
            existing_ids = set()
            existing_timestamps = []
            records_by_id = {}
            last_seen_id = 0

    try:
        entity = await _with_flood_retry(
            lambda: client.get_entity(channel_username),
            f"resolving @{channel_username}",
        )
    except (UsernameNotOccupiedError, UsernameInvalidError, ValueError):
        logger.error(f"Channel '@{channel_username}' does not exist or is not resolvable. Skipping.")
        return None
    except ChannelPrivateError:
        logger.error(f"Channel '@{channel_username}' is private or your account was banned from it. Skipping.")
        return None
    except Exception as e:
        logger.error(f"Could not resolve '@{channel_username}': {type(e).__name__}: {e}")
        return None

    resolved_username = getattr(entity, "username", None)
    if not resolved_username:
        logger.error(
            f"Channel '@{channel_username}' has no public username, so no stable "
            f"t.me post URL can be built. Skipping."
        )
        return None

    channel_title = (getattr(entity, "title", None) or resolved_username).strip()

    # Anything at or below last_seen_id is already stored; skipping it saves an
    # API round trip, but skip that optimisation when edits should be refreshed.
    min_id = 0 if REFRESH_EDITED_MESSAGES else last_seen_id

    try:
        messages = await _with_flood_retry(
            lambda: _collect_messages(client, entity, min_id, cutoff),
            f"reading @{resolved_username}",
        )
    except Exception as e:
        logger.error(f"Failed to read messages from '@{resolved_username}': {type(e).__name__}: {e}")
        return None

    if not messages:
        logger.info(f"No messages in the last {MAX_PAST_MINUTES} minute(s) for '@{resolved_username}'.")
        return master_file

    added_count = 0
    refreshed_count = 0
    skipped_non_english = 0
    duplicates_kept = 0
    collected_at = datetime.datetime.now(datetime.timezone.utc).strftime(TIMESTAMP_FMT)

    for message in messages:
        text = (getattr(message, "raw_text", None) or getattr(message, "message", None) or "")
        if not text.strip():
            continue

        clean_text = text.replace("\n", " ")
        record_id = f"Telegram_{resolved_username}_{message.id}"

        # Already stored: only revisit it when Telegram reports a newer edit.
        if record_id in existing_ids:
            stored = records_by_id.get(record_id)
            edited_at = _format_timestamp(getattr(message, "edit_date", None))
            if not (REFRESH_EDITED_MESSAGES and stored and edited_at
                    and stored.get("time_stamps", {}).get("updated_at") != edited_at):
                continue

            lang, confidence = detect_language(clean_text)
            if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
                continue

            duplication_info = dedup_utils.check_and_register(record_id, clean_text, lsh, hash_by_id)
            refreshed = _build_record(
                message, resolved_username, channel_title, clean_text,
                lang, duplication_info, collected_at,
            )
            # Replace in place: an edit never changes published_at, so the
            # record keeps its position in the chronologically sorted file.
            stored.clear()
            stored.update(refreshed)
            refreshed_count += 1
            continue

        lang, confidence = detect_language(clean_text)
        if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
            skipped_non_english += 1
            continue

        # Tagged, not dropped -- the same rule the other account-driven
        # scrapers now follow. The channel is a trusted source and every
        # message it posted inside the window belongs in the output; the flag
        # stays on the record for a downstream stage to collapse repeats.
        # Dropping here was also unrecoverable: registration happens before the
        # file is written, so a run that died mid-write left the messages in
        # the dedup index and invisible to every later run.
        duplication_info = dedup_utils.check_and_register(record_id, clean_text, lsh, hash_by_id)
        if duplication_info.get("is_duplicate"):
            duplicates_kept += 1

        record = _build_record(
            message, resolved_username, channel_title, clean_text,
            lang, duplication_info, collected_at,
        )

        published_dt = message.date.astimezone(datetime.timezone.utc) if message.date else None
        _insert_sorted(existing_records, existing_timestamps, record, published_dt)
        existing_ids.add(record_id)
        records_by_id[record_id] = record
        added_count += 1

    if skipped_non_english:
        logger.info(f"Filtered out {skipped_non_english} message(s) for '@{resolved_username}' in an unsupported language.")
    if duplicates_kept:
        logger.info(f"Kept {duplicates_kept} message(s) flagged as cross-source duplicates for '@{resolved_username}'.")

    if added_count or refreshed_count:
        # Re-created here, not just at the top of the function: a channel scrape
        # can run for tens of minutes, and losing the whole window's work to a
        # missing directory at the final write is the worst possible moment to
        # fail. RecordFile.save() guards its write the same way.
        os.makedirs(os.path.dirname(master_file) or ".", exist_ok=True)
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(existing_records, f, indent=4, ensure_ascii=False)
        logger.info(
            f"Appended {added_count} new (refreshed {refreshed_count}) sorted messages to "
            f"{master_file} (Total: {len(existing_records)})."
        )
    else:
        logger.info(f"No new unique messages to append for '@{resolved_username}'.")

    return master_file
