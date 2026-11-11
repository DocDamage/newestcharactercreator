"""Two-process, project-bound evidence for an actual Blender keyed animation.

A fixed 1-second keyframed motion is evaluated at 5 frames on independent
private copies. This verifies Blender's timeline *evaluation*, not a user clip,
retargeting, viewport playback, engine export or subjective deformation quality.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event
from typing import Any

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore

from .master_preview import _digest, _master_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


class TimelineEvidenceError(ValidationError):
    """Untrusted or inconsistent animation timeline diagnostic."""


@dataclass(frozen=True, slots=True)
class SavedTimelineDiagnostic:
    project_id: str
    revision: int
    master_blend: str
    master_sha256: str
    evidence: dict[str, Any]
    worker_job_ids: tuple[str, str]


def _sha256(value: Any) -> bool:
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _cancelled(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("Keyframed timeline check cancelled; saved master unchanged")


def validate_timeline_response(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("status") != "REAL_BLENDER_KEYFRAMED_SKIN_TIMELINE_MEASURED":
        raise TimelineEvidenceError("No real Blender keyframed timeline was measured")
    if (value.get("fps") != 24 or type(value.get("fps")) is not int or
            value.get("duration_seconds") != 1.0 or
            value.get("keyframes") != [1, 13, 25] or
            value.get("action_keyframes_inserted") != 3 or
            value.get("action_assigned") is not True or
            value.get("timeline_interpolation_evaluated") is not True):
        raise TimelineEvidenceError("No confirmed one-second three-keyframe Blender action")
    if (not isinstance(value.get("selected_deform_bone"), str)
            or not 1 <= len(value["selected_deform_bone"]) <= 160 or
            type(value.get("rotation_axis_index")) is not int
            or value["rotation_axis_index"] not in (0, 1, 2) or
            value.get("rotation_degrees") != 20.0):
        raise TimelineEvidenceError("No valid fixed pose-bone animation")
    if (type(value.get("evaluated_vertex_count")) is not int
            or not 101 <= value["evaluated_vertex_count"] <= 250000
            or type(value.get("rig_bone_count")) is not int
            or value["rig_bone_count"] < 5 or
            not _sha256(value.get("rig_weight_sha256")) or
            not _sha256(value.get("rig_rest_sha256"))):
        raise TimelineEvidenceError("Missing real rig/mesh evidence")
    for flag, expected in {
        "source_master_saved": False,
        "original_animation_imported": False,
        "user_animation_playback_verified": False,
        "retargeting_verified": False,
        "engine_import_verified": False,
    }.items():
        if value.get(flag) is not expected:
            raise TimelineEvidenceError("Unsupported animation certification or master-save flag")
    if type(value.get("blender_version")) is not str or not value["blender_version"]:
        raise TimelineEvidenceError("Blender version missing")
    samples = value.get("sampled_frames")
    if not isinstance(samples, list) or len(samples) != 5:
        raise TimelineEvidenceError("Missing keyframed timeline samples")
    if [row.get("frame") for row in samples if isinstance(row, dict)] != [1, 7, 13, 19, 25]:
        raise TimelineEvidenceError("Timeline frames are incomplete or out of order")
    baseline = samples[0]["evaluated_sha256"]
    peak = samples[2]["evaluated_sha256"]
    if not _sha256(baseline) or not _sha256(peak) or baseline == peak:
        raise TimelineEvidenceError("Peak bone animation never changed evaluated mesh")
    if samples[4]["evaluated_sha256"] != baseline:
        raise TimelineEvidenceError("Last keyframe did not restore the original shape")
    for row in samples:
        if (type(row.get("evaluated_vertex_count")) is not int
                or row["evaluated_vertex_count"] != value["evaluated_vertex_count"]
                or type(row.get("moved_vertices")) is not int
                or not 0 <= row["moved_vertices"] <= value["evaluated_vertex_count"]
                or not _sha256(row.get("evaluated_sha256"))):
            raise TimelineEvidenceError("Bad frame-by-frame geometry proof")
        magnitude = row.get("max_displacement_local")
        if type(magnitude) not in (float, int) or not math.isfinite(magnitude) or magnitude < 0:
            raise TimelineEvidenceError("Bad frame-by-frame motion measurements")
    for row in samples[1:4]:
        if row["moved_vertices"] < 16 or row["max_displacement_local"] <= 1e-5:
            raise TimelineEvidenceError("An intermediate frame did not deform the mesh")
    for row in (samples[1], samples[3]):
        if row["evaluated_sha256"] in (baseline, peak):
            raise TimelineEvidenceError("Interpolated timeline frame missing")
    if (samples[0]["moved_vertices"] or samples[4]["moved_vertices"]
            or max(samples[0]["max_displacement_local"],
                   samples[4]["max_displacement_local"]) > 2e-6):
        raise TimelineEvidenceError("Neutral animation frames did not restore base mesh")
    return dict(value)


def compare_timelines(first: Any, second: Any) -> dict[str, Any]:
    a = validate_timeline_response(first)
    b = validate_timeline_response(second)
    for key in ("selected_deform_bone", "rotation_axis_index", "rotation_degrees",
                "keyframes", "fps", "evaluated_vertex_count", "rig_bone_count",
                "rig_weight_sha256", "rig_rest_sha256", "blender_version"):
        if a[key] != b[key]:
            raise TimelineEvidenceError("Blender timeline workers disagree on " + key)
    for one, two in zip(a["sampled_frames"], b["sampled_frames"]):
        for key in ("frame", "evaluated_sha256", "evaluated_vertex_count",
                    "moved_vertices"):
            if one[key] != two[key]:
                raise TimelineEvidenceError("Blender timeline workers disagree on frame " + key)
        if abs(one["max_displacement_local"] - two["max_displacement_local"]) > 1e-6:
            raise TimelineEvidenceError("Blender timeline measurements are inconsistent")
    return a


def check_saved_master_timeline(
    store: ProjectStore, *,
    blender_exe: Path,
    worker_script: Path,
    expected_project_id: str,
    expected_revision: int,
    expected_master_blend: str,
    cancel: Event | None = None,
    timeout_s: float = 300,
) -> SavedTimelineDiagnostic:
    """Double-process fixed keyframe proof on an unchanged saved Blender master."""
    original = store.load()
    if (original.project_id != expected_project_id
            or original.revision != expected_revision
            or original.master_blend != expected_master_blend):
        raise ProjectConflict("Project changed before timeline verification")
    if original.family != "humanoid.v1" or original.base_provider != "mpfb":
        raise ValidationError("Timeline diagnostic supports MPFB humanoid projects only")
    if type(timeout_s) not in (float, int) or not .05 <= timeout_s <= 3600:
        raise ValidationError("Invalid Blender timeline timeout")
    executable, bridge = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("Select an existing Blender executable")
    if bridge.is_symlink() or not bridge.is_file():
        raise ValidationError("Bundled Blender worker is missing")
    _cancelled(cancel)
    master, expected_digest = _master_file(store, expected_master_blend)
    if _digest(master, cancel) != expected_digest:
        raise ProjectStorageError("Saved Blender master SHA-256 mismatch")
    jobs = store.root / ".ucc-jobs"
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError("Private Blender job directory is redirected")

    runner = BlenderJobRunner(executable, jobs, bridge)
    results, identifiers = [], []
    for _ in range(2):
        _cancelled(cancel)
        job = JobRequest.new("verify_keyframed_timeline", input_project="candidate.blend")
        result, folder = runner.run(
            job, staged_inputs={"candidate.blend": master},
            cancel=cancel, timeout_s=timeout_s,
        )
        copy = folder / "candidate.blend"
        if (copy.is_symlink() or not copy.is_file()
                or _digest(copy, cancel) != expected_digest
                or _digest(master, cancel) != expected_digest):
            raise ProjectStorageError("Timeline used a changed master copy")
        results.append(validate_timeline_response(result.details))
        identifiers.append(job.job_id)
    observed = compare_timelines(results[0], results[1])
    _cancelled(cancel)
    latest = store.load()
    if (latest.project_id != expected_project_id
            or latest.revision != expected_revision
            or latest.master_blend != expected_master_blend
            or _digest(master, cancel) != expected_digest):
        raise ProjectConflict("Project changed during Blender timeline test")
    return SavedTimelineDiagnostic(
        original.project_id, original.revision, expected_master_blend,
        expected_digest, observed, (identifiers[0], identifiers[1]),
    )
