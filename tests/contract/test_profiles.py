import tempfile
import os
import json
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from src.browser.profiles import PROJECT_ROOT, ProfileInUse, locked_profile, profile_path, prepare_browser_path


class BrowserProfiles(unittest.TestCase):
    def test_default_paths_do_not_depend_on_working_directory(self):
        with patch("pathlib.Path.cwd", return_value=Path("elsewhere")), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(profile_path("facebook"), PROJECT_ROOT / "sessions/browser/facebook")
            prepare_browser_path()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(PROJECT_ROOT / ".venv/playwright-browsers"))

    def test_browser_install_override_is_preserved(self):
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": "custom-browsers"}):
            prepare_browser_path()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], "custom-browsers")

    def test_exclusive_lock_and_release_after_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                with locked_profile("facebook", root) as path:
                    self.assertTrue(path.is_dir())
                    with self.assertRaises(ProfileInUse):
                        with locked_profile("facebook", root):
                            self.fail("Concurrent profile acquired")
                    with locked_profile("tiktok", root) as other:
                        self.assertNotEqual(path, other)
                    raise RuntimeError("simulated failure")
            with locked_profile("facebook", root):
                pass
            self.assertFalse((root / "facebook.lock").exists())

    def test_unknown_platform_cannot_escape_profile_root(self):
        with self.assertRaises(ValueError):
            profile_path("../../Chrome")

    def test_dead_legacy_owner_recovered_without_touching_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = profile_path('facebook', root)
            profile.mkdir()
            cookie = profile / 'session-marker'
            cookie.write_text('preserve')
            lock = root / 'facebook.lock'
            lock.write_text(json.dumps({'pid': 999999, 'platform': 'facebook'}))
            with patch('src.browser.profiles._pid_alive', return_value=False), patch(
                    'src.browser.profiles._profile_browser_running', return_value=False):
                with locked_profile('facebook', root):
                    self.assertEqual(json.loads(lock.read_text())['pid'], os.getpid())
            self.assertEqual(cookie.read_text(), 'preserve')
            self.assertFalse(lock.exists())

    def test_legacy_live_owner_or_orphan_browser_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'facebook.lock'
            value = json.dumps({'pid': os.getpid(), 'platform': 'facebook'})
            lock.write_text(value)
            with self.assertRaises(ProfileInUse):
                with locked_profile('facebook', directory):
                    self.fail('Live owner reclaimed')
            with patch('src.browser.profiles._pid_alive', return_value=False), patch(
                    'src.browser.profiles._profile_browser_running', return_value=True):
                with self.assertRaises(ProfileInUse):
                    with locked_profile('facebook', directory):
                        self.fail('Orphan browser reclaimed')
            self.assertEqual(lock.read_text(), value)

    def test_unknown_owner_is_not_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'facebook.lock'
            for value in ('bad json', '{}', '[]', '{"pid":null}'):
                lock.write_text(value)
                with self.assertRaises(ProfileInUse):
                    with locked_profile('facebook', directory):
                        self.fail('Unverified owner reclaimed')
                self.assertEqual(lock.read_text(), value)

    def test_process_crash_releases_guard_and_recovery_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            code = "import sys; from src.browser.profiles import locked_profile; ctx=locked_profile('facebook',sys.argv[1]); ctx.__enter__(); print('LOCKED',flush=True); sys.stdin.read()"
            child = subprocess.Popen([sys.executable, '-c', code, directory],
                cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'LOCKED')
                with self.assertRaises(ProfileInUse):
                    with locked_profile('facebook', directory):
                        self.fail('Concurrent process acquired profile')
                child.kill()
                child.communicate(timeout=10)
                with patch('src.browser.profiles._profile_browser_running', return_value=False):
                    with locked_profile('facebook', directory):
                        self.assertTrue((Path(directory) / 'facebook.lock').exists())
                self.assertFalse((Path(directory) / 'facebook.lock').exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=10)
