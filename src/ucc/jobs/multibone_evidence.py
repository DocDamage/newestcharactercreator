"""Strict version-1 evidence for a real 2–4 bone source-driven BVH chain.

No Blender or Qt imports. Parent, rest-direction, axis conversion and
per-bone movement must be measured, not inferred from matching names.
The result is explicitly NOT full bone-roll/retargeting certification.
"""
from __future__ import annotations

import math
from typing import Any

from ucc.core.errors import ValidationError


class MultiBoneEvidenceError(ValidationError):
    """Worker did not prove an unambiguous actual multi-bone motion chain."""


def _hex64(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_multibone_evidence(details: Any, *, axis_profile: str) -> dict[str, Any]:
    if not isinstance(details, dict) or details.get("status") != (
        "REAL_MPFB_MULTIBONE_BVH_CHAIN_GEOMETRY_MEASURED"
    ):
        raise MultiBoneEvidenceError("No real multi-bone MPFB source motion was reported")
    if axis_profile not in {"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"} or (
        details.get("axis_profile") != axis_profile
    ):
        raise MultiBoneEvidenceError("Worker used the wrong explicit BVH axis preset")
    if (details.get("rest_direction_alignment_verified") is not True or
            details.get("rest_scale_consistency_verified") is not True or
            details.get("bone_roll_calibrated") is not False or
            details.get("source_orientation_calibrated") is not False or
            details.get("retargeting_verified") is not False):
        raise MultiBoneEvidenceError("Unsafe rest mapping or unsupported retarget claim")
    if not _finite(details.get("relative_rest_length_scale")) or not (
        1e-5 < details["relative_rest_length_scale"] < 1e5
    ):
        raise MultiBoneEvidenceError("Invalid source/target rest-length scale")
    flags = {
        "source_translation_ignored": True,
        "user_clip_evaluated_in_blender": True,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }
    if any(details.get(k) is not v for k, v in flags.items()):
        raise MultiBoneEvidenceError("Multi-bone evidence claimed unsafe export/mutation")
    for key in ("source_sha256", "rig_weight_sha256", "rig_rest_sha256"):
        if not _hex64(details.get(key)):
            raise MultiBoneEvidenceError("Missing real SHA-256 source/rig evidence")
    count = details.get("mapped_bone_count")
    mapped = details.get("mapped_bones")
    per_bone = details.get("per_bone_deformation")
    if (type(count) is not int or not 2 <= count <= 4 or
            not isinstance(mapped, list) or len(mapped) != count or
            not isinstance(per_bone, list) or len(per_bone) != count):
        raise MultiBoneEvidenceError("Expected exactly 2–4 mapped and moving bones")
    sources, targets = set(), set()
    for idx, (bone, movement) in enumerate(zip(mapped, per_bone)):
        if not isinstance(bone, dict) or not isinstance(movement, dict):
            raise MultiBoneEvidenceError("Invalid per-bone chain evidence")
        src, target, parent = bone.get("source"), bone.get("target"), bone.get("parent")
        if (type(src) is not str or type(target) is not str or
                not 1 <= len(src) <= 128 or not 1 <= len(target) <= 128 or
                src.casefold() != target.casefold() or
                src.casefold() in sources or target.casefold() in targets):
            raise MultiBoneEvidenceError("Source-to-target bone names are ambiguous")
        sources.add(src.casefold())
        targets.add(target.casefold())
        if idx == 0:
            if parent is not None or bone.get("rest_alignment_cos") is not None:
                raise MultiBoneEvidenceError("First chain member must be source root")
        else:
            if (type(parent) is not str or
                    parent.casefold() != mapped[idx - 1]["source"].casefold()
                    or not _finite(bone.get("rest_alignment_cos"))
                    or not 0.90 <= bone["rest_alignment_cos"] <= 1.00001):
                raise MultiBoneEvidenceError("BVH source and target parent/rest alignment unproved")
        if (type(bone.get("weighted_vertices")) is not int or
                bone["weighted_vertices"] < 16 or
                not _finite(bone.get("max_delta_degrees")) or
                not 1 <= bone["max_delta_degrees"] <= 45):
            raise MultiBoneEvidenceError("Insufficient independent bone weight/motion")
        if (movement.get("bone") != target or
                type(movement.get("moved_vertices")) is not int or
                movement["moved_vertices"] < 16 or
                not _finite(movement.get("max_displacement_local")) or
                movement["max_displacement_local"] <= 1e-5):
            raise MultiBoneEvidenceError("Individual bone did not drive real MPFB geometry")
    frames = details.get("source_frame_count")
    dt = details.get("source_frame_time")
    if (type(frames) is not int or not 5 <= frames <= 240 or
            not _finite(dt) or not 0.005 <= dt <= 0.5 or
            type(details.get("keyframes_inserted")) is not int or
            details["keyframes_inserted"] != frames * count or
            details.get("frame_sample_count") != 5):
        raise MultiBoneEvidenceError("Source frame/time or Blender Action count mismatch")
    if (type(details.get("rig_bone_count")) is not int or
            details["rig_bone_count"] < 5 or
            type(details.get("blender_version")) is not str or
            not details["blender_version"]):
        raise MultiBoneEvidenceError("Real Blender rig identity is not established")
    samples = details.get("sampled_frames")
    if not isinstance(samples, list) or len(samples) != 5 or not all(
        isinstance(row, dict) for row in samples
    ):
        raise MultiBoneEvidenceError("Five real Blender timeline samples required")
    frame_ids = [row.get("frame") for row in samples]
    if (any(type(x) is not int for x in frame_ids) or
            frame_ids[0] != 1 or frame_ids[-1] != frames or
            frame_ids != sorted(set(frame_ids))):
        raise MultiBoneEvidenceError("BVH sampled frames are incomplete or unordered")
    total = samples[0].get("evaluated_vertex_count")
    if type(total) is not int or not 101 <= total <= 250000:
        raise MultiBoneEvidenceError("Invalid actual evaluated human vertex count")
    hashes = set()
    changed_count = 0
    for row in samples:
        moved, maximum, digest = (
            row.get("moved_vertices"),
            row.get("max_displacement_local"),
            row.get("evaluated_sha256"),
        )
        if (type(row.get("evaluated_vertex_count")) is not int or
                row["evaluated_vertex_count"] != total or
                type(moved) is not int or not 0 <= moved <= total or
                not _finite(maximum) or not 0 <= maximum <= 1e6 or
                not _hex64(digest)):
            raise MultiBoneEvidenceError("Invalid evaluated Blender frame geometry")
        hashes.add(digest)
        if moved >= 16 and maximum > 1e-5:
            changed_count += 1
    if (type(details.get("distinct_geometry_states")) is not int or
            details["distinct_geometry_states"] != len(hashes) or
            len(hashes) < 3 or changed_count < 2 or
            samples[0]["moved_vertices"] != 0 or
            samples[0]["max_displacement_local"] > 2e-6):
        raise MultiBoneEvidenceError("No reproducible distinct multi-bone frame movement")
    return dict(details)


def compare_multibone_evidence(first: Any, second: Any,
                               axis_profile: str) -> dict[str, Any]:
    a = validate_multibone_evidence(first, axis_profile=axis_profile)
    b = validate_multibone_evidence(second, axis_profile=axis_profile)
    for key in (
        "source_sha256", "axis_profile", "relative_rest_length_scale",
        "source_frame_count", "source_frame_time", "mapped_bone_count",
        "mapped_bones", "per_bone_deformation", "keyframes_inserted",
        "rig_weight_sha256", "rig_rest_sha256", "rig_bone_count",
        "blender_version", "distinct_geometry_states",
    ):
        if a[key] != b[key]:
            raise MultiBoneEvidenceError("Two Blender workers disagreed on " + key)
    for one, two in zip(a["sampled_frames"], b["sampled_frames"]):
        for key in ("frame", "evaluated_sha256", "evaluated_vertex_count",
                    "moved_vertices"):
            if one[key] != two[key]:
                raise MultiBoneEvidenceError("Two real Blender timeline frames disagreed")
        if abs(one["max_displacement_local"] -
               two["max_displacement_local"]) > 1e-6:
            raise MultiBoneEvidenceError("Two workers measured inconsistent mesh movement")
    return a
