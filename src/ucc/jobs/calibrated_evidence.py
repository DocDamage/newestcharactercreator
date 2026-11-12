"""Strict, honest evidence from an actual BVH-to-MPFB rest-space calibration.

The job establishes a narrow 2–4 joint quaternion-axis conversion, not
automatic full-body retargeting, visual quality, imported user-owned assets,
or game-engine playback. Two independent Blender workers must agree.
"""
from __future__ import annotations

import math
from typing import Any

from ucc.core.errors import ValidationError


class CalibratedEvidenceError(ValidationError):
    """Insufficient source/target bone-roll/rest-space evidence."""


def _hex(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_calibrated_evidence(raw: Any, axis_profile: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") != (
        "REAL_BVH_REST_AXES_CALIBRATED_MESH_MOTION"
    ):
        raise CalibratedEvidenceError("No real calibrated BVH motion was proved")
    if axis_profile not in {"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"} or raw.get("axis_profile") != axis_profile:
        raise CalibratedEvidenceError("Source BVH up-axis did not match user-selected preset")
    if (raw.get("rest_axes_calibrated") is not True or
            raw.get("bone_roll_independently_verified") is not False or
            raw.get("real_quaternion_action_inserted") is not True):
        raise CalibratedEvidenceError("Unproven calibrated rest frame or Action")
    for name in ("source_sha256", "source_to_target_axes_sha256",
                 "rig_weight_sha256", "rig_rest_sha256"):
        if not _hex(raw.get(name)):
            raise CalibratedEvidenceError("Missing checked calibration/source/rig digest: " + name)
    for key, expected in {
        "source_translation_ignored": True,
        "user_clip_evaluated_in_blender": True,
        "retargeting_verified": False,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }.items():
        if raw.get(key) is not expected:
            raise CalibratedEvidenceError("Unexpected export, approval or source mutation claim")
    count = raw.get("mapped_bone_count")
    bones, movements, axes = (
        raw.get("mapped_bones"), raw.get("per_bone_deformation"),
        raw.get("local_axis_proofs"),
    )
    if (type(count) is not int or not 2 <= count <= 4 or
            any(not isinstance(x, list) or len(x) != count
                for x in (bones, movements, axes))):
        raise CalibratedEvidenceError("Exactly two to four calibrated bones are needed")
    landmarks = raw.get("rest_landmark_count")
    residuals = raw.get("rest_residual_degrees")
    pair = raw.get("rest_reference_pair")
    max_residual = raw.get("max_rest_residual_degrees")
    if (type(landmarks) is not int or landmarks != count or
            not isinstance(residuals, list) or len(residuals) != landmarks or
            not isinstance(pair, list) or len(pair) != 2 or
            any(type(idx) is not int or not 0 <= idx < landmarks for idx in pair)
            or pair[0] == pair[1] or
            any(not _number(x) or not 0 <= x <= 5.0 for x in residuals) or
            not _number(max_residual) or
            abs(max(residuals) - max_residual) > 1e-5):
        raise CalibratedEvidenceError("Insufficient two-direction measured rest-frame fit")

    seen = set()
    for i, (b, movement, proof) in enumerate(zip(bones, movements, axes)):
        if not all(isinstance(item, dict) for item in (b, movement, proof)):
            raise CalibratedEvidenceError("Per-bone evidence must be an object")
        src, dst = b.get("source"), b.get("target")
        if (type(src) is not str or type(dst) is not str or
                not src or len(src) > 128 or not dst or len(dst) > 128 or
                src.casefold() != dst.casefold() or dst.casefold() in seen):
            raise CalibratedEvidenceError("Ambiguous exact source/target bone mapping")
        seen.add(dst.casefold())
        if i == 0:
            if b.get("parent") is not None:
                raise CalibratedEvidenceError("BVH calibration chain requires a source root")
        elif (type(b.get("parent")) is not str or
              b["parent"].casefold() != bones[i - 1]["source"].casefold()):
            raise CalibratedEvidenceError("BVH calibrated chain is not directly connected")
        if (movement.get("bone") != dst or
                type(movement.get("moved_vertices")) is not int or
                movement["moved_vertices"] < 16 or
                not _number(movement.get("max_displacement_local")) or
                movement["max_displacement_local"] <= 1e-5):
            raise CalibratedEvidenceError("A mapped joint did not move real weighted vertices")
        if (proof.get("source") != src or proof.get("target") != dst or
                proof.get("source_axes_to_target_sha256") != raw["source_to_target_axes_sha256"] or
                not _hex(proof.get("target_rest_matrix_sha256")) or
                not _hex(proof.get("calibrated_test_delta_sha256"))):
            raise CalibratedEvidenceError("No independently measured rest-bone matrix proof")
    frames, dt = raw.get("source_frame_count"), raw.get("source_frame_time")
    if (type(frames) is not int or not 5 <= frames <= 240 or
            not _number(dt) or not .005 <= dt <= .5 or
            type(raw.get("keyframes_inserted")) is not int or
            raw["keyframes_inserted"] != frames * count or
            type(raw.get("rig_bone_count")) is not int or raw["rig_bone_count"] < 5):
        raise CalibratedEvidenceError("Real frame count, Action size or skeleton invalid")
    sampled = raw.get("sampled_frames")
    if (not isinstance(sampled, list) or len(sampled) != 5 or
            any(not isinstance(row, dict) for row in sampled)):
        raise CalibratedEvidenceError("Five real sampled geometry states required")
    ids = [r.get("frame") for r in sampled]
    if (any(type(i) is not int for i in ids) or
            ids != sorted(set(ids)) or ids[0] != 1 or ids[-1] != frames):
        raise CalibratedEvidenceError("Source timeline sample frames invalid")
    n = sampled[0].get("evaluated_vertex_count")
    if type(n) is not int or not 100 < n <= 250000:
        raise CalibratedEvidenceError("Evaluated MPFB mesh count invalid")
    hashes = set()
    changes = 0
    for row in sampled:
        if (row.get("evaluated_vertex_count") != n or
                not _hex(row.get("evaluated_sha256")) or
                type(row.get("moved_vertices")) is not int or
                not 0 <= row["moved_vertices"] <= n or
                not _number(row.get("max_displacement_local")) or
                not 0 <= row["max_displacement_local"] <= 1e6):
            raise CalibratedEvidenceError("Evaluated MPFB frame geometry invalid")
        hashes.add(row["evaluated_sha256"])
        if (row["moved_vertices"] >= 16 and
                row["max_displacement_local"] > 1e-5):
            changes += 1
    if (raw.get("distinct_geometry_states") != len(hashes) or
            len(hashes) < 3 or changes < 2 or
            sampled[0]["moved_vertices"] != 0 or
            sampled[0]["max_displacement_local"] > 2e-6):
        raise CalibratedEvidenceError("No actual changing calibrated frame geometry")
    if not isinstance(raw.get("blender_version"), str) or not raw["blender_version"]:
        raise CalibratedEvidenceError("No actual Blender version")
    return dict(raw)


def compare_calibrated_evidence(first: Any, second: Any,
                                axis_profile: str) -> dict[str, Any]:
    a = validate_calibrated_evidence(first, axis_profile)
    b = validate_calibrated_evidence(second, axis_profile)
    for key in (
        "source_sha256", "axis_profile", "source_to_target_axes_sha256",
        "rest_landmark_count", "rest_reference_pair", "mapped_bones",
        "local_axis_proofs", "source_frame_count", "source_frame_time",
        "mapped_bone_count", "keyframes_inserted", "rig_bone_count",
        "rig_weight_sha256", "rig_rest_sha256", "blender_version",
        "distinct_geometry_states",
    ):
        if a[key] != b[key]:
            raise CalibratedEvidenceError("Independent Blender calibration disagreed on " + key)
    for x, y in zip(a["rest_residual_degrees"], b["rest_residual_degrees"]):
        if abs(x - y) > 1e-6:
            raise CalibratedEvidenceError("Independent Blender rest-frame residuals disagree")
    for x, y in zip(a["per_bone_deformation"], b["per_bone_deformation"]):
        if (x["bone"] != y["bone"] or
                x["moved_vertices"] != y["moved_vertices"] or
                abs(x["max_displacement_local"] - y["max_displacement_local"]) > 1e-6):
            raise CalibratedEvidenceError("Independent Blender per-bone movement disagrees")
    for x, y in zip(a["sampled_frames"], b["sampled_frames"]):
        for key in ("frame", "evaluated_vertex_count",
                    "evaluated_sha256", "moved_vertices"):
            if x[key] != y[key]:
                raise CalibratedEvidenceError("Independent Blender frame geometry disagrees")
        if abs(x["max_displacement_local"] - y["max_displacement_local"]) > 1e-6:
            raise CalibratedEvidenceError("Independent Blender frame displacement disagrees")
    return a
