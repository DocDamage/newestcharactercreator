#!/usr/bin/env python3
"""Real Blender+MPFB smoke test. Requires existing Blender 5.3 with MPFB enabled.

Example (PowerShell):
  py -3 tools/run_mpfb_smoke.py --blender "C:\\Program Files\\Blender Foundation\\Blender 5.3\\blender.exe"

Creates a test .blend in --outdir (does not change user projects).
A failure is intentional when the MPFB operator is not registered or needs GUI context.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def execute(args: list[str], seconds: int) -> dict:
    try:
        p = subprocess.run(args, shell=False, capture_output=True, text=True,
                           errors="replace", timeout=seconds)
        return {"return_code": p.returncode,
                "stdout_tail": p.stdout[-7000:], "stderr_tail": p.stderr[-7000:]}
    except subprocess.TimeoutExpired as error:
        return {"return_code": None, "error": "timeout", "detail": str(error)}
    except OSError as error:
        return {"return_code": None, "error": type(error).__name__, "detail": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, help="Exact path to installed blender.exe")
    parser.add_argument("--outdir", default="ucc-smoke-results", help="Test-only output folder")
    parser.add_argument("--timeout", type=int, default=240)
    opt = parser.parse_args()
    outdir = Path(opt.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1]
    blend = outdir / "mpfb_created.blend"
    creation_json = outdir / "mpfb_create_result.json"
    creation = execute([opt.blender, "--background", "--python",
                        str(base / "blender_bridge" / "mpfb_smoke.py"), "--",
                        "--output", str(creation_json), "--blend", str(blend)], opt.timeout)
    report = {"create": creation, "test_blend": str(blend)}
    if creation.get("return_code") == 0 and blend.is_file():
        reopen_json = outdir / "reopen_result.json"
        reopen = execute([opt.blender, "--background", str(blend), "--python",
                          str(base / "blender_bridge" / "check_blend.py"), "--",
                          str(reopen_json)], opt.timeout)
        report["reopen"] = reopen
        if reopen_json.is_file():
            report["reopen_data"] = json.loads(reopen_json.read_text(encoding="utf-8"))
    report["passed"] = bool(
        report.get("reopen", {}).get("return_code") == 0 and
        report.get("reopen_data", {}).get("status") == "ok")
    (outdir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS" if report["passed"] else "NOT PASSED")
    print(f"Full evidence: {outdir / 'summary.json'}")
    if not report["passed"]:
        print("Check create/reopen logs. Failure may reflect Blender/MPFB headless context.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
