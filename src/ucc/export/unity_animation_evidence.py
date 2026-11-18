"""Unity coordinate profile for independently sampled Blender animation evidence."""
from typing import Callable

from .registered_animation_evidence import RegisteredAnimationComparison as UnityAnimationComparison
from .registered_animation_evidence import compare_registered_animation
from .unity_animation_recipe import SOURCE_FRAMES
from .unity_skin_precision import MAX_DEFORMATION_ERROR_M


def _to_unity(vector):
    x, y, z = vector
    return -x, z, -y


def _to_blender(vector):
    x, y, z = vector
    return -x, -z, y


def compare_unity_animation(*, source_bones: list[dict], native_bones: list[dict], source_vertex_count: int,
        native_to_source: list[int], source_pose_samples: bytes, native_pose_samples: bytes,
        source_raw_samples: bytes, native_raw_samples: bytes, check: Callable[[], None]) -> UnityAnimationComparison:
    return compare_registered_animation(source_bones=source_bones, native_bones=native_bones,
        source_vertex_count=source_vertex_count, native_to_source=native_to_source,
        source_pose_samples=source_pose_samples, native_pose_samples=native_pose_samples,
        source_raw_samples=source_raw_samples, native_raw_samples=native_raw_samples, check=check,
        source_frames=SOURCE_FRAMES, maximum_error_m=MAX_DEFORMATION_ERROR_M, native_unit_m=1.,
        to_engine=_to_unity, to_blender=_to_blender)
