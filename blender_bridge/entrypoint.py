"""Blender-only job entrypoint, isolated from the desktop process.

Real bpy/MPFB integration runs only on isolated staged inputs. Acceptance docs
record executed Blender 5.3 gates; numerical diagnostics and saved-copy reopen
do not grant visual quality, arbitrary-rig compatibility or engine approval.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import traceback

import bpy

# Blender --python does not guarantee the repository parent is on sys.path.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from blender_bridge.mpfb_service import (
    create_human_with_rig, inspect_service, locate_human_service,
    locate_target_service, locate_human_properties,
)
from blender_bridge.morphs import check_macro_values, inspect_applied_macro
from blender_bridge.preview_export import export_static_glb
from blender_bridge.refit_revision import apply_body_revision, rig_fingerprint
from blender_bridge.pose_deformation import probe_pose_deformation
from blender_bridge.timeline_animation import verify_keyframed_timeline as verify_real_timeline
from blender_bridge.bvh_clip_probe import source_motion_probe
from blender_bridge.bvh_multichain import verify_multibone_source
from blender_bridge.bvh_calibration_probe import calibrate_bvh_source
from blender_bridge.result_encoding import encode_result
from blender_bridge.channel_bone_conversion import CONVENTION
from blender_bridge.fbx_source import inspect_fbx_source
from blender_bridge.native_retarget import retarget_native
from blender_bridge.native_review_reopen import reopen_native
from blender_bridge.native_playback_cache import export_native_cache
from blender_bridge.native_surface_verify import verify_surface_review
from blender_bridge.native_fit_policy import checked_job
from blender_bridge.native_fit_action import stage_native_fit
from blender_bridge.native_fit_measure import measure_fit,verify_fit

PROTOCOL_VERSION = 1
OPERATIONS = {"inspect_environment", "inspect_character", "create_human", "export_preview_glb", "refit_human", "verify_skin_deformation", "verify_keyframed_timeline", "verify_local_bvh_motion", "verify_multi_bvh_chain", "verify_calibrated_bvh_chain", "verify_reviewed_bvh_chain", "inspect_fbx_animation", "verify_native_fbx_body", "reopen_native_fbx_body", "cache_native_fbx_body", "verify_native_surface_review"}
OPERATIONS |= {"fit_native_fbx_body", "measure_native_fit", "verify_native_fit"}


def native_target_fit(job: dict, root: Path) -> dict:
    options=checked_job(job)
    return {"fit_native_fbx_body":stage_native_fit,"measure_native_fit":measure_fit,"verify_native_fit":verify_fit}[job["operation"]](bpy,root,options)


def verify_native_body(job: dict, root: Path) -> dict:
    options=job["options"]
    hashes={"source_sha256","snapshot_sha256","mapping_sha256","master_sha256"}
    if (job["input_project"]!="candidate.blend" or set(options)!=hashes|{"render_private_frames"} or
            type(options["render_private_frames"]) is not bool or
            any(type(options[k]) is not str or len(options[k])!=64 or any(c not in "0123456789abcdef" for c in options[k]) for k in hashes)):
        raise ValueError("Native body job needs exact bound source/snapshot/map/master and explicit rendering")
    return retarget_native(bpy,root,options)


def reopen_native_body(job: dict, root: Path) -> dict:
    options=job["options"]
    hashes={"source_sha256","snapshot_sha256","mapping_sha256","master_sha256","review_sha256","timeline_sha256"}
    if job["operation"]=="verify_native_surface_review":hashes.add("surface_review_sha256")
    if (job["input_project"]!="candidate.blend" or set(options)!=hashes or
            any(type(options[k]) is not str or len(options[k])!=64 or any(c not in "0123456789abcdef" for c in options[k]) for k in hashes)):
        raise ValueError("Native reopen needs six exact input identities and no paths or override flags")
    action={"cache_native_fbx_body":export_native_cache,"reopen_native_fbx_body":reopen_native,
            "verify_native_surface_review":verify_surface_review}[job["operation"]]
    return action(bpy,root,options)


def inspect_native_fbx(job: dict, root: Path) -> dict:
    options = job["options"]
    digest = options.get("source_sha256")
    if (job["input_project"] is not None or set(options) != {"source_sha256"} or
            type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("Native FBX intake requires exact source SHA and no master")
    return inspect_fbx_source(bpy, member(root,"source.fbx"), member(root,"source_snapshot.json"), digest)


def arguments() -> argparse.Namespace:
    extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    return parser.parse_args(extra)


def member(root: Path, path: str) -> Path:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or path.startswith("/"):
        raise ValueError("Only project-relative paths are accepted")
    if any(part in ("..", ".", "") for part in path.split("/")):
        raise ValueError("Unsafe project-relative path")
    resolved = (root / path).resolve(strict=False)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Path escapes isolated job workspace")
    return resolved


def mpfb_status() -> dict:
    return inspect_service()


def inspect_environment(_: dict, __: Path) -> dict:
    return {"blender_version": bpy.app.version_string,
            "blender_version_tuple": list(bpy.app.version),
            "mpfb_service": mpfb_status()}


def inspect_character(job: dict, root: Path) -> dict:
    source = member(root, job["input_project"])
    if not source.is_file() or source.suffix.lower() != ".blend":
        raise ValueError("Staged input .blend not found")
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes or sum(len(o.data.vertices) for o in meshes) <= 100:
        raise RuntimeError("Insufficient 3D mesh geometry")
    result = {"blender_version": bpy.app.version_string,
              "mesh_count": len(meshes),
              "vertex_count": sum(len(o.data.vertices) for o in meshes),
              "armatures": [{"name": a.name, "bone_count": len(a.data.bones)}
                            for a in bpy.data.objects if a.type == "ARMATURE"],
              "shape_keys": {m.name: ([key.name for key in m.data.shape_keys.key_blocks]
                                      if m.data.shape_keys else []) for m in meshes},
              "visual_deformation_verified": False}
    options = job["options"]
    if options:
        if set(options) not in ({"macro_parameters"},
                                {"macro_parameters", "verify_rig_binding"}):
            raise ValueError("Only explicit MPFB macro/rig inspection is supported")
        requested = check_macro_values(options["macro_parameters"])
        candidates = [m for m in meshes if len(m.data.vertices) > 100]
        if len(candidates) != 1:
            raise RuntimeError("Expected exactly one substantial MPFB basemesh")
        _, human_module = locate_human_service()
        target_service, _ = locate_target_service(human_module)
        result.update(inspect_applied_macro(bpy, candidates[0], target_service, requested))
        if options.get("verify_rig_binding") is True:
            result["rig_binding"] = rig_fingerprint(bpy, candidates[0])
    return result


def export_preview_glb(job: dict, root: Path) -> dict:
    """Export a static GLB from the staged .blend; never save the master."""
    source = member(root, job["input_project"])
    output = member(root, "preview.glb")
    return export_static_glb(bpy, source, output)


def verify_calibrated_bvh_chain(job: dict, root: Path) -> dict:
    """Solve real rest landmarks and apply source motion via target bone matrices."""
    options = job["options"]
    if set(options) != {"axis_profile"} or options["axis_profile"] not in (
        "Y_UP_TO_Z_UP", "Z_UP_IDENTITY",
    ):
        raise ValueError("Explicit supported BVH up-axis required for calibration")
    return calibrate_bvh_source(
        bpy, member(root, job["input_project"]), member(root, "motion.bvh"),
        options["axis_profile"],
    )


def verify_reviewed_bvh_chain(job: dict, root: Path) -> dict:
    """Animate only the explicitly paired 3–64 bone hierarchy in a private copy."""
    options = job["options"]
    if (not {"axis_profile", "reviewed_mapping"}.issubset(options) or
        set(options) - {"axis_profile", "reviewed_mapping", "source_rest_profile_sha256",
                        "source_frame_conversion", "render_private_frames"}) or options["axis_profile"] not in (
        "Y_UP_TO_Z_UP", "Z_UP_IDENTITY",
    ):
        raise ValueError("Reviewed BVH needs exact bone pairs and explicit source axes")
    pairs = options["reviewed_mapping"]
    if type(pairs) is not list or not 3 <= len(pairs) <= 64:
        raise ValueError("Reviewed BVH needs 3–64 source/target bone pairs")
    rest_sha = options.get("source_rest_profile_sha256")
    if "source_rest_profile_sha256" in options and (
        type(rest_sha) is not str or len(rest_sha) != 64 or any(c not in "0123456789abcdef" for c in rest_sha)
    ):
        raise ValueError("Source rest profile SHA-256 must be exact lowercase hex")
    if "source_frame_conversion" in options and (
        options["source_frame_conversion"] != CONVENTION or rest_sha is None
    ):
        raise ValueError("Only the explicit bound BVH conversion convention is supported")
    if "render_private_frames" in options and (
        options["render_private_frames"] is not True or "source_frame_conversion" not in options
    ):
        raise ValueError("Private rendering requires audited source-frame conversion")
    return calibrate_bvh_source(
        bpy, member(root, job["input_project"]), member(root, "motion.bvh"),
        options["axis_profile"], reviewed_mapping=pairs,
        review_path=member(root, "review_motion.blend"),
        source_rest_profile=member(root, "source_rest_frames.json") if rest_sha is not None else None,
        source_rest_profile_sha256=rest_sha,
        audit_source_frames="source_frame_conversion" in options,
        render_private_frames=options.get("render_private_frames", False),
    )


def verify_multi_bvh_chain(job: dict, root: Path) -> dict:
    """Validate and sample only a staged source chain in isolated Blender."""
    options = job["options"]
    if set(options) != {"axis_profile"} or options["axis_profile"] not in (
        "Y_UP_TO_Z_UP", "Z_UP_IDENTITY",
    ):
        raise ValueError("Explicit approved BVH up-axis profile required")
    return verify_multibone_source(
        bpy, member(root, job["input_project"]), member(root, "motion.bvh"),
        options["axis_profile"],
    )


def verify_local_bvh_motion(job: dict, root: Path) -> dict:
    """Evaluate only a staged BVH file, with no arbitrary runtime options."""
    if job["options"]:
        raise ValueError("BVH preview accepts no dynamic scripts or settings")
    return source_motion_probe(
        bpy, member(root, job["input_project"]), member(root, "motion.bvh"),
    )


def verify_keyframed_timeline(job: dict, root: Path) -> dict:
    """Create and sample original diagnostic keyframes without ever saving them."""
    if job["options"]:
        raise ValueError("Keyframed diagnostic has no user-editable options")
    return verify_real_timeline(bpy, member(root, job["input_project"]))


def verify_skin_deformation(job: dict, root: Path) -> dict:
    """Measure a fixed transient bone test on the staged .blend, never save it."""
    if job["options"]:
        raise ValueError("Skin diagnostic accepts no dynamic arguments")
    source = member(root, job["input_project"])
    return probe_pose_deformation(bpy, source)


def refit_human(job: dict, root: Path) -> dict:
    """Morph/refit a private staged copy; never save over the authoritative master."""
    options = job["options"]
    if set(options) != {"macro_parameters"}:
        raise ValueError("Refit requires exactly saved MPFB macro parameters")
    source = member(root, job["input_project"])
    destination = member(root, "refitted_human.blend")
    values = check_macro_values(options["macro_parameters"])
    human_service, module = locate_human_service()
    target_service, _ = locate_target_service(module)
    properties, _ = locate_human_properties(module)
    return apply_body_revision(
        bpy, source, destination, values, human_service, target_service, properties,
    )


def create_human(job: dict, root: Path) -> dict:
    service, module = locate_human_service()
    options = job["options"]
    if options:
        if set(options) != {"macro_parameters"}:
            raise ValueError("Only saved MPFB macro controls may be used")
        values = check_macro_values(options["macro_parameters"])
        target_service, _ = locate_target_service(module)
        details = create_human_with_rig(
            bpy, service, "default", macro_parameters=values,
            target_service=target_service,
        )
    else:
        details = create_human_with_rig(bpy, service, "default")
    path = member(root, "generated_human.blend")
    # The project master staging contract requires the canonical BLENDER header;
    # default per-install compression settings must not change file format.
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=False)
    if not path.is_file() or path.stat().st_size < 16:
        raise RuntimeError("Generated project was not saved")
    return {"blender_version": bpy.app.version_string, "mpfb_service_module": module,
            "staged_blend": "generated_human.blend", "bytes": path.stat().st_size,
            **details}


def main() -> int:
    args = arguments()
    root = args.workspace.resolve(strict=True)
    request = args.request.resolve(strict=True)
    result = args.result.resolve(strict=False)
    if not request.is_relative_to(root) or not result.is_relative_to(root):
        raise SystemExit("Job paths must remain in isolated workspace")
    data = json.loads(request.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"protocol_version", "job_id", "operation", "input_project", "options"}:
        raise SystemExit("Invalid request schema")
    if type(data["protocol_version"]) is not int or data["protocol_version"] != PROTOCOL_VERSION:
        raise SystemExit("Unsupported request version")
    import uuid
    uuid.UUID(data["job_id"])
    if type(data["options"]) is not dict:
        raise SystemExit("Worker options must be a JSON object")
    operation = data["operation"]
    if operation not in OPERATIONS:
        raise SystemExit("Unknown operation")
    reply = {"protocol_version": PROTOCOL_VERSION, "job_id": data["job_id"],
             "operation": operation, "status": "error", "details": {}, "error": "Unknown error"}
    try:
        action = {"inspect_environment": inspect_environment,
                  "inspect_character": inspect_character,
                  "create_human": create_human,
                  "export_preview_glb": export_preview_glb,
                  "refit_human": refit_human,
                  "verify_skin_deformation": verify_skin_deformation,
                  "verify_keyframed_timeline": verify_keyframed_timeline,
                  "verify_local_bvh_motion": verify_local_bvh_motion,
                  "verify_multi_bvh_chain": verify_multi_bvh_chain,
                  "verify_calibrated_bvh_chain": verify_calibrated_bvh_chain,
                   "verify_reviewed_bvh_chain": verify_reviewed_bvh_chain,
                   "inspect_fbx_animation": inspect_native_fbx,
                   "verify_native_fbx_body": verify_native_body,
                   "reopen_native_fbx_body": reopen_native_body,
                   "cache_native_fbx_body": reopen_native_body,
                   "verify_native_surface_review": reopen_native_body,
                   "fit_native_fbx_body": native_target_fit,
                   "measure_native_fit": native_target_fit,
                   "verify_native_fit": native_target_fit}[operation]
        reply["details"] = action(data, root)
        reply["status"] = "ok"
        reply["error"] = None
    except Exception as exc:
        reply["error"] = f"{type(exc).__name__}: {exc}"
        reply["details"] = {"traceback_tail": traceback.format_exc()[-5000:]}
    result.write_text(encode_result(reply), encoding="utf-8")
    return 0 if reply["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
