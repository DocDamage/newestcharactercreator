"""Local, permission-reviewed BVH motion diagnostic on the current MPFB master.

One explicitly chosen file is parsed/hashed locally, copied to a private job,
keyed on one exactly named weighted bone and evaluated twice in real Blender.
No external file download, AI/cloud, general retargeting or new master commit.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event
from typing import Any

from ucc.animations.metadata import inspect_bvh, AnimationMetadataError
from ucc.animations.review_mapping import validate_review_mapping
from ucc.animations.source_rest_frames import read_source_rest_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import AssetPolicyError, LicensePolicy

from .master_preview import _digest, _master_file
from .multibone_evidence import (
    compare_multibone_evidence, validate_multibone_evidence,
)
from .calibrated_evidence import (
    compare_calibrated_evidence, validate_calibrated_evidence,
)
from .reviewed_evidence import compare_reviewed_evidence, validate_reviewed_evidence
from .protocol import JobRequest
from .runner import BlenderJobRunner


class BvhPreviewEvidenceError(ValidationError):
    """The actual source-driven animation has insufficient Blender evidence."""


@dataclass(frozen=True, slots=True)
class LocalBvhClipCheck:
    project_id: str
    revision: int
    master_blend: str
    master_sha256: str
    clip_sha256: str
    clip_name: str
    evidence: dict[str, Any]
    worker_job_ids: tuple[str, str]
    permission_evidence: str = "USER_CONFIRMED_REVIEWED_LOCAL_ONLY"
    private_visual_review_blend: str | None = None

    @property
    def retargeting_verified(self) -> bool:
        return False


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("Local BVH preview cancelled; original files unchanged")


def _sha(s: Any) -> bool:
    return (type(s) is str and len(s) == 64
            and all(c in "0123456789abcdef" for c in s))


def validate_local_bvh_report(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") != "REAL_LOCAL_BVH_SOURCE_DRIVEN_MESH_MOTION_MEASURED":
        raise BvhPreviewEvidenceError("Worker did not prove real BVH source-driven mesh motion")
    if (raw.get("mapping_method") != "DIRECT_NAME_ROTATION_DELTA_NO_REST_CALIBRATION" or
            not isinstance(raw.get("source_bone"), str) or not raw["source_bone"] or
            not isinstance(raw.get("target_bone"), str) or not raw["target_bone"] or
            raw["source_bone"].casefold() != raw["target_bone"].casefold()):
        raise BvhPreviewEvidenceError("BVH source bone mapping was not exact")
    frames = raw.get("source_frame_count")
    if type(frames) is not int or not 5 <= frames <= 240:
        raise BvhPreviewEvidenceError("Unsupported local BVH frame count")
    dt = raw.get("source_frame_time")
    if type(dt) not in (float, int) or not math.isfinite(dt) or not .005 <= dt <= .5:
        raise BvhPreviewEvidenceError("Invalid BVH timing")
    if raw.get("keyframes_inserted") != frames or raw.get("frame_sample_count") != 5:
        raise BvhPreviewEvidenceError("Blender did not key all source motion frames")
    if (type(raw.get("distinct_geometry_states")) is not int or
            raw["distinct_geometry_states"] < 3 or
            type(raw.get("rig_bone_count")) is not int or raw["rig_bone_count"] < 5):
        raise BvhPreviewEvidenceError("Real source motion and rig evidence are missing")
    for key in ("source_sha256", "rig_weight_sha256", "rig_rest_sha256"):
        if not _sha(raw.get(key)):
            raise BvhPreviewEvidenceError("Missing SHA-256 source or rig evidence")
    flags = {
        "source_translation_ignored": True,
        "source_orientation_calibrated": False,
        "user_clip_evaluated_in_blender": True,
        "retargeting_verified": False,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }
    if any(raw.get(key) is not value for key, value in flags.items()):
        raise BvhPreviewEvidenceError("Unsupported BVH completion or certification flag")
    if not isinstance(raw.get("blender_version"), str) or not raw["blender_version"]:
        raise BvhPreviewEvidenceError("Blender version is missing")
    samples = raw.get("sampled_frames")
    if not isinstance(samples, list) or len(samples) != 5 or not all(
        isinstance(row, dict) for row in samples
    ):
        raise BvhPreviewEvidenceError("Expected exactly five real source animation samples")
    source_frames = [row.get("frame") for row in samples]
    if (type(source_frames[0]) is not int or source_frames[0] != 1 or
            type(source_frames[-1]) is not int or source_frames[-1] != frames or
            any(type(n) is not int for n in source_frames) or
            source_frames != sorted(set(source_frames))):
        raise BvhPreviewEvidenceError("Sample frames are not ordered/unique")
    baseline = samples[0]["evaluated_sha256"]
    if not _sha(baseline):
        raise BvhPreviewEvidenceError("Missing valid base mesh frame hash")
    hashes = set()
    motion_count = 0
    vertex_count = samples[0].get("evaluated_vertex_count")
    if type(vertex_count) is not int or not 101 <= vertex_count <= 250000:
        raise BvhPreviewEvidenceError("Invalid evaluated mesh vertex count")
    for row in samples:
        moved = row.get("moved_vertices")
        maximum = row.get("max_displacement_local")
        digest = row.get("evaluated_sha256")
        if (type(row.get("evaluated_vertex_count")) is not int or
                row["evaluated_vertex_count"] != vertex_count or
                type(moved) is not int or not 0 <= moved <= vertex_count or
                type(maximum) not in (int, float) or
                not math.isfinite(maximum) or maximum < 0 or not _sha(digest)):
            raise BvhPreviewEvidenceError("Invalid sample geometry/timing report")
        hashes.add(digest)
        if moved >= 16 and maximum > .00001:
            motion_count += 1
    if len(hashes) != raw["distinct_geometry_states"] or len(hashes) < 3 or motion_count < 2:
        raise BvhPreviewEvidenceError("BVH clip did not produce real distinct skinned frames")
    if samples[0]["moved_vertices"] or samples[0]["max_displacement_local"] > .000002:
        raise BvhPreviewEvidenceError("First BVH frame must be the sampled baseline")
    return dict(raw)


def compare_local_bvh_reports(first: Any, second: Any) -> dict[str, Any]:
    a, b = validate_local_bvh_report(first), validate_local_bvh_report(second)
    for key in ("source_sha256", "source_bone", "target_bone", "mapping_method",
                "source_frame_count", "source_frame_time", "keyframes_inserted",
                "distinct_geometry_states", "rig_bone_count", "rig_weight_sha256",
                "rig_rest_sha256", "blender_version"):
        if a[key] != b[key]:
            raise BvhPreviewEvidenceError("Independent source BVH workers disagree on " + key)
    for s, t in zip(a["sampled_frames"], b["sampled_frames"]):
        for key in ("frame", "moved_vertices", "evaluated_vertex_count", "evaluated_sha256"):
            if s[key] != t[key]:
                raise BvhPreviewEvidenceError("Two Blender processes disagreed on source motion")
        if abs(s["max_displacement_local"] - t["max_displacement_local"]) > 1e-6:
            raise BvhPreviewEvidenceError("BVH motion displacement was not reproducible")
    return a


def check_selected_bvh(
    store: ProjectStore, *,
    blender_exe: Path,
    worker_script: Path,
    source_bvh: Path,
    permission: LicensePolicy,
    expected_project_id: str,
    expected_revision: int,
    expected_master_blend: str,
    cancel: Event | None = None,
    timeout_s: float = 300,
    multi_axis_profile: str | None = None,
    calibrate_rest_axes: bool = False,
    reviewed_mapping: list[dict[str, str]] | None = None,
    source_rest_profile: Path | None = None,
) -> LocalBvhClipCheck:
    """Run two Blender jobs; optionally measure source-to-target rest rotation axes."""

    if source_rest_profile is not None and reviewed_mapping is None:
        raise ValidationError("Source rest-frame intake requires explicit reviewed mapping")
    if reviewed_mapping is not None:
        if not calibrate_rest_axes or multi_axis_profile is None:
            raise ValidationError("Manual mapping requires calibrated source axes")
        reviewed_mapping = validate_review_mapping(reviewed_mapping)
    if type(calibrate_rest_axes) is not bool or (
        calibrate_rest_axes and multi_axis_profile is None
    ):
        raise ValidationError("Calibration requires explicit source up-axis profile")
    if (multi_axis_profile is not None and
            multi_axis_profile not in {"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"}):
        raise ValidationError("Choose an explicit supported BVH source up-axis profile")
    allowed, reason = permission.allow("local_preview")
    if not allowed:
        raise AssetPolicyError("Selected BVH is blocked for local preview: " + reason)
    if type(timeout_s) not in (float, int) or not .05 <= timeout_s <= 3600:
        raise ValidationError("Invalid BVH motion worker timeout")
    snapshot = store.load()
    if (snapshot.project_id != expected_project_id or
            snapshot.revision != expected_revision or
            snapshot.master_blend != expected_master_blend):
        raise ProjectConflict("Saved MPFB character changed before BVH preview")
    if snapshot.family != "humanoid.v1" or snapshot.base_provider != "mpfb":
        raise ValidationError("Local BVH preview requires an MPFB humanoid")
    executable, bridge = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("Choose an installed regular Blender executable")
    if bridge.is_symlink() or not bridge.is_file():
        raise ValidationError("UCC Blender worker file is missing or redirected")
    _check_cancel(cancel)
    clip = Path(source_bvh)
    if clip.suffix.lower() != ".bvh" or clip.is_symlink() or not clip.is_file():
        raise AnimationMetadataError("Explicitly select an existing regular BVH clip")
    parsed = inspect_bvh(clip)
    if (parsed.status != "METADATA_EXTRACTED" or len(parsed.clips) != 1 or
            parsed.clips[0].frame_count is None or
            not 5 <= parsed.clips[0].frame_count <= 240):
        raise AnimationMetadataError("BVH preview supports one complete clip with 5–240 frames")
    source_hash = _digest(clip, cancel)
    rest_profile, rest_sha = None, None
    rest_path = Path(source_rest_profile) if source_rest_profile is not None else None
    if rest_path is not None:
        _check_cancel(cancel)
        rest_profile, rest_sha = read_source_rest_profile(
            rest_path, source_hash, multi_axis_profile, reviewed_mapping,
        )
        _check_cancel(cancel)
    master, master_hash = _master_file(store, expected_master_blend)
    if _digest(master, cancel) != master_hash:
        raise ProjectStorageError("Saved Blender master digest mismatch")
    jobs = store.root / ".ucc-jobs"
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError("Private Blender jobs path is redirected")
    runner = BlenderJobRunner(executable, jobs, bridge)
    reports, ids = [], []
    visual_review_path = None
    for _ in range(2):
        _check_cancel(cancel)
        options = ({"axis_profile": multi_axis_profile}
                   if multi_axis_profile is not None else {})
        if reviewed_mapping is not None:
            options["reviewed_mapping"] = reviewed_mapping
        staged_inputs = {"candidate.blend": master, "motion.bvh": clip}
        if rest_path is not None:
            options["source_rest_profile_sha256"] = rest_sha
            staged_inputs["source_rest_frames.json"] = rest_path
        operation = (
            "verify_reviewed_bvh_chain" if reviewed_mapping is not None else
            "verify_calibrated_bvh_chain" if calibrate_rest_axes else
            "verify_multi_bvh_chain" if multi_axis_profile is not None else
            "verify_local_bvh_motion"
        )
        request = JobRequest.new(
            operation, input_project="candidate.blend", options=options,
        )
        result, folder = runner.run(
            request, timeout_s=timeout_s, cancel=cancel,
            staged_inputs=staged_inputs,
        )
        if rest_path is not None:
            staged_rest = folder / "source_rest_frames.json"
            if (staged_rest.is_symlink() or not staged_rest.is_file() or
                    rest_path.is_symlink() or not rest_path.is_file() or
                    _digest(staged_rest, cancel) != rest_sha or _digest(rest_path, cancel) != rest_sha):
                raise ProjectStorageError("Source rest profile changed during Blender intake")
        staged_model, staged_clip = folder / "candidate.blend", folder / "motion.bvh"
        if (staged_model.is_symlink() or staged_clip.is_symlink() or
                not staged_model.is_file() or not staged_clip.is_file() or
                _digest(staged_model, cancel) != master_hash or
                _digest(staged_clip, cancel) != source_hash or
                _digest(master, cancel) != master_hash or
                _digest(clip, cancel) != source_hash):
            raise ProjectStorageError("Local clip or MPFB master changed during BVH preview")
        evidence = (
            validate_reviewed_evidence(
                result.details, multi_axis_profile, reviewed_mapping,
                source_rest_profile=rest_profile, source_rest_profile_sha256=rest_sha,
            ) if reviewed_mapping is not None else
            validate_calibrated_evidence(
                result.details, axis_profile=multi_axis_profile,
            ) if calibrate_rest_axes else
            validate_multibone_evidence(
                result.details, axis_profile=multi_axis_profile,
            ) if multi_axis_profile is not None else
            validate_local_bvh_report(result.details)
        )
        if evidence["source_sha256"] != source_hash or evidence["source_frame_count"] != parsed.clips[0].frame_count:
            raise BvhPreviewEvidenceError("BVH metadata/bytes do not match Blender source")
        if reviewed_mapping is not None:
            artifact = folder / "review_motion.blend"
            record = evidence["visual_review_blend"]
            if (artifact.is_symlink() or not artifact.is_file() or
                    artifact.stat().st_size != record["bytes"] or
                    _digest(artifact, cancel) != record["sha256"]):
                raise ProjectStorageError("Private Blender Action review file failed SHA-256")
            if visual_review_path is None:
                visual_review_path = str(artifact)
        reports.append(evidence)
        ids.append(request.job_id)
    observed = (
        compare_reviewed_evidence(
            reports[0], reports[1], multi_axis_profile, reviewed_mapping,
            source_rest_profile=rest_profile, source_rest_profile_sha256=rest_sha,
        ) if reviewed_mapping is not None else
        compare_calibrated_evidence(reports[0], reports[1], multi_axis_profile)
        if calibrate_rest_axes else
        compare_multibone_evidence(reports[0], reports[1], multi_axis_profile)
        if multi_axis_profile is not None else
        compare_local_bvh_reports(reports[0], reports[1])
    )
    _check_cancel(cancel)
    newest = store.load()
    if (newest.project_id != expected_project_id or
            newest.revision != expected_revision or
            newest.master_blend != expected_master_blend or
            _digest(master, cancel) != master_hash or
            _digest(clip, cancel) != source_hash):
        raise ProjectConflict("Saved master/source was changed during BVH preview")
    if rest_path is not None and (rest_path.is_symlink() or not rest_path.is_file() or
                                  _digest(rest_path, cancel) != rest_sha):
        raise ProjectConflict("Source rest profile changed before diagnostic completion")
    return LocalBvhClipCheck(
        snapshot.project_id, snapshot.revision, expected_master_blend,
        master_hash, source_hash, parsed.clips[0].name,
        observed, (ids[0], ids[1]),
        private_visual_review_blend=visual_review_path,
    )
