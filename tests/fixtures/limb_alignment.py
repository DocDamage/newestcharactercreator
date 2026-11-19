"""Non-shipping direct bilateral chains and measured pose samples."""
from copy import deepcopy
from math import cos, radians, sin

from ucc.animations.native_math import pose_digest
from ucc.animations.native_skin_policy import BOUND_V1


def _matrix(head=(0., 0., 0.), z_degrees=0.):
    angle = radians(z_degrees)
    c, s = cos(angle), sin(angle)
    x, y, z = head
    return [c, -s, 0., x, s, c, 0., y, 0., 0., 1., z, 0., 0., 0., 1.]


def synthetic_chains():
    bones, pairs, landmarks, frame_poses = [], [], {}, []

    def chain(side, names, heads):
        for index, (role, head) in enumerate(zip(names, heads, strict=True)):
            name = f"{side}_{role}"
            parent = f"{side}_{names[index - 1]}" if index else None
            child = f"{side}_{names[index + 1]}" if index + 1 < len(names) else None
            bones.append(dict(name=name, head=head, parent=parent, matrix=_matrix(head)))
            pairs.append(dict(source=name, source_tip=child,
                              target="target_" + name, target_tip=("target_" + child if child else None)))
            frame_poses.append(_matrix(head, 25. if role == "hip" else 0.))
            if role in ("hip", "foot", "hand"):
                landmarks[name] = {"source": name, "target": "target_" + name}

    for side, x in (("left", -1.), ("right", 1.)):
        chain(side, ("hip", "knee", "foot"), [(x, 0., 2.), (x, 0., 1.), (x, 0., 0.)])
        chain(side, ("upper", "forearm", "hand", "finger"),
              [(x, 0., 3.), (x, 1., 3.), (x, 2., 3.), (x, 3., 3.)])
    world = _matrix((2., 3., 4.))
    source = {"first_frame": 10, "frames": [
        dict(frame=frame, armature_world=world, poses=deepcopy(frame_poses),
             pose_sha256=pose_digest(world, frame_poses))
        for frame in range(10, 15)
    ], "bones": bones}
    profile = {
        "root_motion_policy": "SOURCE_HIP_MIDPOINT_V1",
        "mesh_strain_reference": "TRUE_NEUTRAL_BIND_V2",
        "skin_deformation_policy": BOUND_V1,
        "landmarks": landmarks,
        "pairs": pairs,
        "limb_alignment": {
            "schema_version": 1,
            "first_frame": 10,
            "upper_arm_turns": [{"side": "left", "frame": 11, "angle_degrees": 2.}],
            "forearm_angle_tenths": {"left": [0, 10, 15, 10, 0], "right": [0, 0, -15, 0, 0]},
        },
    }
    return source, profile
