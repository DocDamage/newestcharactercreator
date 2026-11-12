"""Audited basis change for the existing XYZ first-frame-relative BVH convention.

D = R0.T Rf, Db = S.T D S, T = B.T C S, Dt = T Db T.T.
S is supplied bone-rest -> source, B is target-rest -> target, and C is the
measured source -> target axes map. S cancels: Dt must equal B.T C D C.T B.
This is coordinate conversion, not a new rest-pose/roll correction algorithm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import struct
from typing import Any

from blender_bridge.rest_calibration import Matrix3, multiply, transpose, validate_rotation

CONVENTION = "BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1"
MAX_RESIDUAL = 1e-5


class ChannelBoneConversionError(RuntimeError):
    """The declared basis change cannot roundtrip or preserve target motion."""


def residual(a: Matrix3, b: Matrix3) -> float:
    return max(abs(a[i][j] - b[i][j]) for i in range(3) for j in range(3))


def convert_channel_delta(start: Matrix3, current: Matrix3, source_rest: Matrix3,
                          axes: Matrix3, target_rest: Matrix3) -> tuple[Matrix3, Matrix3, Matrix3, float, float]:
    for matrix in (start, current, source_rest, axes, target_rest):
        validate_rotation(matrix)
    channel = multiply(transpose(start), current)
    bone = multiply(multiply(transpose(source_rest), channel), source_rest)
    transfer = multiply(multiply(transpose(target_rest), axes), source_rest)
    target = multiply(multiply(transfer, bone), transpose(transfer))
    roundtrip = multiply(multiply(source_rest, bone), transpose(source_rest))
    direct = multiply(transpose(target_rest), axes)
    expected = multiply(multiply(direct, channel), transpose(direct))
    for matrix in (channel, bone, target, roundtrip):
        validate_rotation(matrix)
    rt, eq = residual(roundtrip, channel), residual(target, expected)
    if rt > MAX_RESIDUAL or eq > MAX_RESIDUAL:
        raise ChannelBoneConversionError("Channel/bone basis roundtrip or target equivalence failed")
    return target, channel, bone, rt, eq


@dataclass
class ConversionTrace:
    frames: int = 0
    max_roundtrip: float = 0.
    max_equivalence: float = 0.
    digest: Any = field(default_factory=sha256)

    def apply(self, frame: int, start: Matrix3, current: Matrix3, source_rest: Matrix3,
              axes: Matrix3, target_rest: Matrix3) -> Matrix3:
        if type(frame) is not int or frame != self.frames + 1:
            raise ChannelBoneConversionError("Conversion audit requires every frame in order")
        target, channel, bone, rt, eq = convert_channel_delta(start, current, source_rest, axes, target_rest)
        self.digest.update(struct.pack("<I", frame))
        for matrix in (channel, bone, target):
            for row in matrix:
                self.digest.update(struct.pack("<qqq", *(round(v * 1_000_000) for v in row)))
        self.frames += 1
        self.max_roundtrip = max(self.max_roundtrip, rt)
        self.max_equivalence = max(self.max_equivalence, eq)
        return target

    def report(self) -> dict[str, Any]:
        return {"trace_sha256": self.digest.hexdigest(), "frames_measured": self.frames,
                "max_roundtrip_residual": self.max_roundtrip,
                "max_target_equivalence_residual": self.max_equivalence}
