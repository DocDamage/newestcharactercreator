"""Pure validation of an explicitly requested channel/bone basis audit."""
from __future__ import annotations

import math
from typing import Any

from ucc.animations.source_rest_frames import CONVERSION_CONVENTION, is_sha256
from ucc.core.errors import ValidationError


def validate_channel_conversion(raw: dict[str, Any], requested: bool, profile_sha: str | None) -> None:
    proof = raw.get("source_frame_conversion")
    if not requested:
        if proof is not None:
            raise ValidationError("Unrequested source-frame conversion claim")
        return
    fields = {"convention", "coordinate_change_applied", "source_channel_interpretation_changed",
              "target_motion_changed_by_source_roll", "profile_sha256", "mapping_sha256", "joint_count",
              "source_frame_count", "traces", "max_roundtrip_residual", "max_target_equivalence_residual"}
    if (type(proof) is not dict or set(proof) != fields or proof.get("convention") != CONVERSION_CONVENTION or
            proof.get("coordinate_change_applied") is not True or
            proof.get("source_channel_interpretation_changed") is not False or
            proof.get("target_motion_changed_by_source_roll") is not False or
            not is_sha256(profile_sha) or proof.get("profile_sha256") != profile_sha or
            proof.get("mapping_sha256") != raw["reviewed_mapping_sha256"] or
            type(proof.get("joint_count")) is not int or proof["joint_count"] != raw["mapped_bone_count"] or
            type(proof.get("source_frame_count")) is not int or proof["source_frame_count"] != raw["source_frame_count"]):
        raise ValidationError("Channel/bone convention, binding or application evidence differs")
    traces = proof.get("traces")
    if type(traces) is not list or len(traces) != raw["mapped_bone_count"]:
        raise ValidationError("Incomplete per-bone conversion traces")
    def bounded(value: Any) -> bool:
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e-5
    for trace in traces:
        if (type(trace) is not dict or set(trace) != {"trace_sha256", "frames_measured",
                "max_roundtrip_residual", "max_target_equivalence_residual"} or
                not is_sha256(trace.get("trace_sha256")) or
                type(trace.get("frames_measured")) is not int or trace["frames_measured"] != raw["source_frame_count"] or
                not bounded(trace.get("max_roundtrip_residual")) or
                not bounded(trace.get("max_target_equivalence_residual"))):
            raise ValidationError("Unbounded or incomplete channel/bone roundtrip")
    for key in ("max_roundtrip_residual", "max_target_equivalence_residual"):
        if not bounded(proof.get(key)) or abs(proof[key] - max(t[key] for t in traces)) > 1e-12:
            raise ValidationError("Conversion residual summary disagrees with bone traces")
