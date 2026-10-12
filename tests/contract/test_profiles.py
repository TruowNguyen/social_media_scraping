import tempfile
import os
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
