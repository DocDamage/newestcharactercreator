"""Reject target-rig influences which invalidate a rest-local FK diagnostic."""
from __future__ import annotations

import math
from typing import Any

from blender_bridge.motion_quality import MotionQualityError


def validate_pose_environment(rig: Any, human: Any, names: list[str]) -> None:
    """Read only: do not mute constraints/drivers or reset a user's saved pose."""
    if rig.animation_data and len(rig.animation_data.drivers):
        raise MotionQualityError("Target rig has drivers; rest-local FK diagnostics are incompatible")
    for obj in (rig, human):
        matrix = obj.matrix_world.to_3x3()
        columns = [tuple(float(matrix[i][j]) for i in range(3)) for j in range(3)]
        lengths = [math.sqrt(sum(x*x for x in col)) for col in columns]
        if (any(not math.isfinite(x) or x < 1e-7 for x in lengths) or
                matrix.determinant() <= 0 or max(lengths) / min(lengths) > 1.0001 or
                any(abs(sum(a*b for a, b in zip(columns[i], columns[j]))) >
                    1e-4 * lengths[i] * lengths[j] for i in range(3) for j in range(i))):
            raise MotionQualityError("Target rig/mesh has reflected, nonuniform or sheared transforms")
    checked = set()
    for name in names:
        bone = rig.pose.bones[name]
        while bone is not None and bone.name not in checked:
            checked.add(bone.name)
            if (any(not constraint.mute and constraint.influence > 0 for constraint in bone.constraints)
                    or (bone.parent is not None and not bone.bone.use_inherit_rotation)):
                raise MotionQualityError("Target bone/ancestor has incompatible constraints or rotation inheritance: " + bone.name)
            if any(not math.isfinite(float(bone.matrix_basis[i][j])) or
                   abs(bone.matrix_basis[i][j] - float(i == j)) > 1e-4
                   for i in range(4) for j in range(4)):
                raise MotionQualityError("Target bone/ancestor has a non-neutral rest-local pose: " + bone.name)
            bone = bone.parent
