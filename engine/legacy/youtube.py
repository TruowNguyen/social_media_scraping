"""Legacy youtube watchlist orchestration; preserves CLI behavior."""
import os
import datetime
from src.collectors.youtube import collector as source

def main():
    channels_file = os.path.join(source.SOURCES_DIR, "yt-channels.txt")
    trusted_channels = source.load_trusted_channels(channels_file)
    source.logger.info(f"Loaded {len(trusted_channels)} trusted channels from {channels_file}.")

    mode = source.get_scrape_mode(source.logger, prefix="YT")

    # Pre-load Whisper model once at startup
    source.get_whisper_model(source.logger)

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(f"Starting scraping run {run_timestamp} for YouTube videos in '{mode}' mode...")

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    if mode == "accounts":
        for channel in trusted_channels:
            try:
                source.scrape_channel_videos(channel, lsh, hash_by_id)
            except Exception as e:
                source.logger.error(f"Error scraping channel '{channel}': {str(e).splitlines()[0]}")
        source.logger.info("Scraping for all trusted channels is done.")
        return

    keyword_file = os.path.join(source.KEYWORDS_DIR, "yt-keywords.txt")
    if not os.path.exists(keyword_file):
        source.logger.error(f"File '{keyword_file}' not found.")
        return

    with open(keyword_file, 'r', encoding='utf-8') as f:
        keywords = [line.strip() for line in f if line.strip()]

    if not keywords:
        source.logger.error(f"No keywords found in '{keyword_file}'.")
        return

    for keyword in keywords:
        try:
            source.search_and_scrape_youtube(keyword, trusted_channels, lsh, hash_by_id)
        except Exception as e:
            source.logger.error(f"Error executing search/scrape for keyword '{keyword}': {str(e).splitlines()[0]}")

    source.logger.info("Scraping for all YouTube keywords is done.")
