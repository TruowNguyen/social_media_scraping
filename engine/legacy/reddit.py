"""Legacy reddit watchlist orchestration; preserves CLI behavior."""
import os
import time
import random
import datetime
from src.collectors.reddit import collector as source

def main():
    if not source.REDDIT_CLIENT_ID or not source.REDDIT_CLIENT_SECRET:
        source.logger.error(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set. Self-service "
            "app registration is closed since Reddit's Responsible Builder Policy "
            "(Nov 2025); request Data API access via the form on Reddit's Data "
            "API wiki, then put both values in .env."
        )
        return

    mode = source.get_scrape_mode(source.logger, prefix="RD")

    keywords = []
    if mode == "keyword":
        if not os.path.exists(source.KEYWORDS_FILE):
            source.logger.error(f"File '{source.KEYWORDS_FILE}' not found.")
            return

        with open(source.KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        if not keywords:
            source.logger.error(f"No keywords found in '{source.KEYWORDS_FILE}'.")
            return

    subreddits = source.load_trusted_subreddits(source.SUBREDDITS_FILE)
    source.logger.info(f"Loaded {len(subreddits)} trusted subreddits from {source.SUBREDDITS_FILE}.")

    # read_only tells praw to authenticate with the app credentials alone
    # (client-credentials grant): no user password, no write scope.
    reddit = source.praw.Reddit(
        client_id=source.REDDIT_CLIENT_ID,
        client_secret=source.REDDIT_CLIENT_SECRET,
        user_agent=source.REDDIT_USER_AGENT,
    )
    reddit.read_only = True

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(f"Starting scraping run {run_timestamp} for Reddit submissions in '{mode}' mode...")

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    if mode == "accounts":
        for index, subreddit_name in enumerate(subreddits, start=1):
            try:
                source.scrape_subreddit(reddit, subreddit_name, lsh, hash_by_id)
            except Exception as e:
                source.logger.error(f"Error scraping 'r/{subreddit_name}': {str(e).splitlines()[0]}")
            if index < len(subreddits):
                time.sleep(random.uniform(*source.SEARCH_DELAY_RANGE))
        source.logger.info("Scraping for all trusted subreddits is done.")
        return

    for index, keyword in enumerate(keywords, start=1):
        try:
            source.search_and_scrape_reddit(reddit, keyword, subreddits, lsh, hash_by_id)
        except Exception as e:
            source.logger.error(f"Error executing search/scrape for keyword '{keyword}': {str(e).splitlines()[0]}")
        if index < len(keywords):
            time.sleep(random.uniform(*source.SEARCH_DELAY_RANGE))

    source.logger.info("Scraping for all Reddit keywords is done.")
