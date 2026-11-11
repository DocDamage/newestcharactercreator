#!/usr/bin/env python3
"""Real Linux smoke for the desktop generation coordinator, no GUI or user data.

Runs Blender/MPFB twice, commits the inspected .blend as a content-addressed
master, and reopens the actual saved UCC project. Synthetic results are not used.
Does not validate Windows, deformation, animations or game-engine imports.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.humanoid_generation import generate_humanoid
from ucc.jobs.master_preview import preview_saved_master


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(blender: Path, root: Path) -> dict:
    store = ProjectStore(root / "isolated-project")
    original = store.save(CharacterProject.new("CI Rigged Humanoid"))
    transaction = generate_humanoid(
        store,
        blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=original.project_id,
        expected_revision=original.revision,
        timeout_s=300,
    )
    reopened = ProjectStore(store.root).load()
    master = store.root / reopened.master_blend
    if (reopened.project_id != original.project_id
            or reopened.revision != original.revision + 1
            or reopened.geometry_state != "generated_unverified"
            or reopened.rig_profile is not None
            or not master.is_file() or master.is_symlink()):
        raise RuntimeError("Project did not retain its identity and unverified master revision")
    if master.stat().st_size < 1024 or _hash(master) != transaction.revision.sha256:
        raise RuntimeError("Committed content-addressed master is missing or mismatched")
    if reopened.master_blend != (
        f"master/versions/{transaction.revision.sha256}.blend"
    ):
        raise RuntimeError("Authoritative master path is not content-addressed")
    if not store.list_backups():
        raise RuntimeError("Previous project metadata revision has no backup")
    if transaction.geometry_state != "generated_unverified" or (
        not reopened.export_readiness()
    ):
        raise RuntimeError("Unverified geometry incorrectly reports engine readiness")

    # Fourth real Blender process: export a static GLB from the persisted master,
    # then parse its actual triangles through the exact reader used by Qt.
    preview = preview_saved_master(
        store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=reopened.project_id,
        expected_revision=reopened.revision,
        expected_master_blend=reopened.master_blend,
        timeout_s=300,
    )
    if (preview.mesh.source_face_count <= 100 or
            preview.mesh.sample_count <= 0 or
            preview.mesh.sample_count > 2000 or
            preview.mesh.animation_count != 0 or
            preview.mesh.skin_count != 0 or
            preview.certified_for_engine_import or
            preview.master_sha256 != transaction.revision.sha256):
        raise RuntimeError("Blender static GLB preview did not meet the bounded preview gate")
    # Preview is a diagnostic; no extra authoritative revision or master mutation.
    if (ProjectStore(store.root).load() != reopened or
            not master.is_file() or
            _hash(master) != transaction.revision.sha256):
        raise RuntimeError("Static preview mutated the authoritative project or Blender master")

    return {
        "status": "REAL_LINUX_PROJECT_GENERATE_REOPEN_STAGED",
        "blender_version": transaction.observed["blender_version"],
        "created_vertices": transaction.observed["created_vertex_count"],
        "reopened_bones": transaction.observed["reopened_bone_count"],
        "project_revision": reopened.revision,
        "master_bytes": master.stat().st_size,
        "master_sha256": transaction.revision.sha256,
        "independent_reopen": True,
        "project_roundtrip": True,
        "geometry_state": reopened.geometry_state,
        "preview_status": "REAL_LINUX_STATIC_MASTER_PREVIEW_PARSED",
        "preview_face_count": preview.mesh.source_face_count,
        "preview_sampled_faces": preview.mesh.sample_count,
        "preview_mesh_vertices": preview.selected_vertex_count,
        "preview_glb_sha256": preview.glb_sha256,
        "preview_master_sha256": preview.master_sha256,
        "preview_skinning_evaluated": False,
        "preview_animation_evaluated": False,
        "windows_verified": False,
        "deformation_verified": False,
        "engine_imports_verified": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    if args.outdir.exists() or args.outdir.is_symlink():
        parser.error("--outdir must be an unused directory")
    args.outdir.mkdir(parents=True)
    try:
        report = verify(args.blender.resolve(strict=True), args.outdir)
    except Exception as exc:
        report = {"status": "error", "error_type": type(exc).__name__,
                  "message": str(exc)[:1000], "project_roundtrip": False}
    (args.outdir / "transaction_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "REAL_LINUX_PROJECT_GENERATE_REOPEN_STAGED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
