"""Independent comparison of corrected Unity skin readback against Blender."""

from dataclasses import dataclass
from math import acos, cos, degrees, isfinite, radians, sqrt
from struct import Struct
from typing import Callable

from ucc.core.errors import ValidationError


SOURCE_FRAMES = 300
SOURCE_VERTICES = 13380
MAX_NATIVE_VERTICES = 200000
MAX_POSITION_ERROR_M = 1e-5
MAX_NORMAL_ANGLE_DEG = 0.1
_POSITION_ERROR_SQUARED = MAX_POSITION_ERROR_M ** 2
_NORMAL_MIN_COSINE = cos(radians(MAX_NORMAL_ANGLE_DEG))
_NORMAL_UNIT_SQUARED_TOLERANCE = 2e-5
_SOURCE = Struct('<3f')
_NATIVE = Struct('<6f')


@dataclass(frozen=True, slots=True)
class UnityCorrectedAnimationComparison:
    frames: int
    source_vertices: int
    native_vertices: int
    compared_vertices: int
    maximum_position_error_m: float
    maximum_normal_angle_deg: float


def compare_unity_corrected_animation(*, source_positions: bytes, source_normals: bytes,
        native_samples: bytes, native_to_source: list[int] | tuple[int, ...],
        check: Callable[[], None]) -> UnityCorrectedAnimationComparison:
    """Check every render vertex, including UV seam duplicates, at all 300 samples.

    The two independent source streams contain Blender-world component triples
    in source-topology order. Native records interleave Unity-world position
    and unit normal triples in render-vertex order. The input proof identity
    and byte custody are the responsibility of the caller.
    """
    if type(native_to_source) not in (list, tuple) or len(native_to_source) > MAX_NATIVE_VERTICES:
        raise ValidationError('Unity corrected readback requires a bounded native vertex map')
    mapping = tuple(native_to_source)
    if (not SOURCE_VERTICES <= len(mapping) <= MAX_NATIVE_VERTICES
            or any(type(index) is not int or not 0 <= index < SOURCE_VERTICES for index in mapping)
            or len(set(mapping)) != SOURCE_VERTICES):
        raise ValidationError('Unity corrected readback requires complete source vertex correspondence')
    native_count = len(mapping)
    source_frame_size = SOURCE_VERTICES * _SOURCE.size
    native_frame_size = native_count * _NATIVE.size
    if any(type(payload) is not bytes or len(payload) != frame_size * SOURCE_FRAMES for payload, frame_size in (
            (source_positions, source_frame_size), (source_normals, source_frame_size),
            (native_samples, native_frame_size))):
        raise ValidationError('Unity corrected readback requires complete 300-frame float32 streams')

    native = memoryview(native_samples)
    maximum_position_squared = 0.0
    minimum_normal_cosine = 1.0
    for frame in range(SOURCE_FRAMES):
        check()
        source_start = frame * source_frame_size
        native_start = frame * native_frame_size
        samples = _NATIVE.iter_unpack(native[native_start:native_start + native_frame_size])
        for native_index, (source_index, sample) in enumerate(zip(mapping, samples, strict=True)):
            offset = source_start + source_index * _SOURCE.size
            x, y, z = _SOURCE.unpack_from(source_positions, offset)
            nx, ny, nz = _SOURCE.unpack_from(source_normals, offset)
            actual_x, actual_y, actual_z, actual_nx, actual_ny, actual_nz = sample

            # Unity's admitted Blender basis is (-x, z, -y) for points and normals.
            dx, dy, dz = actual_x + x, actual_y - z, actual_z + y
            distance_squared = dx*dx + dy*dy + dz*dz
            if not isfinite(distance_squared) or distance_squared > _POSITION_ERROR_SQUARED:
                raise ValidationError(
                    f'Unity corrected position differs from Blender at frame {frame + 1}, vertex {native_index}'
                )

            expected_length = nx*nx + ny*ny + nz*nz
            actual_length = actual_nx*actual_nx + actual_ny*actual_ny + actual_nz*actual_nz
            if (not isfinite(expected_length) or not isfinite(actual_length)
                    or abs(expected_length - 1.0) > _NORMAL_UNIT_SQUARED_TOLERANCE
                    or abs(actual_length - 1.0) > _NORMAL_UNIT_SQUARED_TOLERANCE):
                raise ValidationError(
                    f'Nonfinite or nonunit corrected normal at frame {frame + 1}, vertex {native_index}'
                )
            normal_cosine = (-nx*actual_nx + nz*actual_ny - ny*actual_nz) / sqrt(expected_length * actual_length)
            if normal_cosine < _NORMAL_MIN_COSINE:
                raise ValidationError(
                    f'Unity corrected normal differs from Blender at frame {frame + 1}, vertex {native_index}'
                )
            maximum_position_squared = max(maximum_position_squared, distance_squared)
            minimum_normal_cosine = min(minimum_normal_cosine, normal_cosine)
    check()
    return UnityCorrectedAnimationComparison(
        SOURCE_FRAMES, SOURCE_VERTICES, native_count, SOURCE_FRAMES * native_count,
        sqrt(maximum_position_squared), degrees(acos(minimum_normal_cosine)),
    )
