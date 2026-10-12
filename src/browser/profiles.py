"""Dedicated project profiles and an exclusive cross-platform process lock."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from src.config.env import env_str

PLATFORMS = ("facebook", "tiktok", "threads")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "sessions" / "browser"


class ProfileInUse(RuntimeError):
    """Another job holds the profile; no second browser may open it."""


def profile_path(platform, root=None):
    if platform not in PLATFORMS:
        raise ValueError("Expected facebook, tiktok or threads")
    return (DEFAULT_PROFILE_ROOT if root is None else Path(root)) / platform


@contextmanager
def locked_profile(platform, root=None):
    path = profile_path(platform, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ProfileInUse(f"Profile {platform} is in use; close its job before retrying.") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "platform": platform}, stream)
        path.mkdir(parents=True, exist_ok=True)
        yield path
    finally:
        lock.unlink(missing_ok=True)


def prepare_browser_path():
    """Use the project-local install unless the operator provides an override."""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = env_str(
        "PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".venv" / "playwright-browsers"))
