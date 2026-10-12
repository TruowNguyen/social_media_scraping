"""Legacy x watchlist orchestration; preserves CLI behavior."""
import os
import time
import random
import datetime
from src.collectors.x import collector as source

def _scrape_account_list(accounts: list, lsh, hash_by_id) -> list:
    """Keep processing accounts, returning only those needing a source retry."""
    deferred = []
    for index, account in enumerate(accounts, start=1):
        try:
            _, blocked = source.scrape_account_tweets(account, lsh, hash_by_id)
            if blocked:
                deferred.append(account)
        except Exception as e:
            source.logger.error(f"Error scraping account '@{account}': {str(e).splitlines()[0]}")
        if index < len(accounts):
            delay = (source.ACCOUNT_DELAY_BLOCKED_RANGE if time.monotonic() < source._syndication_cooldown_until
                     else source.ACCOUNT_DELAY_RANGE)
            time.sleep(random.uniform(*delay))
    return deferred

def main():
    accounts_file = os.path.join(source.SOURCES_DIR, "twtr-accounts.txt")
    trusted_accounts = source.load_trusted_accounts(accounts_file)
    source.logger.info(f"Loaded {len(trusted_accounts)} trusted accounts from {accounts_file}.")

    mode = source.get_scrape_mode(source.logger, prefix="X")

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(f"Starting scraping run {run_timestamp} for X (Twitter) in '{mode}' mode...")

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    if mode == "accounts":
        deferred = _scrape_account_list(trusted_accounts, lsh, hash_by_id)
        for retry_pass in range(source.SYNDICATION_RETRY_PASSES):
            if not deferred:
                break
            wait = max(0.0, source._syndication_cooldown_until - time.monotonic())
            source.logger.info(f"Retry pass {retry_pass + 1}: {len(deferred)} account(s), waiting {wait:.1f}s.")
            time.sleep(wait)
            deferred = _scrape_account_list(deferred, lsh, hash_by_id)
        if deferred:
            source.logger.warning(f"Syndication still unavailable for {len(deferred)} account(s); fallback results retained.")
        source.logger.info("Scraping for all trusted accounts is done.")
        return

    keyword_file = os.path.join(source.KEYWORDS_DIR, "twtr-keywords.txt")
    if not os.path.exists(keyword_file):
        source.logger.error(f"File '{keyword_file}' not found.")
        return

    with open(keyword_file, 'r', encoding='utf-8') as f:
        keywords = [line.strip() for line in f if line.strip()]

    if not keywords:
        source.logger.error(f"No keywords found in {keyword_file}.")
        return

    for keyword in keywords:
        try:
            source.search_and_scrape_tweets(keyword, trusted_accounts, lsh, hash_by_id)
        except Exception as e:
            source.logger.error(f"Error executing search/scrape for keyword '{keyword}': {str(e).splitlines()[0]}")

    source.logger.info("Scraping for all keywords is done.")
