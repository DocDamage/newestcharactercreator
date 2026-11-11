"""Portable GUI entrypoint diagnostics, independent of the Qt event loop where possible."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ucc.desktop.__main__ import _result_file, main


class DiagnosticFileContract(unittest.TestCase):
    def test_diagnostic_writes_once_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "diag.json"
            _result_file(target, {"status": "TEST"})
            self.assertEqual(json.loads(target.read_text())["status"], "TEST")
            with self.assertRaisesRegex(RuntimeError, "must not exist"):
                _result_file(target, {"status": "REPLACED"})
            self.assertEqual(json.loads(target.read_text())["status"], "TEST")

    def test_refuses_nonexistent_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "parent"):
                _result_file(Path(directory) / "missing" / "test.json", {"status": "TEST"})

    def test_refuses_symlink_destination_if_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = Path(directory) / "existing.txt"
            anchor.write_text("do not change", encoding="utf-8")
            target = Path(directory) / "diag.json"
            try:
                target.symlink_to(anchor)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable on this host")
            with self.assertRaises(RuntimeError):
                _result_file(target, {"status": "TEST"})
            self.assertEqual(anchor.read_text(encoding="utf-8"), "do not change")


@unittest.skipUnless(os.getenv("UCC_REQUIRE_QT") == "1", "Qt required only in packaged/desktop CI")
class RealQtSelfTest(unittest.TestCase):
    def test_real_3_panel_editor_and_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "self-test.json"
            self.assertEqual(main(["--self-test", "--self-test-report", str(target)]), 0)
            status = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "SELF_TEST_OK")
            self.assertEqual(status["checks"], ["PROJECT_SAVE_REOPEN_OK", "QT_WIDGETS_OK"])
            self.assertNotIn("source_path", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
