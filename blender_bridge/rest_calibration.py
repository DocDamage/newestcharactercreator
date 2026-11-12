"""Explicit BVH-to-MPFB rest-axis calibration, pure Python and no bpy.

BVH rest joint axes are not individually documented by offset vectors. A
minimum of TWO non-collinear corresponding anatomical directions is therefore
required to solve a proper *shared* source-to-target orientation. Bone-local
conversion additionally uses each real Blender rest bone matrix. Insufficient
landmarks, reflection, scale problems or incompatible directions fail closed.

The source motion convention is explicitly ordered XYZ BVH CHANNELS; the
relative rotation is Q(start)^-1 * Q(frame), not Euler angle subtraction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]

Y_UP_TO_Z_UP: Matrix3 = ((1.0, 0.0, 0.0),
                        (0.0, 0.0, -1.0),
                        (0.0, 1.0, 0.0))
Z_UP_IDENTITY: Matrix3 = ((1.0, 0.0, 0.0),
                          (0.0, 1.0, 0.0),
                          (0.0, 0.0, 1.0))
PROFILES = {"Y_UP_TO_Z_UP": Y_UP_TO_Z_UP, "Z_UP_IDENTITY": Z_UP_IDENTITY}
MIN_PAIR_SINE = math.sin(math.radians(10.0))
MAX_REST_RESIDUAL_DEGREES = 5.0
ORTHO_EPS = 1e-5


class RestCalibrationError(RuntimeError):
    """The source skeleton cannot establish a reliable proper rest-axis basis."""


def _vector(vec: Sequence[float]) -> Vector3:
    if len(vec) != 3:
        raise RestCalibrationError("A rest landmark requires exactly three coordinates")
    xyz = tuple(float(x) for x in vec)
    if any(not math.isfinite(x) or abs(x) > 1e6 for x in xyz):
        raise RestCalibrationError("Rest landmark contains invalid coordinates")
    return xyz  # type: ignore[return-value]


def dot(a: Vector3, b: Vector3) -> float:
    return sum(x * y for x, y in zip(a, b))


def cross(a: Vector3, b: Vector3) -> Vector3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a: Vector3) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Sequence[float]) -> Vector3:
    v = _vector(a)
    magnitude = norm(v)
    if not 1e-7 < magnitude < 1e6:
        raise RestCalibrationError("Rest landmark has degenerate or excessive length")
    return (v[0] / magnitude, v[1] / magnitude, v[2] / magnitude)


def transpose(a: Matrix3) -> Matrix3:
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def multiply(a: Matrix3, b: Matrix3) -> Matrix3:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )  # type: ignore[return-value]


def transform(a: Matrix3, v: Vector3) -> Vector3:
    return tuple(sum(a[i][j] * v[j] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def determinant(a: Matrix3) -> float:
    return dot(a[0], cross(a[1], a[2]))


def _columns(e1: Vector3, e2: Vector3, e3: Vector3) -> Matrix3:
    return ((e1[0], e2[0], e3[0]),
            (e1[1], e2[1], e3[1]),
            (e1[2], e2[2], e3[2]))


def _basis(primary: Vector3, secondary: Vector3) -> Matrix3:
    forward = unit(primary)
    axis = dot(forward, secondary)
    candidate = tuple(secondary[i] - axis * forward[i] for i in range(3))
    side = unit(candidate)
    normal = unit(cross(forward, side))
    return _columns(forward, side, normal)


def validate_rotation(a: Matrix3) -> None:
    if any(not math.isfinite(x) for row in a for x in row):
        raise RestCalibrationError("Rotation matrix contains nonfinite elements")
    det = determinant(a)
    if abs(det - 1.0) > ORTHO_EPS:
        raise RestCalibrationError("Rest-axis rotation is reflected, scaled or singular")
    product = multiply(transpose(a), a)
    for i in range(3):
        for j in range(3):
            if abs(product[i][j] - float(i == j)) > ORTHO_EPS:
                raise RestCalibrationError("Rest-axis rotation is not orthonormal")


def project_near_rotation(raw: Matrix3) -> tuple[Matrix3, float, float]:
    """Normalize only tiny MPFB rest matrix roundoff, never reflections/shear.

    Some actual MPFB refitted Blender rest frames include ~1e-5 scaling noise.
    A near-SO(3) matrix can be projected by Gram-Schmidt with an explicit,
    measured absolute correction cap. Wrong-handed, stretched or severely
    sheared transforms fail, and the resulting rotation still satisfies the
    *strict* 1e-5 SO(3) acceptance tolerance.
    """
    if any(not math.isfinite(v) for row in raw for v in row):
        raise RestCalibrationError("Rest matrix has nonfinite elements")
    original_det = determinant(raw)
    if not 0.999 < original_det < 1.001:
        raise RestCalibrationError("Actual rest matrix is reflected or severely scaled")
    columns = tuple(tuple(raw[i][j] for i in range(3)) for j in range(3))
    primary = unit(columns[0])
    proj = dot(primary, columns[1])
    secondary = unit(tuple(columns[1][i] - proj * primary[i] for i in range(3)))
    third = unit(cross(primary, secondary))
    if dot(third, unit(columns[2])) < 0.999:
        raise RestCalibrationError("Rest matrix contains reflection or excessive shear")
    result = _columns(primary, secondary, third)
    correction = max(abs(result[i][j] - raw[i][j])
                     for i in range(3) for j in range(3))
    if correction > 5e-4:
        raise RestCalibrationError("Rest-bone axes differ too much from a proper rotation")
    validate_rotation(result)
    return result, original_det, correction


def _angle_degrees(a: Vector3, b: Vector3) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


@dataclass(frozen=True, slots=True)
class RestFrameCalibration:
    axis_profile: str
    source_axes_to_target: Matrix3
    rest_residual_degrees: tuple[float, ...]
    landmark_pair: tuple[int, int]
    max_rest_residual_degrees: float
    calibrated_rotation_axes_verified: bool = True
    bone_roll_independently_verified: bool = False
    retargeting_verified: bool = False


def calibrate_rest_frames(
    source_directions: Sequence[Sequence[float]],
    target_directions: Sequence[Sequence[float]],
    axis_profile: str,
) -> RestFrameCalibration:
    """Solve proper orientation from corresponding two-or-more rest landmarks."""
    if axis_profile not in PROFILES:
        raise RestCalibrationError("BVH source up-axis must be explicitly selected")
    if not 2 <= len(source_directions) <= 5 or len(source_directions) != len(target_directions):
        raise RestCalibrationError("At least two corresponding rest direction landmarks required")
    axis = PROFILES[axis_profile]
    source = [unit(transform(axis, _vector(item))) for item in source_directions]
    target = [unit(item) for item in target_directions]
    candidates = []
    for i in range(len(source)):
        for j in range(i + 1, len(source)):
            ss = norm(cross(source[i], source[j]))
            tt = norm(cross(target[i], target[j]))
            if ss >= MIN_PAIR_SINE and tt >= MIN_PAIR_SINE:
                candidates.append((min(ss, tt), i, j))
    if not candidates:
        raise RestCalibrationError(
            "No two independent non-collinear source/target directions; "
            "bone roll cannot be resolved"
        )
    _, i, j = max(candidates)
    src_basis = _basis(source[i], source[j])
    dst_basis = _basis(target[i], target[j])
    fit = multiply(dst_basis, transpose(src_basis))
    mapping = multiply(fit, axis)
    validate_rotation(mapping)
    errors = tuple(_angle_degrees(transform(mapping, unit(raw)), trg)
                   for raw, trg in zip(source_directions, target))
    if max(errors) > MAX_REST_RESIDUAL_DEGREES:
        raise RestCalibrationError(
            "Source/target rest landmarks disagree by more than five degrees"
        )
    return RestFrameCalibration(axis_profile, mapping, errors, (i, j), max(errors))


def axis_rotation(axis: str, degrees: float) -> Matrix3:
    if axis not in ("Xrotation", "Yrotation", "Zrotation") or not math.isfinite(degrees):
        raise RestCalibrationError("Unrecognized or nonfinite BVH rotation channel")
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    if axis == "Xrotation":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == "Yrotation":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def bvh_ordered_rotation(order: Sequence[str], xyz_angles: Sequence[float]) -> Matrix3:
    """Compose BVH channels in their declared order (matrix, never Euler subtraction)."""
    if tuple(order) != ("Xrotation", "Yrotation", "Zrotation"):
        raise RestCalibrationError("Calibrated BVH v1 requires exact XYZ rotation channels")
    if len(xyz_angles) != 3:
        raise RestCalibrationError("Expected X/Y/Z BVH rotation samples")
    result = Z_UP_IDENTITY
    for name, angle in zip(order, xyz_angles):
        result = multiply(result, axis_rotation(name, float(angle)))
    validate_rotation(result)
    return result


def calibrated_local_delta(
    source_start: Matrix3,
    source_current: Matrix3,
    source_axes_to_target: Matrix3,
    target_rest_world: Matrix3,
) -> Matrix3:
    """C * (R_start^-1 * R_current) * C^-1 in real target rest-bone axes."""
    for matrix in (source_start, source_current, source_axes_to_target, target_rest_world):
        validate_rotation(matrix)
    converted = multiply(transpose(target_rest_world), source_axes_to_target)
    source_delta = multiply(transpose(source_start), source_current)
    result = multiply(multiply(converted, source_delta), transpose(converted))
    validate_rotation(result)
    return result
