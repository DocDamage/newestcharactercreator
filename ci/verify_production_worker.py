#!/usr/bin/env python3
"""Real Blender subprocess check for UCC's production worker (Linux CI).

Only the already-installed Blender and MPFB extension are used. Generates a
temporary .blend, then opens a byte-identical copy with a NEW Blender process
through the production JSON worker protocol. No output model is uploaded.
This does not certify deformation, Windows, animation or engine imports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner


from ucc.jobs.geometry_evidence import EvidenceError, verify_geometry


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_check(blender: Path, outdir: Path, timeout: int) -> dict[str, Any]:
    """Execute both operations through the same worker used by UCC."""
    runner = BlenderJobRunner(blender, outdir / "jobs", REPO / "blender_bridge" / "entrypoint.py")
    created, create_dir = runner.run(JobRequest.new("create_human"), timeout_s=timeout)
    if created.details.get("staged_blend") != "generated_human.blend":
        raise EvidenceError("Creation result points to an unexpected staged master name")

    master = create_dir / "generated_human.blend"
    if not master.is_file() or master.is_symlink() or master.stat().st_size < 1024:
        raise EvidenceError("Worker did not save a substantial .blend master")
    digest = _sha256(master)

    inspected, inspect_dir = runner.run(
        JobRequest.new("inspect_character", input_project="candidate.blend"),
        timeout_s=timeout, staged_inputs={"candidate.blend": master},
    )
    copy = inspect_dir / "candidate.blend"
    if not copy.is_file() or copy.is_symlink() or _sha256(copy) != digest:
        raise EvidenceError("Inspected candidate differs from the generated Blender master")
    stats = verify_geometry(created.details, inspected.details)
    return {
        "status": "REAL_LINUX_PRODUCTION_WORKER_CREATE_REOPEN_PASSED",
        **stats,
        "master_bytes": master.stat().st_size,
        "master_sha256": digest,
        "worker_protocol_version": created.protocol_version,
        "linux_save_reopen_verified": True,
        "windows_verified": False,
        "visual_deformation_verified": False,
        "animation_playback_verified": False,
        "engine_imports_verified": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 3600:
        parser.error("--timeout must be between 1 and 3600")
    outdir = args.outdir.resolve(strict=False)
    # Fresh directory prevents stale evidence from ever being treated as success.
    if outdir.exists() or outdir.is_symlink():
        parser.error("--outdir must be a new, unused directory")
    outdir.mkdir(parents=True)
    try:
        result = run_check(args.blender.resolve(strict=True), outdir, args.timeout)
    except Exception as exc:
        result = {"status": "error", "error_type": type(exc).__name__,
                  "message": str(exc)[:2000], "linux_save_reopen_verified": False}
    (outdir / "production_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "REAL_LINUX_PRODUCTION_WORKER_CREATE_REOPEN_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
