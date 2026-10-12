"""Legacy logging behavior extracted without changing data policies."""

from logging.handlers import RotatingFileHandler
import logging
import os
from src.config.paths import LOG_DIR

# Apply before optional lazy model imports.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
import warnings
warnings.filterwarnings("ignore", message=".*sacremoses.*")
logging.getLogger("telethon").setLevel(logging.ERROR)

def setup_logging(name: str, log_file: str = "scraper.log") -> logging.Logger:
    """
    Console + rotating file logging. Replaces bare print() calls so a
    long-running/24-7 process has a persistent, size-capped log to check,
    not just whatever scrolled past in a terminal.

    A bare filename is placed inside ``LOG_DIR`` so every scraper's log lands
    in one directory without each scraper repeating the path.

    The handlers go on the ROOT logger, not just the scraper's own, so that
    warnings raised inside the shared modules reach the scraper's log file.
    They previously did not: ``pipeline_utils`` logs to its own module logger,
    which had no handler, so "sentiment model unavailable" -- the one message
    that explains why a whole run came back with null sentiment -- never
    appeared in the log at all. Chatty third-party loggers are pinned to
    WARNING so this does not turn the file into a transformers/telethon dump.
    """
    logger = logging.getLogger(name)
    if logger.handlers or getattr(setup_logging, "_configured", False):
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if not os.path.dirname(log_file):
        log_file = os.path.join(LOG_DIR, log_file)
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.WARNING)      # gates library loggers, not this one
    root.addHandler(console)
    root.addHandler(file_handler)

    # This scraper and the shared modules report at INFO; a record's level is
    # checked against the logger it was emitted on, then handed to every
    # ancestor handler, so these reach the handlers above while a library
    # left at the root's WARNING does not.
    logger.setLevel(logging.INFO)
    for shared in ("src.config.env", "src.analysis.legacy_text", "src.media.transcription", "src.storage.record_file", "src.filtering.dedup"):
        logging.getLogger(shared).setLevel(logging.INFO)
    for noisy in ("telethon", "transformers", "urllib3", "httpx", "asyncio", "filelock", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    setup_logging._configured = True
    return logger
