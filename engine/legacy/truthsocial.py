"""Legacy truthsocial watchlist orchestration; preserves CLI behavior."""
import time
import random
import datetime
import urllib
from src.collectors.truthsocial import collector as source

def main():
    if not source.TRUTHSOCIAL_TOKEN and not (source.TRUTHSOCIAL_USERNAME and source.TRUTHSOCIAL_PASSWORD):
        source.logger.error(
            "TRUTHSOCIAL_USERNAME and TRUTHSOCIAL_PASSWORD must be set in .env "
            "(or TRUTHSOCIAL_TOKEN with an existing bearer token)."
        )
        return

    accounts = source.load_trusted_accounts(source.ACCOUNTS_FILE)
    if not accounts:
        source.logger.error(f"No accounts found in {source.ACCOUNTS_FILE}.")
        return

    source.logger.info(f"Loaded {len(accounts)} trusted accounts from {source.ACCOUNTS_FILE}.")

    mode = source.get_scrape_mode(source.logger, prefix="TS")
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

    try:
        token = source.login()
    except urllib.error.HTTPError as e:
        source.logger.error(f"Login failed: HTTP {e.code}. Check TRUTHSOCIAL_USERNAME/TRUTHSOCIAL_PASSWORD.")
        return
    except Exception as e:
        source.logger.error(f"Login failed: {type(e).__name__}: {e}")
        return

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(f"Starting scraping run {run_timestamp} for Truth Social posts in '{mode}' mode...")

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    # Sequential for the same reason as tel-scraper.py: one authenticated
    # session gains nothing from parallel requests and concurrent reads only
    # raise the odds of the account being rate limited.
    for index, account in enumerate(accounts, start=1):
        source.logger.info(f"[{index}/{len(accounts)}] Scraping '@{account}'...")
        try:
            source.scrape_account(account, token, lsh, hash_by_id, keywords=keywords)
        except Exception as e:
            source.logger.error(f"Unexpected failure on '@{account}': {type(e).__name__}: {e}")
        if index < len(accounts):
            time.sleep(random.uniform(*source.ACCOUNT_DELAY_RANGE))

    source.logger.info("Scraping for all Truth Social accounts is done.")
