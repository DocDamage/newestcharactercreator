"""Measure intrinsic finger motion separately from inherited wrist/root motion."""
import math

from ucc.animations import native_math as nm
from ucc.animations.native_hands import HAND_TARGETS


def hand_local_motion(data):
    indices={row["target"]:i for i,row in enumerate(data["mapped_pairs"])}
    parents={}
    for name in HAND_TARGETS:
        base,side=name.split(".")
        if base.startswith("metacarpal"):
            parent="wrist"
        else:
            digit,joint=map(int,base.removeprefix("finger").split("-"))
            parent=(f"finger{digit}-{joint-1}" if joint>1 else
                    "wrist" if digit==1 else f"metacarpal{digit-1}")
        parents[name]=parent+"."+side
    first={};maximum={name:0. for name in HAND_TARGETS}
    for frame in data["full_timeline_frames"]:
        poses=frame["target_global_poses"]
        for name,parent in parents.items():
            child,_=nm.rotation(poses[indices[name]],target_noise=True)
            owner,_=nm.rotation(poses[indices[parent]],target_noise=True)
            local=nm.product(nm.transposed(owner),child)
            if name not in first:first[name]=local
            delta=nm.product(nm.transposed(first[name]),local)
            angle=math.degrees(math.acos(max(-1.,min(1.,(sum(delta[i][i] for i in range(3))-1)/2))))
            maximum[name]=max(maximum[name],angle)
    return maximum
