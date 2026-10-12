"""
Truth Social account scraper.

Truth Social is a Mastodon fork, so its public read endpoints are the standard
Mastodon ones (/api/v1/accounts/lookup, /api/v1/accounts/<id>/statuses). This
scraper logs in once per run to obtain a bearer token, then walks each trusted
account's recent posts into the shared record schema used by the other
scrapers.

Like tel-scraper.py and tiktok-scraper.py there is no keyword search step:
discovery is account-driven and relevance is left to the asset-mapping stage.

Prerequisites:
  1. python -m pip install -r requirements.txt
  2. A Truth Social account, put in .env (loaded automatically by
     pipeline_utils.py):
       TRUTHSOCIAL_USERNAME=...
       TRUTHSOCIAL_PASSWORD=...
     (or TRUTHSOCIAL_TOKEN=... to reuse a bearer token directly and skip
     the login step entirely).
  3. truth-accounts.txt with one account username per line.

Cloudflare rejects most unauthenticated reads, which is why the token is
required rather than optional.
"""

import os
import re
import json
import time
import html
import random
import datetime
import urllib.error
import urllib.parse
import urllib.request

from src.filtering import dedup as dedup_utils
from src.observability.logging import setup_logging
from src.resilience.rate_limit import RateLimiter
from src.resilience.retry import with_retry
from src.domain.language import detect_language, language_allowed
from src.config.paths import KEYWORDS_DIR, SOURCES_DIR
from src.domain.legacy_schema import build_quality
from src.analysis.legacy_text import analyze_text
from src.config.env import get_scrape_mode, env_int, env_float, env_set, env_range, env_str, env_bool
from src.discovery.keyword_matching import keyword_matches
from src.storage.record_file import RecordFile

logger = setup_logging("truth-scraper", log_file="truth-scraper.log")

# Every constant below is overridable from .env (see .env.example): the bare
# name applies to all scrapers, a "TS_"-prefixed name applies to this one only.
MAX_POSTS_PER_ACCOUNT = env_int("MAX_POSTS_PER_ACCOUNT", 80, prefix="TS")
MAX_PAST_MINUTES = env_int("MAX_PAST_MINUTES", 30 * 24 * 60, prefix="TS")  # default 30 days
PAGE_SIZE = env_int("PAGE_SIZE", 40, prefix="TS")                          # Requested per page; the server caps a page at 20
API_TIMEOUT = env_int("API_TIMEOUT", 30, prefix="TS")                      # Seconds per API call
# Wall-clock budget for paging ONE account. Cloudflare throttles deep paging by
# trickling the response rather than refusing it, and a socket timeout never
# fires on a connection that keeps delivering a few bytes. Without this ceiling
# a single slow account can hang an unattended run indefinitely.
ACCOUNT_TIME_BUDGET = env_int("ACCOUNT_TIME_BUDGET", 180, prefix="TS")      # Seconds

FETCH_MIN_INTERVAL = env_float("FETCH_MIN_INTERVAL", 1.5, prefix="TS")            # Seconds between API calls, enforced globally
ACCOUNT_DELAY_RANGE = env_range("ACCOUNT_DELAY_RANGE", (3.0, 6.0), prefix="TS")   # Jittered pause between accounts

LANGUAGE_MIN_CONFIDENCE = env_float("LANGUAGE_MIN_CONFIDENCE", 0.70, prefix="TS")
ALLOWED_LANGUAGES = env_set("ALLOWED_LANGUAGES", {"en", "fa"}, prefix="TS")
# Replies are posts the account made too, so they are collected by default.
# Set TS_EXCLUDE_REPLIES=true to go back to top-level posts only.
EXCLUDE_REPLIES = env_bool("EXCLUDE_REPLIES", False, prefix="TS")

KEYWORDS_FILE = os.path.join(KEYWORDS_DIR, "truth-keywords.txt")
ACCOUNTS_FILE = os.path.join(SOURCES_DIR, "truth-accounts.txt")
OUTPUT_DIR = "truth-posts/"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S UTC"

