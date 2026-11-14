"""Pure common-anatomy reference math for native global rest/pose rotations."""
from __future__ import annotations
import math
from dataclasses import dataclass

from blender_bridge.rest_calibration import (
    Matrix3, Vector3, unit, dot, cross, norm, multiply, transpose, transform, validate_rotation,
)

CONVENTION = "NATIVE_ANATOMICAL_REFERENCE_V1"


@dataclass
class RootRotation:
    """Rigid character turning has no anatomical swing/twist limit."""
    previous: tuple | None = None
    samples: int = 0
    maximum_step: float = 0.
    maximum_frame: int = 1

    def add(self, values, frame):
        from blender_bridge.motion_quality import checked_quaternion
        q=checked_quaternion(values)
        if type(frame) is not int or frame!=self.samples+1:
            raise ValueError("Native root rotations require every frame")
        dot=sum(a*b for a,b in zip(self.previous,q)) if self.previous else q[0]
        if dot<0: q=tuple(-x for x in q)
        step=math.degrees(2*math.acos(min(1.,abs(dot)))) if self.previous else 0.
        if step>80: raise ValueError("Discontinuous native root rotation")
        if step>self.maximum_step: self.maximum_step,self.maximum_frame=step,frame
        self.previous=q;self.samples+=1
        return q


def subtract(a, b):
    return tuple(x-y for x,y in zip(a,b))


def _columns(x, y, z):
    result = tuple(tuple(v[i] for v in (x,y,z)) for i in range(3))
    validate_rotation(result)
    return result


def body_frame(left: Vector3, right: Vector3, head: Vector3) -> tuple[Matrix3,float]:
    middle = tuple((a+b)/2 for a,b in zip(left,right))
    vertical = subtract(head,middle)
    height = norm(vertical)
    if not .1 < height < 10:
        raise ValueError("Native body landmark height is incompatible with world-meter intake")
    z = unit(vertical)
    across = subtract(left,right)
    if not .02*height < norm(across) < height:
        raise ValueError("Native hip landmarks are degenerate or incompatible")
    x = unit(tuple(across[i]-z[i]*dot(across,z) for i in range(3)))
    return _columns(x,unit(cross(z,x)),z),height


def anatomy_frame(direction: Vector3, secondary: Vector3) -> Matrix3:
    y = unit(direction)
    hint = unit(secondary)
    if abs(dot(y,hint)) > .985:
        raise ValueError("Anatomical segment and secondary direction are nearly parallel")
    z = unit(tuple(hint[i]-y[i]*dot(y,hint) for i in range(3)))
    return _columns(unit(cross(y,z)),y,z)


def target_reference(source_segment: Vector3, target_segment: Vector3,
                     source_secondary: Vector3, target_secondary: Vector3,
                     axes: Matrix3, target_bind: Matrix3) -> tuple[Matrix3,float]:
    """Align actual joint segments, retaining the target's measured bind roll."""
    for rotation in (axes,target_bind):
        validate_rotation(rotation)
    source = anatomy_frame(source_segment,source_secondary)
    target = anatomy_frame(target_segment,target_secondary)
    alignment = multiply(multiply(axes,source),transpose(target))
    reference = multiply(alignment,target_bind)
    validate_rotation(reference)
    residual = norm(subtract(transform(alignment,unit(target_segment)),
                             transform(axes,unit(source_segment))))
    if residual > 1e-5:
        raise ValueError("Common anatomical reference segment alignment failed")
    return reference,residual


def transport_global(source_bind: Matrix3, source_pose: Matrix3,
                     axes: Matrix3, reference: Matrix3) -> Matrix3:
    """C * (S_pose * S_bind.T) * C.T * reference; never subtract frame 1."""
    for rotation in (source_bind,source_pose,axes,reference):
        validate_rotation(rotation)
    delta = multiply(source_pose,transpose(source_bind))
    result = multiply(multiply(multiply(axes,delta),transpose(axes)),reference)
    validate_rotation(result)
    return result


def nearest_mapped_parent(name: str, parents: dict, mapped: set[str]) -> str | None:
    seen = {name}
    parent = parents[name]
    while parent is not None and parent not in mapped:
        if parent in seen or parent not in parents:
            raise ValueError("Cyclic or incomplete native skeleton")
        seen.add(parent)
        parent = parents[parent]
    return parent


def check_mapping_hierarchy(pairs: list[dict], source_parents: dict, target_parents: dict) -> list[str]:
    mapping = {p["source"]:p["target"] for p in pairs}
    sources,targets = set(mapping),set(mapping.values())
    if (sources-set(source_parents) or targets-set(target_parents) or
            pairs[0]["source"] != "@ARMATURE" or target_parents[pairs[0]["target"]] is not None or
            sum(p is None for p in target_parents.values()) != 1):
        raise ValueError("Native map needs one target root and existing source/target bones")
    for row in pairs:
        source,target = row["source"],row["target"]
        ancestor = nearest_mapped_parent(source,source_parents,sources)
        target_ancestor = nearest_mapped_parent(target,target_parents,targets)
        if (mapping.get(ancestor) if ancestor else None) != target_ancestor:
            raise ValueError("Native source/target nearest mapped ancestors differ: "+source)
        for tip,name,parents in ((row["source_tip"],source,source_parents),(row["target_tip"],target,target_parents)):
            if tip is None:
                continue
            if tip not in parents or tip == name:
                raise ValueError("Native anatomical tip must be a strict descendant")
            parent = parents[tip]
            seen = set()
            while parent != name and parent is not None:
                if parent in seen:
                    raise ValueError("Native anatomical tip hierarchy is cyclic")
                seen.add(parent)
                parent = parents[parent]
            if parent != name:
                raise ValueError("Native anatomical tip crosses a branch")
    ordered,remaining = [],dict(target_parents)
    while remaining:
        ready = [n for n,p in remaining.items() if p is None or p in ordered]
        if not ready:
            raise ValueError("Target hierarchy is cyclic or incomplete")
        for name in ready:
            ordered.append(name)
            del remaining[name]
    return ordered
