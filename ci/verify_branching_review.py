"""Real branching coordinator gate; never infer the provenance of the input rig.

Production CI passes the generated MPFB master. Local synthetic tests explicitly
label that input separately. Private .blend/BVH/PNG files must never be uploaded.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ucc.jobs.bvh_clip_diagnostic import check_selected_bvh
from ucc.jobs.runner import WorkerFailure
from ucc.core.errors import ValidationError


def verify_branching(store, blender, master, project, permission, directory,
                     *, required_targets=()):
    script = ROOT / "ci/branching_blender_fixture.py"
    source = directory / "original-branching-contract.bvh"

    def run(mode, blend, output):
        subprocess.run([str(blender), "--background", "--disable-autoexec",
                        "--python-exit-code", "13", "--python", str(script), "--",
                        "--mode", mode, "--blend", str(blend), "--output", str(output)],
                       check=True, timeout=240)

    metadata = store.root / "project.ucc.json"
    digest = lambda path: sha256(path.read_bytes()).hexdigest()
    original = (digest(master), digest(metadata))
    run("create", master, source)
    pairs = json.loads(source.with_suffix(".json").read_text(encoding="utf-8"))
    source_hash = digest(source)
    result = check_selected_bvh(
        store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
        source_bvh=source, permission=permission, expected_project_id=project.project_id,
        expected_revision=project.revision, expected_master_blend=project.master_blend,
        multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
        reviewed_mapping=pairs, timeout_s=300)
    report = result.evidence
    rest_path = source.with_suffix(".rest.json")
    rest_sha = digest(rest_path)
    profiled = check_selected_bvh(
        store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
        source_bvh=source, permission=permission, expected_project_id=project.project_id,
        expected_revision=project.revision, expected_master_blend=project.master_blend,
        multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
        reviewed_mapping=pairs, source_rest_profile=rest_path, timeout_s=300)
    intake = profiled.evidence["source_rest_frame_intake"]
    if (intake["profile_sha256"] != rest_sha or intake["joint_count"] != len(pairs) or
            not intake["validation_only"] or intake["source_channel_interpretation_changed"] or
            profiled.evidence["full_timeline_frames"] != report["full_timeline_frames"]):
        raise RuntimeError("Optional source rest intake changed channel behavior or binding")
    bad = json.loads(rest_path.read_text(encoding="utf-8"))
    bad["source_bvh_sha256"] = "0" * 64
    bad_path = source.with_suffix(".wrong-binding.json")
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    before_jobs = set((store.root / ".ucc-jobs").iterdir())
    try:
        check_selected_bvh(
            store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
            source_bvh=source, permission=permission, expected_project_id=project.project_id,
            expected_revision=project.revision, expected_master_blend=project.master_blend,
            multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
            reviewed_mapping=pairs, source_rest_profile=bad_path)
    except ValidationError:
        pass
    else:
        raise RuntimeError("Mismatched source-rest BVH binding was accepted")
    if set((store.root / ".ucc-jobs").iterdir()) != before_jobs:
        raise RuntimeError("Mismatched BVH binding launched a worker")
    bad = json.loads(rest_path.read_text(encoding="utf-8"))
    bad["joint_frames"][0]["head"][0] += .125
    bad["joint_frames"][0]["tail"][0] += .125
    bad_path = source.with_suffix(".wrong-origin.json")
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    try:
        check_selected_bvh(
            store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
            source_bvh=source, permission=permission, expected_project_id=project.project_id,
            expected_revision=project.revision, expected_master_blend=project.master_blend,
            multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
            reviewed_mapping=pairs, source_rest_profile=bad_path)
    except WorkerFailure as error:
        if "rest head" not in str(error):
            raise
    else:
        raise RuntimeError("Actual Blender accepted a source rest origin unlike the BVH")
    parents = [b["parent"] for b in report["mapped_bones"] if b["parent"] is not None]
    if len(pairs) < 9 or len(set(parents)) == len(parents):
        raise RuntimeError("Real review did not exercise a branching map beyond eight bones")
    if not set(required_targets).issubset({p["target"] for p in pairs}):
        raise RuntimeError("Branching review omitted required full-body endpoints")
    wrong = [dict(p) for p in pairs]
    rows = report["mapped_bones"]
    first, second = next((i, j) for i in range(1, len(rows)) for j in range(i + 1, len(rows))
                         if rows[i]["parent"] != rows[j]["parent"])
    wrong[first]["target"], wrong[second]["target"] = wrong[second]["target"], wrong[first]["target"]
    try:
        check_selected_bvh(
            store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
            source_bvh=source, permission=permission, expected_project_id=project.project_id,
            expected_revision=project.revision, expected_master_blend=project.master_blend,
            multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
            reviewed_mapping=wrong, timeout_s=180)
    except WorkerFailure as error:
        if "parents differ" not in str(error):
            raise
    else:
        raise RuntimeError("Genuine Blender accepted a crossed target hierarchy")
    review_path = Path(result.private_visual_review_blend)
    review_hash = digest(review_path)
    run("reject-step", master, source.with_suffix(".json"))
    run("inspect", review_path, source.with_suffix(".json"))
    reopened = json.loads(review_path.with_suffix(".reopened.json").read_text(encoding="utf-8"))
    if reopened != [frame["evaluated_sha256"] for frame in report["full_timeline_frames"]]:
        raise RuntimeError("All independently reopened skin frames must match the workers")
    quality = json.loads(review_path.with_suffix(".quality.json").read_text(encoding="utf-8"))
    if quality["mesh_edge_strain"] != report["mesh_edge_strain"]:
        raise RuntimeError("Independent reopen edge topology differs")
    for first, second in zip(report["full_timeline_frames"], quality["edge_frames"], strict=True):
        if any(abs(first[key] - second[key]) > 1e-6 for key in second):
            raise RuntimeError("Independent reopen full-frame local edge strain differs")
    for first, second in zip(report["joint_motion_metrics"], quality["joint_motion_metrics"], strict=True):
        for key in first:
            same = (abs(first[key] - second[key]) <= .001 if key.endswith("_degrees")
                    else first[key] == second[key])
            if not same:
                raise RuntimeError("Independent reopen measured joint swing/twist differs: " + key)
    if (original != (digest(master), digest(metadata)) or source_hash != digest(source)
            or review_hash != digest(review_path) or rest_sha != digest(rest_path) or store.load() != project):
        raise RuntimeError("Branching diagnostics modified original source/project/review bytes")
    return {
        "mapped_bones": report["mapped_bones"], "mapped_bone_count": len(pairs),
        "rest_landmark_count": report["rest_landmark_count"],
        "max_rest_residual_degrees": report["max_rest_residual_degrees"],
        "max_adjacent_mesh_step_local": report["max_adjacent_mesh_step_local"],
        "all_frames_evaluated": len(reopened), "two_workers_agree": True,
        "third_process_all_frames_agree": True, "original_bytes_unchanged": True,
        "crossed_target_hierarchy_rejected": True,
        "required_anatomical_endpoints": list(required_targets),
        "motion_quality_schema_version": report["motion_quality_schema_version"],
        "mesh_edge_strain": report["mesh_edge_strain"],
        "joint_motion_metrics": report["joint_motion_metrics"],
        "min_edge_length_ratio": min(f["min_edge_length_ratio"] for f in report["full_timeline_frames"]),
        "max_edge_stretch_ratio": max(f["max_edge_stretch_ratio"] for f in report["full_timeline_frames"]),
        "third_process_quality_metrics_agree": True,
        "quality_fault_injections_rejected_and_skin_restored": True,
        "partial_action_removed_after_step_failure": True,
        "source_rest_frame_intake": intake,
        "source_rest_profile_original_sha256": rest_sha,
        "source_rest_profile_original_bytes_unchanged": True,
        "source_rest_wrong_binding_rejected_before_worker": True,
        "source_rest_wrong_origin_rejected_by_blender": True,
        "source_rest_validation_did_not_change_motion": True,
        "retargeting_verified": False, "animation_visual_quality_verified": False,
        "engine_import_verified": False,
    }
