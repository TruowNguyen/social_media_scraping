"""Bounded single-item yt-dlp metadata bridge; never ASR or media download."""
import multiprocessing
from src.acquisition.browser_adapters import set_publication
from src.acquisition.models import AdapterError, AccessProbeResult, FetchResult
from src.acquisition.identity import source_references


class QuietLogger:
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


def metadata_worker(connection, url, seconds):
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(dict(quiet=True, no_warnings=True, skip_download=True, noplaylist=True, retries=0, extractor_retries=0, socket_timeout=min(15, seconds), logger=QuietLogger())) as downloader:
            info = downloader.extract_info(url, download=False)
        connection.send({key: info.get(key) for key in ("id", "title", "description", "channel_id", "uploader_id", "channel", "channel_url", "timestamp", "upload_date", "view_count", "like_count", "comment_count", "thumbnail")})
    except Exception:
        connection.send({"error": "YOUTUBE_METADATA_UNAVAILABLE"})
    finally:
        connection.close()


def fetch_metadata(url, deadline):
    deadline.check()
    process_context = multiprocessing.get_context("spawn")
    reader, writer = process_context.Pipe(duplex=False)
    worker = process_context.Process(target=metadata_worker, args=(writer, url, deadline.remaining()))
    worker.start()
    writer.close()
    try:
        if not reader.poll(deadline.remaining()):
            raise AdapterError("BUDGET_EXHAUSTED", "YOUTUBE_FETCH_TIMEOUT")
        result = reader.recv()
        if result.get("error"):
            raise AdapterError("SOURCE_UNAVAILABLE", result["error"])
        return result
    except EOFError:
        raise AdapterError("SOURCE_UNAVAILABLE", "YOUTUBE_WORKER_FAILED") from None
    finally:
        reader.close()
        worker.join(timeout=min(1, deadline.remaining()))
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
        if not worker.is_alive():
            worker.close()


class YouTubeItemAdapter:
    def __init__(self, fetcher=fetch_metadata):
        self.fetcher = fetcher

    def probe_access(self, source):
        return AccessProbeResult("SOURCE_UNAVAILABLE", "YOUTUBE_REQUIRES_ITEM_PROBE")

    def discover(self, request):
        raise AdapterError("SKIPPED", "YOUTUBE_ITEM_BRIDGE_ONLY")

    def fetch_item(self, candidate, context):
        if candidate.prefilter_decision not in {"PASS", "REVIEW"}:
            raise ValueError("Fetch requires PASS or REVIEW")
        info = self.fetcher(candidate.canonical_url, context.deadline)
        refs = source_references(context.source)
        if not (set(filter(None, (info.get("channel_id"), info.get("uploader_id")))) & refs):
            raise AdapterError("ACCESS_DENIED", "YOUTUBE_CHANNEL_MISMATCH")
        if info.get("id") != candidate.platform_item_id:
            raise AdapterError("EXTRACTION_FAILED", "YOUTUBE_ITEM_MISMATCH")
        candidate.origin_source_ref = info.get("channel_id") or info.get("uploader_id")
        candidate.title, candidate.raw_text = info.get("title"), info.get("description") or None
        candidate.author.update(platform_author_id=info.get("channel_id"), display_name=info.get("channel"), profile_url=info.get("channel_url"))
        for key, native in {"views": "view_count", "likes": "like_count", "comments": "comment_count"}.items():
            value = info.get(native)
            candidate.engagement[key] = value if type(value) is int and value >= 0 else None
        set_publication(candidate, epoch=info.get("timestamp"))
        if not candidate.published_at and info.get("upload_date"):
            from datetime import datetime
            try:
                candidate.publication_date = datetime.strptime(info["upload_date"], "%Y%m%d").date().isoformat()
                candidate.publication_precision = "DATE_ONLY"
            except ValueError:
                pass
        candidate.window_status = context.window.status(candidate.published_at, candidate.publication_precision)
        candidate.content_type = "VIDEO"
        candidate.extraction_status = "FETCHED" if candidate.raw_text else "METADATA_ONLY"
        candidate.evidence_provenance.append("YOUTUBE_YTDLP_METADATA")
        candidate.missing_data_reasons = ["TRANSCRIPT_NOT_REQUESTED"]
        if not candidate.published_at:
            candidate.missing_data_reasons.append("PUBLICATION_TIME_UNRESOLVED")
        return FetchResult(candidate)
