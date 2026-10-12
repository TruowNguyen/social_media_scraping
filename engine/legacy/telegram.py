"""Legacy telegram watchlist orchestration; preserves CLI behavior."""
import random
import datetime
import asyncio
from src.collectors.telegram import collector as source

async def run():
    if not source.TELEGRAM_API_ID or not source.TELEGRAM_API_HASH:
        source.logger.error(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set. Create an "
            "application at https://my.telegram.org, then put both values in .env."
        )
        return

    try:
        api_id = int(source.TELEGRAM_API_ID)
    except (TypeError, ValueError):
        source.logger.error(f"TELEGRAM_API_ID must be an integer, got '{source.TELEGRAM_API_ID}'.")
        return

    channels = source.load_trusted_channels(source.CHANNELS_FILE)
    if not channels:
        source.logger.error(f"No channels found in {source.CHANNELS_FILE}.")
        return

    source.logger.info(f"Loaded {len(channels)} trusted channels from {source.CHANNELS_FILE}.")

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source.logger.info(
        f"Starting scraping run {run_timestamp} for Telegram "
        f"(window: last {source.MAX_PAST_MINUTES} minute(s))..."
    )

    lsh, hash_by_id = source.dedup_utils.load_lsh()

    client = source.TelegramClient(source.TELEGRAM_SESSION_NAME, api_id, source.TELEGRAM_API_HASH)
    client.flood_sleep_threshold = source.FLOOD_SLEEP_THRESHOLD

    async with client:
        # A single MTProto session gains nothing from parallel requests and
        # concurrent reads raise the flood-ban risk for the account, so
        # channels are walked sequentially with a jittered pause between them.
        for index, channel in enumerate(channels, start=1):
            source.logger.info(f"[{index}/{len(channels)}] Scraping '@{channel}'...")
            try:
                await source.scrape_channel(client, channel, lsh, hash_by_id)
            except Exception as e:
                source.logger.error(f"Unexpected failure on '@{channel}': {type(e).__name__}: {e}")

            if index < len(channels):
                await asyncio.sleep(random.uniform(*source.CHANNEL_DELAY_RANGE))

    source.logger.info(f"Scraping run {run_timestamp} complete.")

def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        source.logger.info("Interrupted by user. Partial results already written are kept.")
