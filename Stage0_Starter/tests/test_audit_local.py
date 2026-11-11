"""Unit tests requiring no Blender, AI models, internet, or third-party packages."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_local import scan_models  # noqa: E402


class ReadOnlyScannerTests(unittest.TestCase):
    def test_no_roots_does_not_scan_anything(self) -> None:
        result = scan_models([])
        self.assertEqual(result["examined_files"], 0)
        self.assertEqual(result["models"], [])

    def test_detects_file_without_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.safetensors"
            path.write_bytes(b"metadata-only-test")
            result = scan_models([Path(temp)])
            self.assertEqual(len(result["models"]), 1)
            self.assertEqual(result["models"][0]["model_family"], "unknown")
            self.assertEqual(result["models"][0]["bytes"], len(b"metadata-only-test"))

    def test_excludes_git_and_respects_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / ".git").mkdir()
            (path / ".git" / "hidden.ckpt").write_bytes(b"not-a-model")
            for i in range(3):
                (path / f"{i}.pt").write_bytes(b"placeholder-contents-test-only")
            result = scan_models([path], max_files=2)
            self.assertTrue(result["max_files_exceeded"])
            self.assertEqual(len(result["models"]), 2)


if __name__ == "__main__":
    unittest.main()
