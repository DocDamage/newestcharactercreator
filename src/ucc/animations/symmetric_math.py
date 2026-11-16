"""Pure four-bone shoulder correction with final source-world safety bounds."""
import math
from typing import Callable

from ucc.core.errors import ValidationError
from . import native_math as nm
from .contact_fit import _checked_pose, _rotation_vector
from .hand_fit import orient_hand
from .symmetric_fit import ShoulderFit, SymmetricFit


def _sub(a, b): return tuple(x-y for x, y in zip(a, b))
def _add(a, b): return tuple(x+y for x, y in zip(a, b))
def _mul(a, s): return tuple(x*s for x in a)
def _dot(a, b): return sum(x*y for x, y in zip(a, b))
def _point(m): return tuple(m[j*4+3] for j in range(3))


def _unit(a):
    length = math.hypot(*a)
    if not 1e-8 < length < 1e6: raise ValidationError('Degenerate symmetric fitting limb direction')
    return _mul(a, 1/length)


def _rotation(vector):
    degrees = math.hypot(*vector)
    if not math.isfinite(degrees) or degrees > 15.+1e-9:
        raise ValidationError('Symmetric clavicle rotation exceeds its fixed 15-degree bound')
    if degrees < 1e-12: return [[float(j == k) for k in range(3)] for j in range(3)]
    x, y, z = (v/degrees for v in vector)
    angle = math.radians(degrees); sine = math.sin(angle); cosine = 1-math.cos(angle)
    cross = [[0., -z, y], [z, 0., -x], [-y, x, 0.]]; squared = nm.product(cross, cross)
    return [[float(j == k)+sine*cross[j][k]+cosine*squared[j][k] for k in range(3)] for j in range(3)]


def _between(a, b):
    a, b = _unit(a), _unit(b); cosine = max(-1., min(1., _dot(a, b)))
    # A rotated shoulder starts in a different frame. The relative solve has a
    # derived 15+15 degree bound; final source-world rotations still cap at 15.
    if math.degrees(math.acos(cosine)) > 30.+1e-8:
        raise ValidationError('Symmetric relative arm rotation exceeds its derived bound')
    x, y, z = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    cross = [[0., -z, y], [z, 0., -x], [-y, x, 0.]]; squared = nm.product(cross, cross)
    return [[float(j == k)+cross[j][k]+squared[j][k]/(1+cosine) for k in range(3)] for j in range(3)]


def _relative_arm(side: ShoulderFit, poses: list[list[float]], frame: int,
                  offset: tuple[float, float, float], maximum: float) -> list[list[float]]:
    result = [list(m) for m in poses]
    if not any(offset): return result
    indices = {n: i for i, n in enumerate(side.arm.targets)}
    u, l, h = (indices[n] for n in side.arm.chain)
    shoulder, elbow, wrist = (_point(poses[i]) for i in (u, l, h))
    first, second = _sub(elbow, shoulder), _sub(wrist, elbow)
    a, b = math.hypot(*first), math.hypot(*second)
    target = _add(wrist, offset); direction = _sub(target, shoulder); distance = math.hypot(*direction)
    if min(a, b) < 1e-5 or not abs(a-b)+1e-7 < distance < a+b-1e-7:
        raise ValidationError('Symmetric fitting endpoint is unreachable; no scaling or clamping')
    axis = _unit(direction); pole = _sub(first, _mul(axis, _dot(first, axis)))
    if math.hypot(*pole) < min(a, b)*1e-4:
        raise ValidationError('Symmetric fitting cannot infer a straight-arm elbow pole')
    along = (a*a+distance*distance-b*b)/(2*distance)
    height = math.sqrt(max(0., a*a-along*along))
    new_elbow = _add(shoulder, _add(_mul(axis, along), _mul(_unit(pole), height)))
    if math.dist(new_elbow, elbow) > maximum+1e-9:
        raise ValidationError('Symmetric relative elbow exceeds its derived displacement bound')
    for i, old, new, head in ((u, first, _sub(new_elbow, shoulder), shoulder),
                              (l, second, _sub(target, new_elbow), new_elbow)):
        rotation = nm.product(_between(old, new), [[poses[i][j*4+k] for k in range(3)] for j in range(3)])
        for j in range(3): result[i][j*4:j*4+3] = rotation[j]; result[i][j*4+3] = head[j]
    for name in side.arm.hand_descendants:
        i = indices[name]
        for j in range(3): result[i][j*4+3] += offset[j]
    return result


