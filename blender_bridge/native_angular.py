"""Stable additional-rotation velocity from Blender float32 quaternions."""
import math


def angular_velocity(delta: tuple[float,float,float,float],fps: float) -> tuple[float,float,float]:
    """Use the quaternion vector part; acos(w) loses tiny float32 rotations.

    atan2 remains accurate when w rounds to one. Hemisphere selection keeps
    q/-q equivalent without clamping or relaxing any angular safety bound.
    """
    if (len(delta)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in delta) or
        type(fps) not in (int,float) or not math.isfinite(fps) or not 1<=fps<=240 or math.hypot(*delta)<1e-12):
        raise ValueError('Invalid additional-rotation quaternion or frame rate')
    w,x,y,z=delta
    if w<0:w,x,y,z=-w,-x,-y,-z
    length=math.hypot(x,y,z)
    if length<1e-15:return (0.,0.,0.)
    factor=math.degrees(2*math.atan2(length,w))*fps/length
    return (x*factor,y*factor,z*factor)
