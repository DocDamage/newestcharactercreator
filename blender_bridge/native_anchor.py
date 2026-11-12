"""Explicit source hip-midpoint root constraint; legacy profiles stay unchanged."""
from blender_bridge.rest_calibration import multiply, transpose, transform

POLICY = "SOURCE_HIP_MIDPOINT_V1"
LEGACY = "ARMATURE_ORIGIN_DISPLACEMENT_V1"


def midpoint(points):
    return tuple(sum(p[i] for p in points)/len(points) for i in range(3))


def validate_target_chain(rig, pairs, landmarks):
    """This policy requires hip heads rigidly attached through neutral helpers."""
    root = pairs[0]["target"]
    mapped = {p["target"] for p in pairs}
    for key in ("left_hip", "right_hip"):
        bone = rig.data.bones[landmarks[key]["target"]]
        while bone.name != root:
            if not bone.use_inherit_rotation or bone.inherit_scale != "FULL":
                raise ValueError("Hip anchor needs ordinary inherited transforms on the hip chain")
            bone = bone.parent
            if bone is None or (bone.name in mapped and bone.name != root):
                raise ValueError("Hip anchor needs neutral helpers between the mapped root and hip heads")


def root_position(source_bind_midpoint, source_pose_midpoint, target_bind_midpoint,
                  root_bind_head, axes, scale, root_bind_rotation, root_pose_rotation):
    """Place the target hip midpoint at the scaled source joint-head trajectory."""
    displacement = transform(axes, tuple(b-a for a,b in zip(source_bind_midpoint, source_pose_midpoint)))
    expected_hip = tuple(target_bind_midpoint[i]+scale*displacement[i] for i in range(3))
    delta = multiply(root_pose_rotation, transpose(root_bind_rotation))
    offset = transform(delta, tuple(target_bind_midpoint[i]-root_bind_head[i] for i in range(3)))
    return tuple(expected_hip[i]-offset[i] for i in range(3)), expected_hip
