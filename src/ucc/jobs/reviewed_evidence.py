"""Fail-closed evidence for manually mapped, whole-timeline BVH review.

The first 3–8 bone slice remains unapproved for visual quality, bone-roll
compatibility across external rigs, game-engine export, and production reuse.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from ucc.animations.review_mapping import review_mapping_sha256, validate_review_mapping
from ucc.core.errors import ValidationError
from .calibrated_evidence import compare_calibrated_evidence, validate_calibrated_evidence


class ReviewedEvidenceError(ValidationError):
    """The private reviewed BVH mapping or actual Blender evidence is insufficient."""


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _hex(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(x in "0123456789abcdef" for x in value)


def _canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """Feed legacy calibration invariants with normalized target-only aliases."""
    clone = deepcopy(raw)
    clone["status"] = "REAL_BVH_REST_AXES_CALIBRATED_MESH_MOTION"
    for i, row in enumerate(clone["mapped_bones"]):
        row["source"] = row["target"]
        row["parent"] = clone["mapped_bones"][i-1]["target"] if i else None
    for proof in clone["local_axis_proofs"]:
        proof["source"] = proof["target"]
    return clone


def validate_reviewed_evidence(raw: Any, axis_profile: str,
                               mapping: object) -> dict[str, Any]:
    pairs = validate_review_mapping(mapping)
    if not isinstance(raw, dict) or raw.get("status") != "REAL_REVIEWED_BVH_FULL_TIMELINE_MOTION":
        raise ReviewedEvidenceError("Reviewed source did not execute actual Blender motion")
    if raw.get("reviewed_mapping_sha256") != review_mapping_sha256(pairs):
        raise ReviewedEvidenceError("Explicit source-to-target mapping hash mismatch")
    if raw.get("explicit_mapping_reviewed_by_user") is not True:
        raise ReviewedEvidenceError("The Blender worker did not use explicit reviewed pairs")
    rows = raw.get("mapped_bones")
    if not isinstance(rows, list) or len(rows) != len(pairs):
        raise ReviewedEvidenceError("Mapped source/target count does not match user review")
    for i, (row, pair) in enumerate(zip(rows, pairs)):
        if (not isinstance(row, dict) or row.get("source") != pair["source"] or
                row.get("target") != pair["target"] or
                row.get("parent") != (pairs[i-1]["source"] if i else None) or
                (i > 0 and row.get("target_parent") != pairs[i-1]["target"])):
            raise ReviewedEvidenceError("Mapped joint name or parent hierarchy was changed")
    try:
        validate_calibrated_evidence(_canonical(raw), axis_profile, max_bones=8)
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        raise ReviewedEvidenceError("Measured calibrated rotation/skin evidence rejected") from exc
    frames = raw["source_frame_count"]
    full = raw.get("full_timeline_frames")
    diagonal = raw.get("model_baseline_diagonal_local")
    maximum = raw.get("max_adjacent_mesh_step_local")
    if (not isinstance(full, list) or len(full) != frames or
            not _number(diagonal) or not .01 < diagonal < 100000 or
            not _number(maximum) or not 0 <= maximum <= diagonal * .8):
        raise ReviewedEvidenceError("No bounded full-frame evaluated skin motion")
    states = {}
    max_seen = 0.0
    for i, item in enumerate(full):
        if not isinstance(item, dict):
            raise ReviewedEvidenceError("Full-frame motion report must contain objects")
        move = item.get("moved_vertices")
        delta = item.get("max_displacement_local")
        adjacent = item.get("adjacent_max_displacement_local")
        if (item.get("frame") != i + 1 or not _hex(item.get("evaluated_sha256")) or
                type(move) is not int or move < 0 or
                move > raw["sampled_frames"][0]["evaluated_vertex_count"] or
                not _number(delta) or not 0 <= delta <= diagonal * 1.5 or
                not _number(adjacent) or not 0 <= adjacent <= diagonal * .8):
            raise ReviewedEvidenceError("Unbounded, incomplete or misordered evaluated frame")
        if i == 0 and (move != 0 or delta > 2e-6 or adjacent > 2e-6):
            raise ReviewedEvidenceError("First frame must be the reference pose")
        states[i + 1] = item
        max_seen = max(max_seen, adjacent)
    if (abs(maximum - max_seen) > 1e-6 or
            len({row["evaluated_sha256"] for row in full}) < 3):
        raise ReviewedEvidenceError("Full timeline hashes or maximum step are inconsistent")
    for sample in raw["sampled_frames"]:
        inspected = states.get(sample["frame"])
        if (inspected is None or sample["evaluated_sha256"] != inspected["evaluated_sha256"] or
                sample["moved_vertices"] != inspected["moved_vertices"] or
                abs(sample["max_displacement_local"] - inspected["max_displacement_local"]) > 1e-6):
            raise ReviewedEvidenceError("Sparse calibration and full timeline disagree")
    steps = raw.get("max_bone_quaternion_step_degrees")
    if (not isinstance(steps, dict) or set(steps) != {p["target"] for p in pairs} or
            any(not _number(v) or not 0 <= v <= 80.0 for v in steps.values())):
        raise ReviewedEvidenceError("Missing bounded, per-bone quaternion discontinuity checks")
    artifact = raw.get("visual_review_blend")
    if (raw.get("visual_review_artifact_created") is not True or
            raw.get("animation_visual_quality_verified") is not False or
            raw.get("joint_twist_visual_quality_verified") is not False or
            not isinstance(artifact, dict) or artifact.get("name") != "review_motion.blend" or
            type(artifact.get("bytes")) is not int or
            not 10000 < artifact["bytes"] <= 512 * 1024 * 1024 or
            not _hex(artifact.get("sha256"))):
        raise ReviewedEvidenceError("Private Blender Action inspection artifact unproven")
    return dict(raw)


def compare_reviewed_evidence(first: Any, second: Any, axis_profile: str,
                              mapping: object) -> dict[str, Any]:
    a = validate_reviewed_evidence(first, axis_profile, mapping)
    b = validate_reviewed_evidence(second, axis_profile, mapping)
    try:
        compare_calibrated_evidence(_canonical(a), _canonical(b), axis_profile, max_bones=8)
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        raise ReviewedEvidenceError("Independent calibrated Blender workers disagree") from exc
    for field in ("reviewed_mapping_sha256", "max_bone_quaternion_step_degrees",
                  "model_baseline_diagonal_local", "max_adjacent_mesh_step_local"):
        if a[field] != b[field]:
            raise ReviewedEvidenceError("Two reviewed workers disagree on " + field)
    for x, y in zip(a["full_timeline_frames"], b["full_timeline_frames"]):
        if x != y:
            raise ReviewedEvidenceError("Independent Blender full-frame evaluated meshes disagree")
    # Blender .blend files contain internal save metadata, and the SHA of two
    # distinct private review COPIES is NOT presumed to be deterministic.
    return a
