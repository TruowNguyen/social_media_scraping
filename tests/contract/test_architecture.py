"""Checks the structural boundary and compatibility state ownership."""
import ast
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class Architecture(unittest.TestCase):
    def test_src_has_no_engine_or_root_facade_dependency(self):
        for path in (ROOT / "src").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertNotIn(name.split(".")[0], {"engine", "pipeline_utils", "dedup_utils"}, str(path))

    def test_collectors_share_dedup_state_owner(self):
        from src.filtering import dedup
        with patch.object(dedup, "DB_PATH", "isolated-test.db"):
            for platform in ("youtube", "x", "telegram", "reddit", "tiktok", "truthsocial"):
                module = importlib.import_module(f"src.collectors.{platform}.collector")
                self.assertIs(module.dedup_utils, dedup)
                self.assertEqual(module.dedup_utils.DB_PATH, "isolated-test.db")

    def test_no_root_python_files_and_shared_analysis_owner(self):
        self.assertEqual(list(ROOT.glob("*.py")), [])
        from src.analysis.legacy_text import analyze_text
        for platform in ("youtube", "x", "telegram", "reddit", "tiktok", "truthsocial"):
            module = importlib.import_module(f"src.collectors.{platform}.collector")
            self.assertIs(module.analyze_text, analyze_text)

    def test_schema_has_no_model_dependency(self):
        path = ROOT / "src/domain/legacy_schema.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").startswith(("src.analysis", "src.media", "transformers", "torch")))

    def test_manual_dispatch_calls_only_requested_runtime(self):
        from engine import runtime
        with patch.object(runtime.importlib, "import_module") as load:
            runtime.main(["--platform", "tiktok"])
            load.assert_called_once_with("engine.legacy.tiktok")
            load.return_value.main.assert_called_once_with()

    def test_collectors_import_without_running_main_or_loading_models(self):
        from src.analysis import legacy_text
        from src.media import transcription
        with patch.object(legacy_text, "_load_asset_nli_model", side_effect=AssertionError("import started NLI")), patch.object(transcription, "get_whisper_model", side_effect=AssertionError("import started ASR")):
            for platform in ("youtube", "x", "telegram", "reddit", "tiktok", "truthsocial"):
                module = importlib.import_module(f"src.collectors.{platform}.collector")
                self.assertFalse(hasattr(module, "main"))
                importlib.import_module(f"engine.legacy.{platform}")
