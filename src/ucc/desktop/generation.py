"""Desktop binding for UCC's existing isolated Blender worker.

The source and frozen builds must both ship the exact trusted bridge script.
This module never installs Blender/MPFB, selects an executable without user
action, or starts a job on import.
"""
from __future__ import annotations

from pathlib import Path
import sys
from threading import Event

from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.jobs.humanoid_generation import HumanoidGeneration, generate_humanoid
from ucc.jobs.body_revision import BodyRevisionResult, apply_saved_body_revision
from ucc.jobs.customized_humanoid import CustomizedHumanoidBuild
from ucc.jobs.master_preview import MasterPreview, preview_saved_master
from ucc.jobs.pose_diagnostic import SavedMasterPoseCheck, check_saved_master_pose
from ucc.jobs.timeline_diagnostic import SavedTimelineDiagnostic, check_saved_master_timeline
from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck, check_selected_bvh
from ucc.library.provenance import LicensePolicy


def bundled_worker_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[3]
    worker = base / "blender_bridge" / "entrypoint.py"
    service = worker.parent / "mpfb_service.py"
    preview = worker.parent / "preview_export.py"
    morphs = worker.parent / "morphs.py"
    refit = worker.parent / "refit_revision.py"
    pose = worker.parent / "pose_deformation.py"
    timeline = worker.parent / "timeline_animation.py"
    bvh_parser = worker.parent / "bvh_motion.py"
    bvh_probe = worker.parent / "bvh_clip_probe.py"
    multi_chain = worker.parent / "bvh_multichain.py"
    calibration_math = worker.parent / "rest_calibration.py"
    calibration_worker = worker.parent / "bvh_calibration_probe.py"
    review_timeline = worker.parent / "bvh_review_timeline.py"
    motion_quality = worker.parent / "motion_quality.py"
    pose_environment = worker.parent / "pose_environment.py"
    source_rest_intake = worker.parent / "source_rest_intake.py"
    result_encoding = worker.parent / "result_encoding.py"
    channel_conversion = worker.parent / "channel_bone_conversion.py"
    private_renders = worker.parent / "private_review_render.py"
    fbx_source = worker.parent / "fbx_source.py"
    native_files=[worker.parent/name for name in ("native_reference.py","native_inputs.py","native_retarget.py","native_timeline.py","native_skin.py","native_anchor.py","native_corrective.py","native_skin_stack.py","native_review_reopen.py","native_playback_cache.py")]
    native_files += [worker.parent/name for name in ('face_policy.py', 'face_geometry.py',
                    'face_materials.py', 'face_operations.py', 'face_assets.py')]
    native_files += [worker.parent/name for name in ('hand_policy.py', 'hand_geometry.py', 'hand_assets.py')]
    native_files += [worker.parent/name for name in ('hand_master.py','hand_revision.py','hand_pose_checks.py')]
    native_files += [worker.parent/'hand_bounds.py']
    native_files += [worker.parent/name for name in ('expression_policy.py', 'expression_geometry.py',
                                                   'expression_prepare.py', 'expression_existing.py')]
    if (not worker.is_file() or worker.is_symlink()
            or not service.is_file() or service.is_symlink()
            or not preview.is_file() or preview.is_symlink()
            or not morphs.is_file() or morphs.is_symlink()
            or not refit.is_file() or refit.is_symlink()
            or not pose.is_file() or pose.is_symlink()
            or not timeline.is_file() or timeline.is_symlink()
            or not bvh_parser.is_file() or bvh_parser.is_symlink()
            or not bvh_probe.is_file() or bvh_probe.is_symlink()
            or not multi_chain.is_file() or multi_chain.is_symlink()
            or not calibration_math.is_file() or calibration_math.is_symlink()
            or not calibration_worker.is_file() or calibration_worker.is_symlink()
            or not review_timeline.is_file() or review_timeline.is_symlink()
            or not motion_quality.is_file() or motion_quality.is_symlink()
            or not pose_environment.is_file() or pose_environment.is_symlink()
            or not source_rest_intake.is_file() or source_rest_intake.is_symlink()
            or not result_encoding.is_file() or result_encoding.is_symlink()
            or not channel_conversion.is_file() or channel_conversion.is_symlink()
            or not private_renders.is_file() or private_renders.is_symlink()
            or not fbx_source.is_file() or fbx_source.is_symlink()
            or any(not path.is_file() or path.is_symlink() for path in native_files)):
        raise ValidationError(
            "Blender worker bridge is unavailable. Run from the repo checkout "
            "or a complete Windows alpha archive."
        )
    return worker


def generate_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    cancel: Event,
) -> HumanoidGeneration | CustomizedHumanoidBuild:
    if store.load().facial_parameters or store.load().expression is not None:
        from ucc.jobs.customized_humanoid import generate_customized_humanoid
        from ucc.jobs.face_discovery import discover_face_data
        script = bundled_worker_path()
        data = discover_face_data(store, blender_exe=blender_exe, worker_script=script, cancel=cancel)
        return generate_customized_humanoid(
            store, blender_exe=blender_exe, worker_script=script, mpfb_data_dir=data,
            expected_project_id=project_id, expected_revision=revision, cancel=cancel)
    return generate_humanoid(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        cancel=cancel, timeout_s=300,
    )


def preview_master_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
) -> MasterPreview:
    project=store.load()
    return preview_saved_master(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
        full_surface=bool(project.facial_parameters or project.parts or project.expression),
    )


def refit_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
) -> BodyRevisionResult | CustomizedHumanoidBuild:
    if store.load().facial_parameters or store.load().expression is not None:
        from ucc.jobs.customized_humanoid import apply_saved_customized_body_revision
        from ucc.jobs.face_discovery import discover_face_data
        script = bundled_worker_path()
        data = discover_face_data(store, blender_exe=blender_exe, worker_script=script, cancel=cancel)
        return apply_saved_customized_body_revision(
            store, blender_exe=blender_exe, worker_script=script, mpfb_data_dir=data,
            expected_project_id=project_id, expected_revision=revision,
            expected_master_blend=master_blend, cancel=cancel)
    return apply_saved_body_revision(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
    )


def inspect_rig_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
) -> SavedMasterPoseCheck:
    return check_saved_master_pose(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
    )


def inspect_timeline_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
) -> SavedTimelineDiagnostic:
    return check_saved_master_timeline(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
    )

def test_local_bvh_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    source_bvh: Path,
    permission: LicensePolicy,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
    multi_axis_profile: str | None = None,
    calibrate_rest_axes: bool = False,
    reviewed_mapping: list[dict[str, str]] | None = None,
    source_rest_profile: Path | None = None,
    audit_source_frames: bool = False,
    render_private_frames: bool = False,
) -> LocalBvhClipCheck:
    return check_selected_bvh(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        source_bvh=source_bvh, permission=permission,
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
        multi_axis_profile=multi_axis_profile,
        calibrate_rest_axes=calibrate_rest_axes,
        reviewed_mapping=reviewed_mapping,
        source_rest_profile=source_rest_profile,
        audit_source_frames=audit_source_frames,
        render_private_frames=render_private_frames,
    )
