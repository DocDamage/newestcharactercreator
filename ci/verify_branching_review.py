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


def verify_branching(store, blender, master, project, permission, directory):
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
    parents = [b["parent"] for b in report["mapped_bones"] if b["parent"] is not None]
    if len(pairs) < 9 or len(set(parents)) == len(parents):
        raise RuntimeError("Real review did not exercise a branching map beyond eight bones")
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
    run("inspect", review_path, source.with_suffix(".json"))
    reopened = json.loads(review_path.with_suffix(".reopened.json").read_text(encoding="utf-8"))
    if reopened != [frame["evaluated_sha256"] for frame in report["full_timeline_frames"]]:
        raise RuntimeError("All independently reopened skin frames must match the workers")
    if (original != (digest(master), digest(metadata)) or source_hash != digest(source)
            or review_hash != digest(review_path) or store.load() != project):
        raise RuntimeError("Branching diagnostics modified original source/project/review bytes")
    return {
        "mapped_bones": report["mapped_bones"], "mapped_bone_count": len(pairs),
        "rest_landmark_count": report["rest_landmark_count"],
        "max_rest_residual_degrees": report["max_rest_residual_degrees"],
        "max_adjacent_mesh_step_local": report["max_adjacent_mesh_step_local"],
        "all_frames_evaluated": len(reopened), "two_workers_agree": True,
        "third_process_all_frames_agree": True, "original_bytes_unchanged": True,
        "crossed_target_hierarchy_rejected": True,
        "retargeting_verified": False, "animation_visual_quality_verified": False,
        "engine_import_verified": False,
    }
