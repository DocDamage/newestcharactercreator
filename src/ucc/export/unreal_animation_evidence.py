"""Unreal centimetre and handedness profile for registered raw animation."""
from dataclasses import dataclass
from typing import Callable

from .registered_animation_evidence import RegisteredAnimationComparison, compare_registered_animation
from .unreal_bind_math import expected_position_cm, unique_correspondence


SOURCE_FRAMES = 300
MAX_RAW_ERROR_M = 50e-6
CENTIMETRE_M = .01


@dataclass(frozen=True, slots=True)
class UnrealAnimationComparison:
    samples: RegisteredAnimationComparison
    maximum_bind_position_error_m: float


def _swap_axes(vector):
    # This reflection maps either direction. Pose translations supplied by
    # Unreal are converted to metres separately from the orientation basis.
    x, y, z = vector
    return -y, -x, z


def compare_unreal_animation(*, source_bind_points_m: list, native_bind_points_cm: list,
        source_bones: list[dict], native_bones: list[dict], source_pose_samples: bytes,
        native_pose_samples: bytes, source_raw_samples: bytes, native_raw_samples: bytes,
        check: Callable[[], None]) -> UnrealAnimationComparison:
    source_cm = [expected_position_cm(row) for row in source_bind_points_m]
    native_to_source, bind_error_cm = unique_correspondence(source_cm, native_bind_points_cm, check=check)
    samples = compare_registered_animation(source_bones=source_bones, native_bones=native_bones,
        source_vertex_count=len(source_cm), native_to_source=native_to_source,
        source_pose_samples=source_pose_samples, native_pose_samples=native_pose_samples,
        source_raw_samples=source_raw_samples, native_raw_samples=native_raw_samples, check=check,
        source_frames=SOURCE_FRAMES, maximum_error_m=MAX_RAW_ERROR_M, native_unit_m=CENTIMETRE_M,
        to_engine=_swap_axes, to_blender=_swap_axes)
    return UnrealAnimationComparison(samples, bind_error_cm*CENTIMETRE_M)
