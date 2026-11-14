"""Validate numerical joint/edge evidence without importing Blender or Qt."""
from __future__ import annotations

import math
from typing import Any

from ucc.core.errors import ValidationError


def _number(value: Any, low: float, high: float) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and low <= value <= high


def validate_motion_quality(raw: dict[str, Any], targets: list[str], *, neutral_reference: bool=False) -> None:
    if (type(raw.get("motion_quality_schema_version")) is not int or
            raw["motion_quality_schema_version"] != (2 if neutral_reference else 1) or
            raw.get("target_pose_environment_checked") is not True):
        raise ValidationError("Missing versioned joint/mesh quality measurements")
    mesh = raw.get("mesh_edge_strain")
    if not isinstance(mesh, dict):
        raise ValidationError("Missing evaluated edge topology evidence")
    total, measured, excluded = (mesh.get(k) for k in (
        "evaluated_edge_count", "measured_edge_count", "degenerate_baseline_edges_excluded"))
    digest = mesh.get("evaluated_topology_sha256")
    if (any(type(x) is not int for x in (total, measured, excluded)) or
            not 16 <= measured <= total <= 750000 or excluded != total - measured or
            type(digest) is not str or len(digest) != 64 or
            any(c not in "0123456789abcdef" for c in digest)):
        raise ValidationError("Invalid measured/excluded edge counts or topology SHA")
    for i, frame in enumerate(raw["full_timeline_frames"]):
        lo, hi = frame.get("min_edge_length_ratio"), frame.get("max_edge_stretch_ratio")
        if (not _number(lo, .05, 4.) or not _number(hi, .05, 4.) or lo > hi or
                (i == 0 and not neutral_reference and (abs(lo - 1) > 1e-6 or abs(hi - 1) > 1e-6))):
            raise ValidationError("Missing or extreme full-frame local edge strain")
    joints = raw.get("joint_motion_metrics")
    if not isinstance(joints, list) or len(joints) != len(targets):
        raise ValidationError("Missing measured per-joint swing/twist")
    frames = raw["source_frame_count"]
    for joint, target in zip(joints, targets):
        if (not isinstance(joint, dict) or joint.get("bone") != target or
                type(joint.get("frames_measured")) is not int or joint["frames_measured"] != frames):
            raise ValidationError("Joint quality bone or full-frame count mismatch")
        for metric, limit in (("swing", 150.), ("twist", 90.), ("step", 80.)):
            frame = joint.get(f"max_{metric}_frame")
            if (not _number(joint.get(f"max_{metric}_degrees"), 0., limit) or
                    type(frame) is not int or not 1 <= frame <= frames):
                raise ValidationError("Invalid maximum joint angle or frame")
        if abs(joint["max_step_degrees"] - raw["max_bone_quaternion_step_degrees"][target]) > 1e-6:
            raise ValidationError("Per-joint step and quaternion discontinuity evidence disagree")
