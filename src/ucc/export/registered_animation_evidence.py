"""Compare registered native animation samples with independently reopened Blender poses."""
from dataclasses import dataclass
from math import asin, degrees, dist, hypot, isfinite, radians, sin
from struct import Struct
from typing import Callable

from ucc.core.errors import ValidationError


MAX_BONE_ANGLE_DEG = 0.1
_MAX_AXIS_DISTANCE = 2 * sin(radians(MAX_BONE_ANGLE_DEG) / 2)
_POINT = Struct('<3f')
_BONE = Struct('<16f')


@dataclass(frozen=True, slots=True)
class RegisteredAnimationComparison:
    frames: int
    source_vertices: int
    native_vertices: int
    bones: int
    maximum_raw_skin_error_m: float
    maximum_bone_position_error_m: float
    maximum_bone_axis_error_deg: float


def _position(matrix):
    return matrix[3], matrix[7], matrix[11]


def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _basis(matrix):
    if (len(matrix) != 16 or any(type(value) not in (int, float) or not isfinite(value) for value in matrix)
            or any(abs(actual - expected) > 1e-5 for actual, expected in zip(matrix[12:], (0, 0, 0, 1)))):
        raise ValidationError('Native animation contains a malformed affine bone transform')
    axes = ((matrix[0], matrix[4], matrix[8]), (matrix[1], matrix[5], matrix[9]),
            (matrix[2], matrix[6], matrix[10]))
    lengths = tuple(hypot(*axis) for axis in axes)
    if min(lengths) < 1e-6 or max(lengths)/min(lengths) > 1.001:
        raise ValidationError('Native animation contains a collapsed or nonuniform bone basis')
    x, y, z = (tuple(value / length for value in axis) for axis, length in zip(axes, lengths))
    cross = (x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0])
    if _dot(cross, z) < .99999 or max(abs(_dot(a, b)) for a, b in ((x, y), (y, z), (z, x))) > 1e-4:
        raise ValidationError('Native animation contains a sheared or reflected bone basis')
    return (x, y, z), lengths[0]


def _skeleton(rows: object) -> dict:
    if type(rows) is not list or not rows:
        raise ValidationError('Native animation skeleton is missing')
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get('name')) is not str or not row['name'] or row['name'] in result:
            raise ValidationError('Native animation skeleton contains invalid or duplicate bone names')
        parent = row.get('parent')
        if parent is not None and type(parent) is not str:
            raise ValidationError('Native animation contains invalid bone ancestry')
        result[row['name']] = parent or None
    if any(parent is not None and (parent not in result or parent == bone) for bone, parent in result.items()):
        raise ValidationError('Native animation skeleton contains an unresolved bone parent')
    return result


def _matrices(rows: list[dict], key: str):
    matrices = [row.get(key) for row in rows]
    if any(type(row) is not list for row in matrices):
        raise ValidationError('Native animation has missing rest matrices')
    return matrices


def compare_registered_animation(*, source_bones: list[dict], native_bones: list[dict], source_vertex_count: int,
        native_to_source: list[int], source_pose_samples: bytes, native_pose_samples: bytes,
        source_raw_samples: bytes, native_raw_samples: bytes, check: Callable[[], None],
        source_frames: int, maximum_error_m: float, native_unit_m: float,
        to_engine: Callable[[tuple], tuple], to_blender: Callable[[tuple], tuple]) -> RegisteredAnimationComparison:
    """Compare every render vertex and named bone at every fixed-clock sample."""
    if _skeleton(source_bones) != _skeleton(native_bones):
        raise ValidationError('Native and Blender animation bone names or parent links differ')
    if (type(source_vertex_count) is not int or source_vertex_count < 1 or type(native_to_source) is not list
            or any(type(index) is not int or not 0 <= index < source_vertex_count for index in native_to_source)
            or len(set(native_to_source)) != source_vertex_count):
        raise ValidationError('Native render mesh does not cover every Blender source vertex')
    count = len(source_bones)
    source_size = _POINT.size * source_vertex_count
    native_size = _POINT.size * len(native_to_source)
    bone_size = _BONE.size * count
    if any(len(payload) != size * source_frames for payload, size in (
            (source_pose_samples, bone_size), (native_pose_samples, bone_size),
            (source_raw_samples, source_size), (native_raw_samples, native_size))):
        raise ValidationError('Native animation samples have an incomplete fixed-clock binary layout')

    source_indices = {row['name']: i for i, row in enumerate(source_bones)}
    source_rest = _matrices(source_bones, 'world')
    native_rest = _matrices(native_bones, 'rest_world')
    bindings = []
    for native_index, row in enumerate(native_bones):
        source_index = source_indices[row['name']]
        source_matrix, native_matrix = source_rest[source_index], native_rest[native_index]
        source_axes, source_scale = _basis(source_matrix)
        native_axes, native_scale = _basis(native_matrix)
        native_position = tuple(value*native_unit_m for value in _position(native_matrix))
        if dist(to_engine(_position(source_matrix)), native_position) > maximum_error_m:
            raise ValidationError('Native animation neutral bone location differs from Blender')
        # FBX import may reorient a bone's local basis. Lock the basis change at rest,
        # then apply it to every evaluated Blender pose.
        local_axes = [tuple(_dot(to_blender(axis), ref) for ref in source_axes) for axis in native_axes]
        bindings.append((source_index, local_axes, source_scale, native_scale))

    max_point = max_bone = max_axis = 0.
    for frame in range(source_frames):
        check()
        source_frame = source_size * frame
        native_frame = memoryview(native_raw_samples)[native_size*frame:native_size*(frame+1)]
        for index, observed in zip(native_to_source, _POINT.iter_unpack(native_frame), strict=True):
            original_point = _POINT.unpack_from(source_raw_samples, source_frame + _POINT.size*index)
            if native_unit_m != 1.:
                observed = tuple(value*native_unit_m for value in observed)
            error = dist(to_engine(original_point), observed)
            if not isfinite(error) or error > maximum_error_m:
                raise ValidationError(f'Native raw skin differs from Blender at sample {frame + 1}')
            max_point = max(max_point, error)
        for native_index, (source_index, local_axes, source_scale, native_scale) in enumerate(bindings):
            original = _BONE.unpack_from(source_pose_samples, bone_size*frame + _BONE.size*source_index)
            observed = _BONE.unpack_from(native_pose_samples, bone_size*frame + _BONE.size*native_index)
            native_position = tuple(value*native_unit_m for value in _position(observed))
            bones_error = dist(to_engine(_position(original)), native_position)
            original_axes, original_scale = _basis(original)
            observed_axes, observed_scale = _basis(observed)
            if (bones_error > maximum_error_m
                    or abs(original_scale/source_scale - observed_scale/native_scale) > 1e-4):
                raise ValidationError(f'Native bone translation or scale differs at sample {frame + 1}')
            max_bone = max(max_bone, bones_error)
            for local, actual in zip(local_axes, observed_axes, strict=True):
                expected = tuple(sum(local[i]*original_axes[i][j] for i in range(3)) for j in range(3))
                axis_error = dist(to_engine(expected), actual)
                if axis_error > _MAX_AXIS_DISTANCE:
                    raise ValidationError(f'Native bone orientation differs at sample {frame + 1}')
                max_axis = max(max_axis, axis_error)
    check()
    return RegisteredAnimationComparison(source_frames, source_vertex_count, len(native_to_source), count,
                                   max_point, max_bone, degrees(2*asin(max_axis/2)))
