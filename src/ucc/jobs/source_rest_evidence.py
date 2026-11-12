"""Evidence that source rest metadata was validated, never silently applied."""
from __future__ import annotations

import math
from typing import Any

from ucc.animations.source_rest_frames import (
    is_sha256, rotation_sha256, validate_source_rest_profile,
)
from ucc.core.errors import ValidationError


def _number(value: Any, maximum: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def validate_source_rest_evidence(raw: dict, profile: dict | None, profile_sha: str | None,
                                  axis: str, mapping: object) -> None:
    intake = raw.get("source_rest_frame_intake")
    if profile is None:
        if intake is not None or profile_sha is not None:
            raise ValidationError("Worker reported unrequested source rest metadata")
        return
    profile = validate_source_rest_profile(profile, raw["source_sha256"], axis, mapping)
    if (not is_sha256(profile_sha) or type(intake) is not dict or
            set(intake) != {"schema_version", "profile_sha256", "source_bvh_sha256", "axis_profile",
                            "joint_count", "joint_frames", "validation_only",
                            "source_channel_interpretation_changed", "source_roll_independently_verified"} or
            type(intake.get("schema_version")) is not int or intake["schema_version"] != 1 or
            intake.get("profile_sha256") != profile_sha or
            intake.get("source_bvh_sha256") != raw["source_sha256"] or intake.get("axis_profile") != axis or
            intake.get("validation_only") is not True or
            intake.get("source_channel_interpretation_changed") is not False or
            intake.get("source_roll_independently_verified") is not False):
        raise ValidationError("Source rest intake binding, version or validation-only status differs")
    expected = profile["joint_frames"]
    rows = intake.get("joint_frames")
    if (type(intake.get("joint_count")) is not int or intake["joint_count"] != len(expected) or
            type(rows) is not list or len(rows) != len(expected)):
        raise ValidationError("Incomplete source rest-frame proof")
    parents = {row["parent"] for row in expected}
    for row, frame in zip(rows, expected):
        if (type(row) is not dict or set(row) != {"source", "parent", "rest_rotation_sha256",
                                               "rest_head_error_local", "terminal_tail_error_local",
                                               "tail_axis_error_degrees"} or
                row["source"] != frame["source"] or row["parent"] != frame["parent"] or
                row["rest_rotation_sha256"] != rotation_sha256(frame["rotation"]) or
                not _number(row["rest_head_error_local"], 1e-5) or
                not _number(row["tail_axis_error_degrees"], 1.) or
                (row["terminal_tail_error_local"] is None and frame["source"] not in parents) or
                (row["terminal_tail_error_local"] is not None and
                 not _number(row["terminal_tail_error_local"], 1e-5))):
            raise ValidationError("Source rest matrices, hierarchy or actual BVH position checks disagree")
    for actual, source in zip(raw["mapped_bones"], expected):
        parent = actual["parent"]
        if (parent.casefold() if parent is not None else None) != (
            source["parent"].casefold() if source["parent"] is not None else None
        ):
            raise ValidationError("Rest descriptor and calibrated BVH source parents disagree")
