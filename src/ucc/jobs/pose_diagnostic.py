"""Project-bound, read-only double-process Blender skin deformation diagnostic.

A real pose-bone rotation is applied only to copies of a saved master in
private worker job folders. Two independent Blender subprocesses must agree.
This validates one controlled static deformation response, not animation,
retargeting, visual skinning quality or target-engine imports.
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


class PoseEvidenceError(ValidationError):
    """A Blender pose response was insufficient or inconsistent."""


@dataclass(frozen=True, slots=True)
class SavedMasterPoseCheck:
    project_id: str
    revision: int
    master_blend: str
    master_sha256: str
    evidence: dict[str, Any]
    worker_job_ids: tuple[str, str]

    @property
    def animation_playback_verified(self) -> bool:
        return False


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("Rig pose check cancelled; project and master are unchanged")


def _sha_string(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def validate_pose_evidence(details: Any) -> dict[str, Any]:
    """Reject fabricated status, invalid measurements, or exported/edited outcomes."""
    if not isinstance(details, dict):
        raise PoseEvidenceError("Blender pose check result must be an object")
    if details.get("status") != "REAL_STATIC_SKIN_POSE_MOVEMENT_MEASURED":
        raise PoseEvidenceError("No real evaluated skin movement reported")
    bone = details.get("selected_deform_bone")
    if not isinstance(bone, str) or not bone or len(bone) > 160:
        raise PoseEvidenceError("No valid weighted deform bone was selected")
    axis = details.get("rotation_axis_index")
    angle = details.get("rotation_degrees")
    count = details.get("moved_vertex_count")
    total = details.get("evaluated_vertex_count")
    maximum = details.get("max_vertex_displacement_local")
    bones = details.get("rig_bone_count")
    if (type(axis) is not int or axis not in (0, 1, 2) or
            type(angle) not in (int, float) or angle != 20.0):
        raise PoseEvidenceError("Unexpected pose test angle or rotation axis")
    if (type(count) is not int or type(total) is not int or
            not 16 <= count <= total <= 250_000):
        raise PoseEvidenceError("No substantial measured vertex movement")
    if (type(maximum) not in (int, float) or not math.isfinite(maximum)
            or not 1e-5 < maximum <= 1e6):
        raise PoseEvidenceError("Pose movement magnitude invalid")
    if type(bones) is not int or bones < 5:
        raise PoseEvidenceError("No substantial bound skeleton was measured")
    for field in ("neutral_evaluated_sha256", "posed_evaluated_sha256",
                  "restored_evaluated_sha256", "rig_weight_sha256",
                  "rig_rest_sha256"):
        if not _sha_string(details.get(field)):
            raise PoseEvidenceError(f"Missing checked {field} from Blender")
    if (details["neutral_evaluated_sha256"] ==
            details["posed_evaluated_sha256"]):
        raise PoseEvidenceError("Bone movement did not change evaluated mesh geometry")
    if (details["restored_evaluated_sha256"] !=
            details["neutral_evaluated_sha256"]):
        raise PoseEvidenceError("Test did not return to the original pose")
    expected_flags = {
        "rig_binding_verified": True,
        "source_master_saved": False,
        "animation_clip_playback_verified": False,
        "retargeting_verified": False,
        "engine_import_verified": False,
    }
    if any(details.get(k) is not v for k, v in expected_flags.items()):
        raise PoseEvidenceError("Unexpected rig/certification or master-save flag")
    if not isinstance(details.get("blender_version"), str) or not details["blender_version"]:
        raise PoseEvidenceError("Missing Blender version evidence")
    return dict(details)


def verify_repeated_pose(first: Any, second: Any) -> dict[str, Any]:
    """Require matching geometry, rig and selected test bone in two Blender runs."""
    a = validate_pose_evidence(first)
    b = validate_pose_evidence(second)
    for key in (
        "selected_deform_bone", "rotation_axis_index", "rotation_degrees",
        "moved_vertex_count", "evaluated_vertex_count", "rig_bone_count",
        "neutral_evaluated_sha256", "posed_evaluated_sha256",
        "restored_evaluated_sha256", "rig_weight_sha256", "rig_rest_sha256",
        "blender_version",
    ):
        if a[key] != b[key]:
            raise PoseEvidenceError(
                "Independent Blender processes disagreed on " + key
            )
    if abs(a["max_vertex_displacement_local"] -
           b["max_vertex_displacement_local"]) > 1e-6:
        raise PoseEvidenceError("Independent Blender measurements were inconsistent")
    return a


def check_saved_master_pose(
    store: ProjectStore,
    *,
    blender_exe: Path,
    worker_script: Path,
    expected_project_id: str,
    expected_revision: int,
    expected_master_blend: str,
    cancel: Event | None = None,
    timeout_s: float = 300,
) -> SavedMasterPoseCheck:
    """Probe two independent copies of a saved rig; never write its master or JSON."""
    original = store.load()
    if (original.project_id != expected_project_id or
            original.revision != expected_revision or
            original.master_blend != expected_master_blend):
        raise ProjectConflict("Project changed before the saved-rig diagnostic")
    if original.family != "humanoid.v1" or original.base_provider != "mpfb":
        raise ValidationError("Pose diagnostic only supports existing MPFB humanoids")
    if type(timeout_s) not in (int, float) or not 0.05 <= timeout_s <= 3600:
        raise ValidationError("Invalid Blender pose diagnostic timeout")
    executable, bridge = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("Choose an existing installed Blender executable")
    if bridge.is_symlink() or not bridge.is_file():
        raise ValidationError("Blender worker bridge is unavailable or redirected")
    _check_cancel(cancel)
    master, digest = _master_file(store, expected_master_blend)
    if _digest(master, cancel) != digest:
        raise ProjectStorageError("Saved Blender master failed SHA-256 verification")
    jobs = store.root / ".ucc-jobs"
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError("Private Blender work directory is redirected")

    worker = BlenderJobRunner(executable, jobs, bridge)
    answers = []
    identifiers = []
    for _ in range(2):
        _check_cancel(cancel)
        job = JobRequest.new("verify_skin_deformation", input_project="candidate.blend")
        response, directory = worker.run(
            job, staged_inputs={"candidate.blend": master},
            timeout_s=timeout_s, cancel=cancel,
        )
        staged = directory / "candidate.blend"
        if (staged.is_symlink() or not staged.is_file()
                or _digest(staged, cancel) != digest
                or _digest(master, cancel) != digest):
            raise ProjectStorageError("Pose check used modified Blender master bytes")
        answers.append(validate_pose_evidence(response.details))
        identifiers.append(job.job_id)
    result = verify_repeated_pose(answers[0], answers[1])
    _check_cancel(cancel)

    current = store.load()
    if (current.project_id != expected_project_id or
            current.revision != expected_revision or
            current.master_blend != expected_master_blend or
            _digest(master, cancel) != digest):
        raise ProjectConflict("Project changed during pose test; discard stale evidence")
    return SavedMasterPoseCheck(
        original.project_id, original.revision, expected_master_blend, digest,
        result, (identifiers[0], identifiers[1]),
    )
