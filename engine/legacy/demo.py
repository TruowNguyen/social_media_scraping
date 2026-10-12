"""Run the shared pipeline on synthetic posts without network or credentials."""

import datetime
import json
import os
import tempfile
from pathlib import Path

# The demo always runs without model downloads or local credential files.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["SENTIMENT_MODEL"] = "none"
os.environ["MULTILINGUAL_SENTIMENT_MODEL"] = "none"
os.environ["ASSET_NLI_MODEL"] = "none"

from src.filtering import dedup as dedup_utils
from src.storage.record_file import RecordFile
from src.analysis.legacy_text import analyze_text
from src.domain.legacy_schema import build_quality
from src.domain.language import detect_language


def main():
    samples = [
        ("X", "1800000000000000000", "tweet",
         "https://x.com/demo_news/status/1800000000000000000",
         "Oil prices rose as traders reviewed the latest supply report."),
        ("Telegram", "1", "message", "https://t.me/demo_news/1",
         "Oil prices rose as traders reviewed the latest supply report."),
        ("Telegram", "2", "message", "https://t.me/demo_news/2",
         "قیمت تتر امروز بالا رفت و USDT گران شد. طلا هم رشد کرد."),
    ]
    original_db = dedup_utils.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as directory:
            dedup_utils.DB_PATH = str(Path(directory) / "dedup-index.db")
            lsh, hash_by_id = dedup_utils.load_lsh()
            output = RecordFile(str(Path(directory) / "synthetic-records.json"))
            for platform, native_id, content_type, url, text in samples:
                record_id = f"{platform}_demo_news_{native_id}"
                lang, _ = detect_language(text)
                sentiment, assets = analyze_text(text, lang)
                record = {
                    "record_id": record_id,
                    "Source": {
                        "platform": platform, "Source_type": "Social_media",
                        "Source_name": "Synthetic Demo", "Source_id": native_id,
                        "url": url, "author_name": "Synthetic Demo", "author_id": "demo_news",
                    },
                    "Content": {
                        "Content_type": content_type, "title": "N/A", "raw_text": text,
                        "Clean_text": "", "language": lang,
                    },
                    "time_stamps": {
                        "published_at": "2026-01-01 10:00:00 UTC",
                        "collected_at": "2026-01-01 11:00:00 UTC", "updated_at": None,
                    },
                    "asset_mention": assets,
                    "sentiment": sentiment,
                    "Engagement": {"Views": 0, "likes": 0, "Comments": 0, "shares": 0},
                    "media": {"has_media": False, "media_type": None, "media_url": None},
                    "deduplication": dedup_utils.check_and_register(record_id, text, lsh, hash_by_id),
                }
                record["quality"] = build_quality(record)
                output.add(record, datetime.datetime(2026, 1, 1, 10, tzinfo=datetime.timezone.utc))
            output.save()
            records = json.loads(Path(output.path).read_text(encoding="utf-8"))
    finally:
        dedup_utils.DB_PATH = original_db

    assert len(records) == 3
    assert not records[0]["deduplication"]["is_duplicate"]
    assert records[1]["deduplication"]["original_record_id"] == records[0]["record_id"]
    assert records[2]["Content"]["language"] == "fa"
    assert {"USDT", "XAU"} <= {asset["Symbol"] for asset in records[2]["asset_mention"]}
    assert all(record["quality"]["is_complete"] for record in records)
    assert all(record["sentiment"]["label"] is None for record in records)
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
