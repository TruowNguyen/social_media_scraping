"""Legacy env behavior extracted without changing data policies."""

import logging
import os
import sys
from dotenv import load_dotenv

# Shell exports take precedence; initialize once for all legacy components.
load_dotenv()

def _env_raw(name: str, prefix: str = ""):
    for key in ([f"{prefix}_{name}"] if prefix else []) + [name]:
        value = os.environ.get(key)
        if value is not None and value.strip():
            return key, value.strip()
    return None, None

def _env_parsed(name: str, default, prefix: str, parse):
    key, value = _env_raw(name, prefix)
    if value is None:
        return default
    try:
        return parse(value)
    except (TypeError, ValueError) as e:
        logging.getLogger(__name__).warning(
            "Invalid value for %s (%r): %s. Using default %r.", key, value, e, default
        )
        return default

def env_str(name: str, default: str = "", prefix: str = "") -> str:
    return _env_parsed(name, default, prefix, str)

def env_int(name: str, default: int, prefix: str = "") -> int:
    return _env_parsed(name, default, prefix, lambda v: int(float(v)))

def env_float(name: str, default: float, prefix: str = "") -> float:
    return _env_parsed(name, default, prefix, float)

def env_bool(name: str, default: bool, prefix: str = "") -> bool:
    def parse(value):
        lowered = value.casefold()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError("expected a boolean like true/false")
    return _env_parsed(name, default, prefix, parse)

def env_set(name: str, default: set, prefix: str = "") -> set:
    """Comma-separated list -> set of lowercased items (e.g. ALLOWED_LANGUAGES=en,fa)."""
    return _env_parsed(
        name, default, prefix,
        lambda v: {item.strip().casefold() for item in v.split(",") if item.strip()},
    )

def env_range(name: str, default: tuple, prefix: str = "") -> tuple:
    """"min,max" -> (float, float), used for the jittered pacing delays."""
    def parse(value):
        parts = [float(p) for p in value.split(",")]
        if len(parts) != 2 or parts[0] > parts[1]:
            raise ValueError("expected 'min,max' with min <= max")
        return (parts[0], parts[1])
    return _env_parsed(name, default, prefix, parse)

def get_scrape_mode(logger=None, prefix: str = "") -> str:
    """Returns "keyword" or "accounts" for this run.

    Read from SCRAPE_MODE (or <PREFIX>_SCRAPE_MODE) so a cron/bash wrapper can
    pick the discovery method with no terminal input. Only an interactive
    terminal falls back to asking; a non-interactive run with no variable set
    uses "keyword", which is the historical behaviour of every scraper that
    has keywords.
    """
    log = logger or logging.getLogger(__name__)
    key, value = _env_raw("SCRAPE_MODE", prefix)
    if value:
        mode = value.casefold()
        aliases = {"keyword": "keyword", "keywords": "keyword",
                   "accounts": "accounts", "account": "accounts", "channels": "accounts"}
        if mode in aliases:
            log.info(f"{key}={mode} set in environment; skipping interactive prompt.")
            return aliases[mode]
        log.warning(f"Unrecognised {key}={value!r}; expected 'keyword' or 'accounts'.")

    if not sys.stdin.isatty():
        log.info("SCRAPE_MODE not set and no terminal attached; defaulting to 'keyword' mode.")
        return "keyword"

    while True:
        choice = input(
            "Scrape by (1) keyword, prioritizing trusted accounts, or "
            "(2) trusted accounts only (all recent posts, no keyword)? [1/2]: "
        ).strip()
        if choice == "1":
            return "keyword"
        if choice == "2":
            return "accounts"
        print("Please enter 1 or 2.")
