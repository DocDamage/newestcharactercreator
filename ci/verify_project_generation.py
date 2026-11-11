#!/usr/bin/env python3
"""Real Linux smoke for the desktop generation coordinator, no GUI or user data.

Runs Blender/MPFB twice, commits the inspected .blend as a content-addressed
master, and reopens the actual saved UCC project. Synthetic results are not used.
Does not validate Windows, deformation, animations or game-engine imports.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.humanoid_generation import generate_humanoid
from ucc.jobs.body_revision import apply_saved_body_revision
from ucc.jobs.master_preview import preview_saved_master
from ucc.jobs.pose_diagnostic import check_saved_master_pose


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(blender: Path, root: Path) -> dict:
    store = ProjectStore(root / "isolated-project")
    started = store.save(CharacterProject.new("CI Rigged Humanoid"))
    desired = {"height": .82, "muscle": .22, "weight": .88}
    original = store.save(
        replace(started, parameters=tuple(sorted(desired.items())),
                revision=started.revision + 1),
        expected_revision=started.revision,
    )
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
    if (dict(reopened.parameters) != desired or
            transaction.observed.get("macro_parameters_observed") != desired or
            not transaction.observed.get("morph_save_reopen_verified")):
        raise RuntimeError("Saved slider values were not applied to the real MPFB body")

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

    # Independent neutral baseline: a second real generated and reopened human.
    neutral_store = ProjectStore(root / "neutral-baseline")
    neutral = neutral_store.save(CharacterProject.new("Neutral baseline"))
    neutral_result = generate_humanoid(
        neutral_store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=neutral.project_id,
        expected_revision=neutral.revision, timeout_s=300,
    )
    if (neutral_result.observed["macro_parameters_observed"] !=
            {"height": .5, "muscle": .5, "weight": .5}):
        raise RuntimeError("Baseline MPFB phenotype unexpectedly not neutral")
    if (transaction.observed["macro_evaluated_sha256"] ==
            neutral_result.observed["macro_evaluated_sha256"]):
        raise RuntimeError("Changing saved body slider values did not change real Blender geometry")
    neutral_view = preview_saved_master(
        neutral_store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=neutral.project_id,
        expected_revision=neutral_result.revision.project.revision,
        expected_master_blend=neutral_result.revision.project.master_blend,
        timeout_s=300,
    )
    if (preview.mesh.source_face_count != neutral_view.mesh.source_face_count or
            preview.mesh.triangles == neutral_view.mesh.triangles):
        raise RuntimeError(
            "Static GLB preview did not reflect actual changed MPFB body geometry"
        )

    # Apply a second phenotype to the EXISTING model on an isolated copy.
    # No fresh basemesh generation is permitted within refit_human.
    refit_values = {"height": .66, "muscle": .76, "weight": .33}
    edited = store.save(
        replace(reopened, parameters=tuple(sorted(refit_values.items())),
                revision=reopened.revision + 1),
        expected_revision=reopened.revision,
    )
    refitted = apply_saved_body_revision(
        store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=edited.project_id,
        expected_revision=edited.revision,
        expected_master_blend=edited.master_blend,
        timeout_s=300,
    )
    new_project = ProjectStore(store.root).load()
    revised_master = store.root / new_project.master_blend
    if (new_project.geometry_state != "generated_unverified"
            or new_project.revision != edited.revision + 1
            or new_project.project_id != edited.project_id
            or new_project.master_blend == edited.master_blend
            or not revised_master.is_file()
            or _hash(master) != transaction.revision.sha256
            or _hash(revised_master) != refitted.revision.sha256
            or refitted.observed["macro_parameters_observed"] != refit_values
            or not refitted.observed["rig_binding_verified"]
            or not refitted.observed["morph_save_reopen_verified"]
            or refitted.observed["macro_evaluated_sha256"] ==
               transaction.observed["macro_evaluated_sha256"]):
        raise RuntimeError("Existing MPFB rig/body was not safely refitted and reopened")
    refit_preview = preview_saved_master(
        store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=new_project.project_id,
        expected_revision=new_project.revision,
        expected_master_blend=new_project.master_blend,
        timeout_s=300,
    )
    if refit_preview.mesh.triangles == preview.mesh.triangles:
        raise RuntimeError("Refitted real character GLB preview geometry did not change")
    if ProjectStore(store.root).load() != new_project:
        raise RuntimeError("Refit preview modified the UCC project")

    # Two further genuine Blender processes must rotate a weighted deform bone,
    # observe real evaluated vertex movement, restore the pose and agree on hashes.
    pose = check_saved_master_pose(
        store, blender_exe=blender,
        worker_script=ROOT / "blender_bridge" / "entrypoint.py",
        expected_project_id=new_project.project_id,
        expected_revision=new_project.revision,
        expected_master_blend=new_project.master_blend,
        timeout_s=300,
    )
    p = pose.evidence
    if (p["moved_vertex_count"] < 16 or
            p["neutral_evaluated_sha256"] == p["posed_evaluated_sha256"] or
            p["neutral_evaluated_sha256"] != p["restored_evaluated_sha256"] or
            p["animation_clip_playback_verified"] is not False or
            p["engine_import_verified"] is not False or
            p["source_master_saved"] is not False or
            not p["rig_binding_verified"] or
            len(pose.worker_job_ids) != 2):
        raise RuntimeError("Existing refitted rig failed real two-process pose test")
    if (ProjectStore(store.root).load() != new_project or
            _hash(revised_master) != refitted.revision.sha256):
        raise RuntimeError("Transient pose test modified the saved Blender master")

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
        "requested_body_macros": desired,
        "observed_body_macros": transaction.observed["macro_parameters_observed"],
        "changed_body_sha256": transaction.observed["macro_evaluated_sha256"],
        "neutral_body_sha256": neutral_result.observed["macro_evaluated_sha256"],
        "real_body_shape_different_from_neutral": True,
        "static_preview_mesh_different_from_neutral": True,
        "preview_status": "REAL_LINUX_STATIC_MASTER_PREVIEW_PARSED",
        "preview_face_count": preview.mesh.source_face_count,
        "preview_sampled_faces": preview.mesh.sample_count,
        "preview_mesh_vertices": preview.selected_vertex_count,
        "preview_glb_sha256": preview.glb_sha256,
        "preview_master_sha256": preview.master_sha256,
        "preview_skinning_evaluated": False,
        "preview_animation_evaluated": False,
        "refit_status": "REAL_LINUX_EXISTING_MPFb_RIG_REFIT_REOPEN_PASSED",
        "refit_requested_macros": refit_values,
        "refit_observed_macros": refitted.observed["macro_parameters_observed"],
        "refit_original_master_sha256": transaction.revision.sha256,
        "refit_new_master_sha256": refitted.revision.sha256,
        "refit_body_sha256": refitted.observed["macro_evaluated_sha256"],
        "refit_weight_sha256": refitted.observed["weight_sha256"],
        "refit_weighted_vertices": refitted.observed["weighted_vertices"],
        "refit_bones": refitted.observed["reopened_bones"],
        "refit_rig_binding_verified": True,
        "refit_preview_geometry_changed": True,
        "refit_original_master_preserved": True,
        "refit_new_project_revision": new_project.revision,
        "pose_test_status": p["status"],
        "pose_test_bone": p["selected_deform_bone"],
        "pose_test_axis": p["rotation_axis_index"],
        "pose_test_rotation_degrees": p["rotation_degrees"],
        "pose_test_moved_vertices": p["moved_vertex_count"],
        "pose_test_max_displacement_local": p["max_vertex_displacement_local"],
        "pose_test_restored_neutral_sha256": p["restored_evaluated_sha256"],
        "pose_test_original_sha256": p["neutral_evaluated_sha256"],
        "pose_test_deformed_sha256": p["posed_evaluated_sha256"],
        "pose_test_source_master_unchanged": True,
        "pose_test_two_processes_agreed": True,
        "pose_test_animation_playback_verified": False,
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
