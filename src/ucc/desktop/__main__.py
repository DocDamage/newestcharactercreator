"""Launch UCC's desktop workstation or verify its frozen Windows executable.

Self-test performs a real local Qt/widget + versioned project roundtrip; it does
not generate Blender meshes or establish game-engine compatibility.  No bundled
character data or user paths are read during the diagnostic.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def _result_file(path: Path | None, result: dict) -> None:
    """Write a minimal diagnostic report; never overwrite a symlink or arbitrary data."""
    if path is None:
        if sys.stdout is not None:
            print(json.dumps(result, sort_keys=True))
        return
    if path.is_symlink() or path.exists():
        raise RuntimeError("Diagnostic report destination must not exist or be a symlink")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeError("Diagnostic report parent must be an existing normal folder")
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(result, output, sort_keys=True, indent=2)
            output.write("\n")
    except OSError:
        raise


def _self_test(report: Path | None) -> int:
    """Execute real but non-destructive Qt and storage checks in temp files."""
    result: dict[str, object] = {"status": "SELF_TEST_FAILED", "version": "0.1.0-alpha", "checks": []}
    try:
        from PySide6.QtWidgets import QApplication
        from ucc.desktop.controller import DesktopController
        from ucc.desktop.window import MainWindow

        app = QApplication.instance() or QApplication(["ucc-desktop-self-test"])
        with tempfile.TemporaryDirectory(prefix="ucc-alpha-health-") as temp:
            project_dir = Path(temp) / "private_test_project"
            controller = DesktopController()
            controller.create(project_dir, "Diagnostic Character")
            controller.set_morph("height", 0.75)
            controller.save()
            reopened = DesktopController()
            reopened.open(project_dir)
            loaded = reopened.view()
            if loaded.name != "Diagnostic Character" or dict(loaded.morphs)["height"] != 0.75:
                raise RuntimeError("Saved character project did not reopen with correct metadata")
            if loaded.geometry_state != "not_generated":
                raise RuntimeError("Diagnostic unexpectedly reported verified mesh geometry")
            result["checks"].append("PROJECT_SAVE_REOPEN_OK")
            window = MainWindow(reopened)
            try:
                if window.tabs.count() != 3 or window.character.heading.text() != loaded.name:
                    raise RuntimeError("Qt editor failed to initialize expected widgets")
                result["checks"].append("QT_WIDGETS_OK")
            finally:
                window.close()
                window.deleteLater()
            app.processEvents()
        result["status"] = "SELF_TEST_OK"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        # Avoid embedding private absolute paths, checkpoint names or environment inventories.
        result["diagnostic"] = "Self-check failed; inspect local application logs"
    try:
        _result_file(report, result)
    except (OSError, RuntimeError) as exc:
        if sys.stderr is not None:
            print(f"UCC self-test could not write the report: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0 if result["status"] == "SELF_TEST_OK" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Universal Character Creator alpha desktop")
    parser.add_argument("--self-test", action="store_true", help="Exercise actual Qt and metadata roundtrip")
    parser.add_argument("--self-test-report", type=Path, metavar="FILE",
                        help="Write a new JSON test report to this path (never overwrite)")
    args = parser.parse_args(argv)
    if args.self_test_report is not None and not args.self_test:
        parser.error("--self-test-report requires --self-test")
    if args.self_test:
        return _self_test(args.self_test_report)
    try:
        from PySide6.QtWidgets import QApplication
        from ucc.desktop.window import MainWindow
    except ImportError as exc:
        if sys.stderr is not None:
            print('PySide6 is required: install with `py -3 -m pip install -e ".[desktop]"', file=sys.stderr)
            print(f"Dependency detail: {exc}", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("UCC")
    app.setApplicationName("Universal Character Creator")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
