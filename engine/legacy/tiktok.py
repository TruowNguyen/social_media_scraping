"""Legacy tiktok watchlist orchestration; preserves CLI behavior."""
import time
import random
import datetime
from src.collectors.tiktok import collector as source

def main():
    accounts = source.load_trusted_accounts(source.ACCOUNTS_FILE)
    if not accounts:
        source.logger.error(f"No accounts found in {source.ACCOUNTS_FILE}.")
        return

    source.logger.info(f"Loaded {len(accounts)} trusted accounts from {source.ACCOUNTS_FILE}.")

    mode = source.get_scrape_mode(source.logger, prefix="TT")
    keywords = []
    if mode == "keyword":
        keywords = source.load_keywords(source.KEYWORDS_FILE)
        if not keywords:
            source.logger.error(
                f"Keyword mode needs '{source.KEYWORDS_FILE}' with one keyword per line. "
                f"Set SCRAPE_MODE=accounts to collect every recent post instead."
            )
            return
        source.logger.info(f"Loaded {len(keywords)} keywords from {source.KEYWORDS_FILE}.")

    # Pre-load Whisper model once at startup
    source.get_whisper_model(source.logger)

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(f"Starting scraping run {run_timestamp} for TikTok videos in '{mode}' mode...")

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    # Sequential, like tel-scraper.py: TikTok blocks aggressively on bursts and
    # a thread pool would buy throughput at the cost of getting the run banned.
    for index, account in enumerate(accounts, start=1):
        source.logger.info(f"[{index}/{len(accounts)}] Scraping '@{account}'...")
        try:
            source.scrape_account(account, lsh, hash_by_id, keywords=keywords)
        except Exception as e:
            source.logger.error(f"Unexpected failure on '@{account}': {type(e).__name__}: {e}")
        if index < len(accounts):
            time.sleep(random.uniform(*source.ACCOUNT_DELAY_RANGE))

    source.logger.info("Scraping for all TikTok accounts is done.")
