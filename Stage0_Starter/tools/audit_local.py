#!/usr/bin/env python3
"""Read-only Windows preflight for UCC. Does not download or install anything.

Usage (Windows PowerShell):
  py -3 tools/audit_local.py --output preflight.json
  py -3 tools/audit_local.py --scan-root D:\\Models --scan-root F:\\ComfyUI --output preflight.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pth", ".pt", ".onnx", ".gguf"}
EXCLUDED_DIRS = {
    "$recycle.bin", "system volume information", "windows", "windows.old",
    "node_modules", ".git", ".venv", "venv", "__pycache__",
}


def find_program(program: str, explicit: str | None, candidates: list[Path]) -> dict:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    found = shutil.which(program)
    if found:
        paths.append(Path(found))
    paths.extend(candidates)
    for path in paths:
        if path.is_file():
            return {"found": True, "path": str(path.resolve())}
    return {"found": False, "tested_candidates": len(paths)}


def local_probe(url: str) -> dict:
    start = time.monotonic()
    try:
        with urlopen(url, timeout=2.5) as response:
            data = response.read(256)
            return {
                "reachable": True,
                "status_code": response.status,
                "duration_ms": round((time.monotonic() - start) * 1000),
                "sample_size": len(data),
            }
    except (URLError, HTTPError, OSError, TimeoutError) as error:
        return {"reachable": False, "error": type(error).__name__}


def probe_version(path: str, args: list[str], timeout: float = 8) -> dict:
    try:
        result = subprocess.run([path, *args], shell=False,
                                capture_output=True, text=True, errors="replace",
                                timeout=timeout)
        first_lines = (result.stdout + "\n" + result.stderr).strip().splitlines()[:3]
        return {"exit_code": result.returncode, "output": first_lines}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__, "detail": str(error)[:250]}


def scan_models(roots: list[Path], max_files: int = 150_000) -> dict:
    """Opt-in metadata-only scan. No file loads, no hash, no symlink traversal."""
    results = []
    errors = []
    visited = 0
    hit_limit = False
    for root in roots:
        if not root.is_dir():
            errors.append({"root": str(root), "error": "missing_or_not_directory"})
            continue
        for base, subdirs, filenames in os.walk(root, followlinks=False, onerror=lambda e: errors.append({"error": str(e)})):
            subdirs[:] = [d for d in subdirs if d.lower() not in EXCLUDED_DIRS
                          and not (Path(base) / d).is_symlink()]
            for filename in filenames:
                visited += 1
                if visited > max_files:
                    hit_limit = True
                    break
                path = Path(base) / filename
                if path.suffix.lower() not in MODEL_EXTENSIONS or path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                except OSError as error:
                    errors.append({"path": str(path), "error": type(error).__name__})
                    continue
                results.append({
                    "path": str(path), "bytes": stat.st_size,
                    "format": path.suffix.lower(), "model_family": "unknown",
                    "license_status": "unknown", "classification_confidence": 0.0,
                })
            if hit_limit:
                break
        if hit_limit:
            break
    return {"models": results, "examined_files": visited,
            "max_files_exceeded": hit_limit, "errors": errors}


def build_report(args: argparse.Namespace) -> dict:
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    report: dict = {
        "report_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "read_only": True,
    }
    blender_candidates = [
        program_files / "Blender Foundation" / f"Blender {version}" / "blender.exe"
        for version in ("5.3", "5.2", "5.1", "5.0")
    ]
    aseprite_candidates = [
        program_files / "Aseprite" / "aseprite.exe",
        local / "Programs" / "Aseprite" / "aseprite.exe",
        home / "scoop" / "apps" / "aseprite" / "current" / "aseprite.exe",
    ]
    report["blender"] = find_program("blender.exe" if os.name == "nt" else "blender", args.blender, blender_candidates)
    report["aseprite"] = find_program("aseprite.exe" if os.name == "nt" else "aseprite", args.aseprite, aseprite_candidates)
    for tool, flags in (("blender", ["--version"]), ("aseprite", ["--version"])):
        if report[tool]["found"]:
            report[tool]["version_probe"] = probe_version(report[tool]["path"], flags)
    report["nvidia_smi"] = {"found": bool(shutil.which("nvidia-smi"))}
    if shutil.which("nvidia-smi"):
        report["nvidia_smi"]["gpu"] = probe_version("nvidia-smi", [
            "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"])
    report["local_apis"] = {
        "comfyui": local_probe(args.comfyui.rstrip("/") + "/system_stats"),
        "webui": local_probe(args.webui.rstrip("/") + "/sdapi/v1/sd-models"),
    }
    report["model_scan"] = scan_models([Path(p).expanduser() for p in args.scan_root], args.max_files)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", help="Optional path to blender.exe")
    parser.add_argument("--aseprite", help="Optional path to aseprite.exe")
    parser.add_argument("--comfyui", default="http://127.0.0.1:8188")
    parser.add_argument("--webui", default="http://127.0.0.1:7860")
    parser.add_argument("--scan-root", action="append", default=[],
                        help="Directory to search; no roots means NO filesystem-wide scan")
    parser.add_argument("--max-files", type=int, default=150_000)
    parser.add_argument("--output", help="Write JSON report to this path instead of stdout")
    args = parser.parse_args()
    if args.max_files < 1:
        parser.error("--max-files must be positive")
    report = build_report(args)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote read-only preflight report: {path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