API_BASE = "https://truthsocial.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# Truth Social's own web client credentials. These are public values shipped in
# the site's JavaScript bundle, not secrets -- unlike TRUTHSOCIAL_PASSWORD,
# which is read from the environment and never stored here.
CLIENT_ID = env_str("TRUTHSOCIAL_CLIENT_ID", "9X1Fdd-pxNsAgEDNi_SfhJWi8T-vLuV2WVzKIbkTCw4")
CLIENT_SECRET = env_str("TRUTHSOCIAL_CLIENT_SECRET", "ozF8jzI4968oTKFkEnsBC-UbLPCdrSv0MkXGQu2o_-M")

TRUTHSOCIAL_USERNAME = env_str("TRUTHSOCIAL_USERNAME") or None
TRUTHSOCIAL_PASSWORD = env_str("TRUTHSOCIAL_PASSWORD") or None
TRUTHSOCIAL_TOKEN = env_str("TRUTHSOCIAL_TOKEN") or None

_fetch_rate_limiter = RateLimiter(FETCH_MIN_INTERVAL)

def _read_bounded(response) -> bytes:
    """Reads a response body under a wall-clock deadline.

    ``urlopen(timeout=...)`` bounds each individual socket operation, not the
    call as a whole. Cloudflare throttles a client it considers too eager by
    TRICKLING the response instead of refusing it, and a body that delivers a
    few bytes every couple of seconds never trips a per-read timeout -- the
    call simply never returns, which hung unattended runs indefinitely. Reading
    in chunks and checking the clock between them is what actually bounds it.
    """
    deadline = time.monotonic() + API_TIMEOUT
    chunks = []
    while True:
        if time.monotonic() > deadline:
            raise _RetryableApiError(f"response body still arriving after {API_TIMEOUT}s")
        chunk = response.read(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


class _RetryableApiError(Exception):
    """A transient API failure worth retrying (timeout, connection reset, 429, 5xx)."""


_BLOCK_TAG_RE = re.compile(r"</?(?:p|br|div|li)[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def load_trusted_accounts(filepath: str = ACCOUNTS_FILE) -> list:
    """
    Loads trusted Truth Social usernames from a file.

    As with tel-channels.txt there are no auto-created defaults: a guessed
    handle would silently scrape an impersonator account instead of failing.
    """
    if not os.path.exists(filepath):
        logger.error(
            f"File '{filepath}' not found. Create it with one Truth Social "
            f"username per line (e.g. 'realDonaldTrump'), '#' for comments."
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


def _html_to_text(content: str) -> str:
    """
    Flattens a status's HTML body into plain text.

    Block-level tags become spaces first so that paragraphs and line breaks do
    not weld the last word of one line onto the first word of the next.
    """
    if not content:
        return ""
    text = _BLOCK_TAG_RE.sub(" ", content)
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _parse_api_timestamp(value):
    """Parses a Mastodon ISO-8601 timestamp into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _format_timestamp(value) -> str:
    dt = _parse_api_timestamp(value)
    return dt.strftime(TIMESTAMP_FMT) if dt else None


@with_retry(max_attempts=3, base_delay=5.0, exceptions=(_RetryableApiError,))
def _api_request(path: str, token: str = None, params: dict = None, payload: dict = None):
    """Performs one authenticated call against the Mastodon-compatible API.

    Retried with backoff: Cloudflare fronts this API and answers a client it
    considers too eager by stalling the connection rather than refusing it, so
    a timeout here is usually transient. Combined with ACCOUNT_TIME_BUDGET in
    fetch_statuses, a throttled account costs the run one bounded pause
    instead of hanging it.
    """
    url = API_BASE + path
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            return json.loads(_read_bounded(response).decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 429/5xx is "come back later" and worth a retry; 401/403/404 is a
        # verdict about this request and retrying only wastes the budget.
        if e.code == 429 or e.code >= 500:
            raise _RetryableApiError(f"HTTP {e.code}") from e
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise _RetryableApiError(f"{type(e).__name__}: {e}") from e


def login() -> str:
    """
    Exchanges the configured account credentials for a read-scoped bearer token.

    A token supplied via TRUTHSOCIAL_TOKEN is used as-is so an unattended run
    can skip the password grant entirely.
    """
    if TRUTHSOCIAL_TOKEN:
        logger.info("Using bearer token from TRUTHSOCIAL_TOKEN.")
        return TRUTHSOCIAL_TOKEN

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "password",
        "username": TRUTHSOCIAL_USERNAME,
        "password": TRUTHSOCIAL_PASSWORD,
        # The web client always sends this even for a password grant; omitting
        # it makes the token endpoint reject valid credentials outright.
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        # Only read scope is requested: this scraper never posts or follows.
        "scope": "read",
    }
    result = _api_request("/oauth/v2/token", payload=payload)
    token = result.get("access_token")
    if not token:
        raise RuntimeError("login succeeded but returned no access_token")
    logger.info("Authenticated against Truth Social.")
    return token


def lookup_account(username: str, token: str) -> dict:
    _fetch_rate_limiter.wait()
    return _api_request("/api/v1/accounts/lookup", token=token, params={"acct": username})


def fetch_statuses(account_id: str, token: str, cutoff) -> list:
    """
    Pages back through an account's posts until the time window or the cap.

    Statuses come back newest-first, so the first post older than the cutoff
    means every remaining one is older too and paging can stop.
    """
    statuses = []
    max_id = None
    deadline = time.monotonic() + ACCOUNT_TIME_BUDGET

    while len(statuses) < MAX_POSTS_PER_ACCOUNT:
        if time.monotonic() > deadline:
            logger.warning(
                f"Time budget of {ACCOUNT_TIME_BUDGET}s reached after {len(statuses)} post(s); "
                f"keeping them and moving on."
            )
            break
        params = {"limit": min(PAGE_SIZE, MAX_POSTS_PER_ACCOUNT - len(statuses))}
        if EXCLUDE_REPLIES:
            params["exclude_replies"] = "true"
        if max_id:
            params["max_id"] = max_id

        _fetch_rate_limiter.wait()
        try:
            page = _api_request(f"/api/v1/accounts/{account_id}/statuses", token=token, params=params)
        except Exception as e:
            # Now that paging walks the whole window rather than stopping at
            # the first short page, a single slow page is likely on a busy
            # account. Keep what was already collected instead of losing the
            # account for the run.
            logger.warning(
                f"Stopped paging after {len(statuses)} post(s): "
                f"{type(e).__name__}: {str(e).splitlines()[0]}"
            )
            break
        if not isinstance(page, list) or not page:
            break

        reached_cutoff = False
        for status in page:
            published = _parse_api_timestamp(status.get("created_at"))
            if published and published < cutoff:
                reached_cutoff = True
                break
            statuses.append(status)

        # Deliberately NOT "len(page) < limit": Truth Social caps a page at 20
        # statuses however many were asked for, so treating a short page as the
        # end of the timeline stopped every account after its first page and
        # capped a 30-day window at 20 posts. Only an EMPTY page, the time
        # cutoff, or MAX_POSTS_PER_ACCOUNT ends the walk.
        if reached_cutoff:
            break
        max_id = page[-1].get("id")
        if not max_id:
            break

    return statuses


def _media_alt_text(status: dict) -> str:
    """Best available text for a post whose body is empty.

    A media-only post still carries a spoiler/CW line or per-attachment alt
    text often enough to be worth keeping; that beats storing nothing.
    """
    parts = [str(status.get("spoiler_text") or "").strip()]
    for attachment in (status.get("media_attachments") or []):
        parts.append(str(attachment.get("description") or "").strip())
    return " ".join(p for p in parts if p).strip()


def _extract_media_info(status: dict) -> dict:
    """Maps a status's first attachment onto the shared media schema."""
    attachments = status.get("media_attachments") or []
    if not attachments:
        return {"has_media": False, "media_type": None, "media_url": None}

    attachment = attachments[0]
    media_type = {"image": "photo", "gifv": "video", "video": "video", "audio": "audio"}.get(
        attachment.get("type"), attachment.get("type") or "other"
    )
    media_url = attachment.get("url") or attachment.get("preview_url")
    if not (isinstance(media_url, str) and media_url.startswith(("http://", "https://"))):
        return {"has_media": False, "media_type": None, "media_url": None}

    return {"has_media": True, "media_type": media_type, "media_url": media_url}


def _build_engagement(status: dict) -> dict:
    """Truth Social exposes no view count, so Views stays 0 rather than guessed."""
    return {
        "Views": 0,
        "likes": max(0, int(status.get("favourites_count") or 0)),
        "Comments": max(0, int(status.get("replies_count") or 0)),
        "shares": max(0, int(status.get("reblogs_count") or 0)),
    }


def _build_record(status: dict, username: str, display_name: str, raw_text: str,
                  lang: str, duplication_info: dict, collected_at: str,
                  context_terms=None, media_status: dict = None,
                  text_is_complete: bool = True) -> dict:
    """Assembles one status into the shared cross-platform record schema.

    ``media_status`` is the status the CONTENT came from -- the reblogged post
    for a repost, otherwise the status itself. Identity, id, URL and timestamps
    always come from ``status``, so a repost stays addressable at this
    account's own permalink.
    """
    media_status = media_status or status
    status_id = str(status.get("id"))
    sentiment, asset_mention = analyze_text(
        raw_text, lang, context_terms=context_terms or [])
    record = {
        "record_id": f"TruthSocial_{username}_{status_id}",
        "Source": {
            "platform": "TruthSocial",
            "Source_type": "Social_media",
            "Source_name": display_name,
            "Source_id": status_id,
            "url": f"{API_BASE}/@{username}/posts/{status_id}",
            "author_name": display_name,
            "author_id": username
        },
        "Content": {
            "Content_type": "post",
            "title": "N/A",
            "raw_text": raw_text,
            "Clean_text": "",
            "language": lang
        },
        "time_stamps": {
            "published_at": _format_timestamp(status.get("created_at")),
            "collected_at": collected_at,
            # Mastodon-family servers report a real edit timestamp, so this
            # field carries a value where the post was actually edited.
            "updated_at": _format_timestamp(status.get("edited_at"))
        },
        "asset_mention": asset_mention,
        "sentiment": sentiment,
        "Engagement": _build_engagement(status),
        "media": _extract_media_info(media_status),
        "deduplication": duplication_info
    }
    record["quality"] = build_quality(
        record,
        complete_raw_text=text_is_complete,
        extraction_errors=[] if text_is_complete else ["media-only post: no text body on the status"],
    )
    return record


def scrape_account(username: str, token: str, lsh, hash_by_id, keywords=None, output_dir: str = OUTPUT_DIR):
    """Scrapes one account's recent posts into the right output file(s).

    Account-only mode (``keywords`` empty) keeps every post inside the time
    window in ``truthsocial_<account>.json``. Keyword mode pages exactly the
    same trusted-account timelines -- the trusted accounts are the search
    space, since Truth Social's search endpoint is unscoped and Cloudflare
    gated -- and files each post under the first keyword it matches, in
    ``truthsocial_<keyword>.json``. A post matching no keyword is dropped in
    that mode.
    """
    os.makedirs(output_dir, exist_ok=True)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=MAX_PAST_MINUTES)

    try:
        account = lookup_account(username, token)
    except urllib.error.HTTPError as e:
        logger.error(f"Could not resolve '@{username}': HTTP {e.code}. Skipping.")
        return None
    except Exception as e:
        logger.error(f"Could not resolve '@{username}': {type(e).__name__}: {e}")
        return None

    account_id = account.get("id")
    if not account_id:
        logger.error(f"Account '@{username}' returned no id. Skipping.")
        return None

    # Use the handle the server reports, so a renamed account is stored under
    # its real username and the record_id/URL checks stay consistent.
    resolved_username = account.get("username") or username
    display_name = (account.get("display_name") or resolved_username).strip()

    if keywords:
        buckets = {
            keyword: RecordFile(
                os.path.join(output_dir, f"truthsocial_{keyword.replace(' ', '_').lower()}.json"), logger
            )
            for keyword in keywords
        }
    else:
        safe_account = resolved_username.replace(" ", "_").lower()
        buckets = {None: RecordFile(os.path.join(output_dir, f"truthsocial_{safe_account}.json"), logger)}

    try:
        statuses = fetch_statuses(account_id, token, cutoff)
    except Exception as e:
        logger.error(f"Failed reading posts for '@{resolved_username}': {type(e).__name__}: {e}")
        return None

    if not statuses:
        logger.info(f"No posts in the last {MAX_PAST_MINUTES} minute(s) for '@{resolved_username}'.")
        return None

    logger.info(f"Found {len(statuses)} candidate post(s) for '@{resolved_username}'.")

    skipped_unsupported_lang = 0
    skipped_no_keyword = 0
    reblogged = 0
    media_only = 0
    duplicates_kept = 0
    collected_at = datetime.datetime.now(datetime.timezone.utc).strftime(TIMESTAMP_FMT)

    for status in statuses:
        status_id = str(status.get("id") or "")
        if not status_id:
            continue

        record_id = f"TruthSocial_{resolved_username}_{status_id}"
        if any(bucket.has(record_id) for bucket in buckets.values()):
            continue

        # A reblog is a post this trusted account chose to amplify, so it is
        # collected like any other. Its text and media come from the reblogged
        # status, while the identity/URL stay this account's -- the record is
        # "@account reposted this", which is exactly what happened.
        reblog = status.get("reblog") if isinstance(status.get("reblog"), dict) else None
        if reblog:
            reblogged += 1
        content_status = reblog or status

        raw_text = _html_to_text(content_status.get("content"))
        if not raw_text:
            # A media-only post (image/video, no caption) is still a post from
            # a trusted account inside the window. It is stored with the media
            # description as text where one exists, and flagged as an
            # incomplete extraction so the quality score reflects reality --
            # dropping it silently lost roughly half of some accounts' output.
            raw_text = _media_alt_text(content_status)
            text_is_complete = bool(raw_text)
            if not raw_text:
                raw_text = "[media-only post with no text]"
            media_only += 1
        else:
            text_is_complete = True

        matched_keyword = None
        if keywords:
            matched_keyword = next((kw for kw in keywords if keyword_matches(raw_text, kw)), None)
            if matched_keyword is None:
                skipped_no_keyword += 1
                continue

        lang, confidence = detect_language(raw_text)
        if not language_allowed(lang, confidence, ALLOWED_LANGUAGES, LANGUAGE_MIN_CONFIDENCE):
            skipped_unsupported_lang += 1
            continue

        # Tagged, not dropped: the account is a trusted source and every post
        # it made inside the window belongs in the output. The flag stays on
        # the record for a downstream stage to collapse repeats.
        duplication_info = dedup_utils.check_and_register(record_id, raw_text, lsh, hash_by_id)
        if duplication_info.get("is_duplicate"):
            duplicates_kept += 1

        record = _build_record(status, resolved_username, display_name, raw_text,
                               lang, duplication_info, collected_at,
                               context_terms=[matched_keyword] if matched_keyword else [],
                               media_status=content_status, text_is_complete=text_is_complete)

        buckets[matched_keyword].add(record, _parse_api_timestamp(status.get("created_at")))

    if skipped_unsupported_lang:
        logger.info(f"Filtered out {skipped_unsupported_lang} unsupported-language post(s) for '@{resolved_username}'.")
    if skipped_no_keyword:
        logger.info(f"Filtered out {skipped_no_keyword} post(s) matching no keyword for '@{resolved_username}'.")
    if reblogged:
        logger.info(f"Collected {reblogged} repost(s) for '@{resolved_username}'.")
    if media_only:
        logger.info(f"Collected {media_only} media-only post(s) for '@{resolved_username}'.")
    if duplicates_kept:
        logger.info(f"Kept {duplicates_kept} post(s) flagged as cross-source duplicates for '@{resolved_username}'.")

    written = [bucket.path for bucket in buckets.values() if bucket.save()]
    if not written:
        logger.info(f"No new unique posts to append for '@{resolved_username}'.")
    return written or None


def load_keywords(filepath: str = KEYWORDS_FILE) -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
