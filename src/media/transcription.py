"""Legacy transcription behavior extracted without changing data policies."""

import logging
import os
import tempfile
import threading
import time
from src.config.env import env_str
from src.resilience.retry import with_retry

WHISPER_TASK = env_str("WHISPER_TASK", "translate").strip().lower()

if WHISPER_TASK not in {"translate", "transcribe"}:
    WHISPER_TASK = "translate"

WHISPER_MODEL_SIZE = env_str("WHISPER_MODEL_SIZE", "small")

_whisper_model = None

_model_lock = threading.Lock()

_WHISPER_FAILURE_LIMIT = 3

_whisper_failure_count = 0

_whisper_disabled = False

_whisper_state_lock = threading.Lock()

_ENV_FAILURE_MARKERS = ("libcublas", "libcudnn", "cannot be loaded", "cuda")

def _whisper_logger(logger):
    return logger if logger is not None else logging.getLogger(__name__)

def get_whisper_model(logger=None):
    """Lazily loads and caches the faster-whisper model."""
    global _whisper_model
    log = _whisper_logger(logger)
    with _model_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                log.info(f"Initializing faster-whisper model ({WHISPER_MODEL_SIZE})... (this may take a moment on first run)")
                try:
                    _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cuda", compute_type="float16")
                    log.info(f"faster-whisper model ({WHISPER_MODEL_SIZE}) successfully loaded and ready (GPU/CUDA).")
                except Exception as gpu_err:
                    log.warning(
                        f"Could not initialize Whisper on GPU ({str(gpu_err).splitlines()[0]}). "
                        "Falling back to CPU (int8)."
                    )
                    _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
                    log.info(f"faster-whisper model ({WHISPER_MODEL_SIZE}) successfully loaded and ready (CPU fallback).")
            except ImportError:
                log.warning("faster-whisper is not installed. Falling back strictly to subtitle scraping.")
                _whisper_model = False
    return _whisper_model

def _record_whisper_env_failure(error_text: str, logger=None) -> bool:
    """Tracks consecutive environment-level Whisper failures (missing CUDA
    libs, etc). Returns True once the failure limit is hit and Whisper has
    been disabled for the rest of this run."""
    global _whisper_failure_count, _whisper_disabled
    lowered = error_text.lower()
    if not any(marker in lowered for marker in _ENV_FAILURE_MARKERS):
        return False

    with _whisper_state_lock:
        if _whisper_disabled:
            return True
        _whisper_failure_count += 1
        if _whisper_failure_count >= _WHISPER_FAILURE_LIMIT:
            _whisper_disabled = True
            _whisper_logger(logger).error(
                f"Whisper failed {_whisper_failure_count} times in a row with an "
                f"environment/library error ('{error_text}'). Disabling audio "
                "transcription for the rest of this run and falling back to "
                "subtitle-only mode. Fix: use CPU transcription or follow "
                "faster-whisper's GPU setup for compatible CUDA/cuDNN libraries "
                "and library paths before the next run (see README.md)."
            )
            return True
    return False

@with_retry(max_attempts=2, base_delay=3.0, exceptions=(Exception,))
def _download_audio(media_url: str, out_template: str, extra_opts: dict = None) -> None:
    import yt_dlp

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'socket_timeout': 25,
        'retries': 3,
        'fragment_retries': 3,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    ydl_opts.update(extra_opts or {})
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([media_url])

def transcribe_audio(media_url: str, media_id: str, duration: int = 0,
                     max_duration: int = 0, extra_opts: dict = None, logger=None) -> str:
    """
    Downloads a post's audio track and returns an English transcript, or None.

    ``max_duration`` (seconds, 0 disables) skips anything longer, so a 24/7
    live broadcast can never stall a run on an unbounded download.
    """
    log = _whisper_logger(logger)
    if max_duration and duration and duration > max_duration:
        log.info(f"Skipping audio download for {media_id}: duration ({duration}s) exceeds {max_duration}s cap.")
        return None

    model = get_whisper_model(logger)
    if not model or _whisper_disabled:
        return None

    log.info(f"Downloading lightweight audio for {media_id}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, f"{media_id}.%(ext)s")

        try:
            _download_audio(media_url, out_template, extra_opts)

            audio_file = os.path.join(tmpdir, f"{media_id}.mp3")
            if not os.path.exists(audio_file):
                files = os.listdir(tmpdir)
                if not files:
                    return None
                audio_file = os.path.join(tmpdir, files[0])

            log.info(f"Transcribing audio for {media_id} with Whisper...")
            start_t = time.time()
            # task="translate" makes Whisper auto-detect the spoken language
            # and translate it directly to English, instead of transcribing
            # verbatim in whatever language is detected. Combined with a
            # multilingual model (not "*.en"), this is what actually handles
            # non-English source audio correctly.
            segments, info = model.transcribe(audio_file, beam_size=2, task=WHISPER_TASK)
            transcript_text = " ".join([seg.text.strip() for seg in segments])
            elapsed = time.time() - start_t
            log.info(
                f"Finished transcribing {media_id} in {elapsed:.1f}s "
                f"({len(transcript_text.split())} words, detected source language: {info.language})."
            )
            return transcript_text if transcript_text.strip() else None

        except Exception as e:
            err_text = str(e).splitlines()[0] if str(e) else type(e).__name__
            log.warning(f"Audio transcription failed for {media_id}: {err_text}")
            _record_whisper_env_failure(err_text, logger)
            return None