def _side_frame(side: ShoulderFit, poses: list[list[float]], frame: int) -> list[list[float]]:
    arm = side.arm; offset = arm.offsets[frame-1]; angles = side.rotations[frame-1]
    hand_angles = arm.hand_rotations[frame-1] if arm.hand_rotations else (0., 0., 0.)
    if not any(offset) and not any(angles) and not any(hand_angles): return [list(m) for m in poses]
    delta = _rotation(angles); indices = {n: i for i, n in enumerate(arm.targets)}
    pivot = _point(poses[indices[side.clavicle]]); intermediate = [list(m) for m in poses]
    for name in side.branch:
        i = indices[name]; point = _sub(_point(poses[i]), pivot)
        rotation = nm.product(delta, [[poses[i][j*4+k] for k in range(3)] for j in range(3)])
        for j in range(3):
            intermediate[i][j*4:j*4+3] = rotation[j]
            intermediate[i][j*4+3] = pivot[j]+sum(delta[j][k]*point[k] for k in range(3))
    hand = indices[arm.chain[2]]
    relative = tuple(poses[hand][j*4+3]+offset[j]-intermediate[hand][j*4+3] for j in range(3))
    moved = max(math.dist(_point(intermediate[indices[n]]), _point(poses[indices[n]])) for n in arm.chain)
    maximum = arm.maximum_offset+moved
    if math.hypot(*relative) > maximum+1e-9:
        raise ValidationError('Symmetric intermediate offset violates its triangle-inequality bound')
    result = _relative_arm(side, intermediate, frame, relative, maximum)
    # Preserve the source-driven global hand orientation and intrinsic fingers,
    # then apply only the explicitly declared local hand rotation.
    for name in arm.hand_descendants:
        i = indices[name]; result[i] = list(poses[i])
        for j in range(3): result[i][j*4+3] += offset[j]
    if arm.hand_rotations: result = orient_hand(arm, result, frame)
    for name in side.branch:
        i = indices[name]; maximum = arm.maximum_offset
        if name in arm.hand_descendants and name != arm.chain[2] and arm.hand_rotations:
            radius = math.dist(_point(poses[i]), _point(poses[hand]))
            maximum += 2*radius*math.sin(math.radians(math.hypot(*hand_angles))/2)
        if math.dist(_point(result[i]), _point(poses[i])) > maximum+1e-9:
            raise ValidationError('Symmetric final joint exceeds its fixed source-world displacement bound')
        old, _ = nm.rotation(poses[i], target_noise=True); new, _ = nm.rotation(result[i], target_noise=True)
        if math.hypot(*_rotation_vector(nm.product(new, nm.transposed(old)))) > 15.+1e-6:
            raise ValidationError('Symmetric final rotation exceeds its fixed 15-degree source-world bound')
    return result


def fit_symmetric_frame(plan: SymmetricFit, original: list[list[float]],
                        base_poses: list[list[float]], frame: int) -> list[list[float]]:
    """Keep every inactive base matrix; change only the declared disjoint branches."""
    if (type(frame) is not int or not 1 <= frame <= len(plan.active_frames) or
            type(original) is not list or type(base_poses) is not list or
            len(original) != len(plan.targets) or len(base_poses) != len(plan.targets)):
        raise ValidationError('Symmetric fitting pose or frame coverage differs')
    for row in (*original, *base_poses): _checked_pose(row)
    if not plan.active_frames[frame-1]: return [list(m) for m in base_poses]
    left = _side_frame(plan.left, original, frame); right = _side_frame(plan.right, original, frame)
    left_names, right_names = set(plan.left.branch), set(plan.right.branch)
    return [left[i] if n in left_names else right[i] if n in right_names else list(original[i])
            for i, n in enumerate(plan.targets)]


def verify_symmetric_sequence(plan: SymmetricFit, originals: list, bases: list, actuals: list,
                              *, cancel_check: Callable[[], None] = lambda: None) -> dict:
    """Audit complete combined poses before measuring either shoulder's timing."""
    count = len(plan.active_frames)
    if any(type(v) is not list or len(v) != count for v in (originals, bases, actuals)):
        raise ValidationError('Symmetric fitting angular audit requires the complete sequence')
    names = (*plan.left.arm.chain, plan.left.clavicle, *plan.right.arm.chain, plan.right.clavicle)
    indices = {n: plan.targets.index(n) for n in names}
    previous = {}; velocities = {n: (0., 0., 0.) for n in names}
    maximum_speed = maximum_acceleration = 0.
    for frame, (original, base, actual) in enumerate(zip(originals, bases, actuals), 1):
        cancel_check(); expected = fit_symmetric_frame(plan, original, base, frame)
        if type(actual) is not list or len(actual) != len(expected):
            raise ValidationError('Symmetric fitting observations are incomplete')
        for wanted, measured in zip(expected, actual):
            _checked_pose(measured)
            if any(abs(a-b) > (1e-5 if j % 4 == 3 else 1e-4) for j, (a, b) in enumerate(zip(wanted, measured))):
                raise ValidationError('Actual symmetric pose differs from its declared branches or retained base')
        for name, i in indices.items():
            old, _ = nm.rotation(original[i], target_noise=True); new, _ = nm.rotation(actual[i], target_noise=True)
            correction = nm.product(new, nm.transposed(old))
            velocity = ((0., 0., 0.) if frame == 1 else tuple(v*plan.fps for v in
                        _rotation_vector(nm.product(correction, nm.transposed(previous[name])))))
            speed = math.hypot(*velocity); acceleration = math.dist(velocity, velocities[name])*plan.fps
            if speed > 90.+.01 or acceleration > 900.+.1:
                raise ValidationError('Symmetric correction has discontinuous angular motion')
            maximum_speed = max(maximum_speed, speed); maximum_acceleration = max(maximum_acceleration, acceleration)
            previous[name] = correction; velocities[name] = velocity
    end = max(math.hypot(*v)*plan.fps for v in velocities.values())
    if end > 900.+.1: raise ValidationError('Symmetric correction ends with discontinuous angular motion')
    return {'frames': count, 'tracked_joints': len(indices), 'max_speed_degrees_s': maximum_speed,
            'max_acceleration_degrees_s2': max(maximum_acceleration, end)}
