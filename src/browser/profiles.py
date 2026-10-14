"""Dedicated project profiles and an exclusive cross-platform process lock."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
from src.config.env import env_str
from src.storage.file_lock import file_lock

PLATFORMS = ("facebook", "tiktok", "threads")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "sessions" / "browser"


class ProfileInUse(RuntimeError):
    """Another job holds the profile; no second browser may open it."""


def profile_path(platform, root=None):
    if platform not in PLATFORMS:
        raise ValueError("Expected facebook, tiktok or threads")
    return (DEFAULT_PROFILE_ROOT if root is None else Path(root)) / platform


def _pid_alive(pid):
    """Unknown/permission-denied owners are treated as alive, never reclaimed."""
    if type(pid) is not int or pid <= 0:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no PID
        try:
            code=wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value==259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _profile_browser_running(path):
    """An orphan browser can outlive Python. Reclaim only after a reliable scan."""
    target = str(path.resolve()).replace('\\', '/').casefold()
    try:
        if os.name == 'nt':
            env = dict(os.environ, SOCIAL_LISTENING_PROFILE_CHECK=target)
            script = "$ErrorActionPreference='Stop'; $target=$env:SOCIAL_LISTENING_PROFILE_CHECK; $found=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Replace('\\','/').ToLowerInvariant().Contains($target) }; if ($found) { 'BUSY' } else { 'FREE' }"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                env=env, capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode != 0 or result.stdout.strip() != 'FREE'
        result = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True, timeout=10)
        return result.returncode != 0 or any(target in line.replace('\\', '/').casefold()
            for line in result.stdout.splitlines())
    except (OSError, subprocess.TimeoutExpired):
        return True


@contextmanager
def locked_profile(platform, root=None):
    path = profile_path(platform, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    # The OS releases this guard on process death. Keep its inode/file permanent:
    # unlinking an OS lock allows competing processes to lock different files.
    guard = file_lock(path.with_suffix('.guard'), timeout=0)
    try:
        guard.__enter__()
    except ValueError:
        raise ProfileInUse(f"Profile {platform} is in use; close its job before retrying.") from None
    owned = False
    try:
        if lock.exists():
            try:
                owner = json.loads(lock.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise ProfileInUse(f"Profile {platform} has an unverified lock.") from None
            if not isinstance(owner, dict) or _pid_alive(owner.get('pid')) or _profile_browser_running(path):
                raise ProfileInUse(f"Profile {platform} is in use; close its job before retrying.")
            lock.unlink()  # Only dead-owner metadata; never delete the browser profile.
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ProfileInUse(f"Profile {platform} is in use; close its job before retrying.") from None
        owned = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "platform": platform}, stream)
        path.mkdir(parents=True, exist_ok=True)
        yield path
    finally:
        try:
            if owned:
                lock.unlink(missing_ok=True)
        finally:
            guard.__exit__(None, None, None)


def prepare_browser_path():
    """Use the project-local install unless the operator provides an override."""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = env_str(
        "PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".venv" / "playwright-browsers"))
