"""Bounded target-hand local rotation vectors; no source-rest reinterpretation."""
from __future__ import annotations
import math
from typing import TYPE_CHECKING

from ucc.core.errors import ValidationError
from . import native_math as nm

if TYPE_CHECKING:
    from .contact_fit import ContactFit

POLICY = 'BOUNDED_NATIVE_ARM_HAND_IK_V2'


def read_rotations(rows: list[dict], fps: float) -> tuple[tuple[float,float,float], ...]:
    values=[]
    for row in rows:
        vector=row.get('hand_rotation_local_degrees')
        if (type(vector) is not list or len(vector)!=3 or
            any(type(v) not in (float,int) or not -15.<=v<=15. for v in vector) or
            math.hypot(*vector)>15.+1e-12):
            raise ValidationError('Hand fitting requires finite local rotation vectors bounded to 15 degrees')
        values.append(tuple(float(v) for v in vector))
    if values[0]!=(0.,0.,0.) or values[-1]!=(0.,0.,0.) or not any(math.hypot(*v)>1e-7 for v in values):
        raise ValidationError('Hand fitting requires unchanged endpoints and a nonzero hand correction')
    speeds=[(0.,0.,0.)]+[tuple((b[i]-a[i])*fps for i in range(3)) for a,b in zip(values,values[1:])]+[(0.,0.,0.)]
    if (any(math.hypot(*v)>90.+1e-9 for v in speeds) or
        any(math.dist(a,b)*fps>900.+1e-9 for a,b in zip(speeds,speeds[1:]))):
        raise ValidationError('Hand fitting local rotation speed or acceleration exceeds fixed limits')
    return tuple(values)


def orient_hand(plan: ContactFit, result: list[list[float]], frame: int) -> list[list[float]]:
    """Rodrigues rotation in the original posed hand frame, around its fitted head.

    Rotate complete mapped hand descendants rigidly; intrinsic finger poses
    and all arm/head positions remain unchanged. Helpers stay under the actual
    Blender hierarchy and must still pass saved-pose reproduction.
    """
    vector=plan.hand_rotations[frame-1]
    degrees=math.hypot(*vector)
    if degrees==0.:return result
    axis=tuple(v/degrees for v in vector);x,y,z=axis
    cross=[[0.,-z,y],[z,0.,-x],[-y,x,0.]]
    squared=nm.product(cross,cross);angle=math.radians(degrees)
    local=[[float(i==j)+math.sin(angle)*cross[i][j]+(1-math.cos(angle))*squared[i][j]
            for j in range(3)] for i in range(3)]
    indices={name:i for i,name in enumerate(plan.targets)}
    hand=result[indices[plan.chain[2]]]
    rotation=[[hand[r*4+c] for c in range(3)] for r in range(3)]
    world=nm.product(nm.product(rotation,local),nm.transposed(rotation))
    pivot=tuple(hand[r*4+3] for r in range(3))
    for name in plan.hand_descendants:
        i=indices[name];matrix=result[i]
        orientation=nm.product(world,[[matrix[r*4+c] for c in range(3)] for r in range(3)])
        relative=tuple(matrix[r*4+3]-pivot[r] for r in range(3))
        for r in range(3):
            matrix[r*4:r*4+3]=orientation[r]
            matrix[r*4+3]=pivot[r]+sum(world[r][c]*relative[c] for c in range(3))
    return result
