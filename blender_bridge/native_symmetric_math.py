"""Independent mathutils shoulder solve; never changes a Blender scene."""
import math

from blender_bridge.native_angular import angular_velocity
from blender_bridge.native_hand_fit import orient


def _matrices(targets, poses):
    from mathutils import Matrix
    if type(poses) is not list or len(poses) != len(targets):
        raise ValueError('Symmetric worker pose coverage differs')
    result = {}
    for name, row in zip(targets, poses):
        if (type(row) is not list or len(row) != 16 or
                any(type(v) not in (int, float) or not -1e6 <= v <= 1e6 or not math.isfinite(v) for v in row) or
                any(abs(row[12+j]-float(j == 3)) > 1e-7 for j in range(4))):
            raise ValueError('Symmetric worker needs finite affine poses')
        m = Matrix([row[j:j+4] for j in range(0, 16, 4)])
        r = m.to_3x3(); gram = r.transposed()@r
        if abs(r.determinant()-1.) > .001 or max(abs(gram[i][j]-float(i == j)) for i in range(3) for j in range(3)) > .001:
            raise ValueError('Symmetric worker rejects reflected, scaled or sheared poses')
        result[name] = m
    return result


def _side(side, original, frame):
    from mathutils import Matrix, Quaternion, Vector
    matrices = {n: m.copy() for n, m in original.items()}
    offset = Vector(side['offsets'][frame-1]); angles = Vector(side['clavicle_rotations'][frame-1])
    if angles.length > 15.+1e-9: raise ValueError('Symmetric worker clavicle exceeds 15 degrees')
    hand_angles = side['hand_rotations'][frame-1] if side['hand_rotations'] else (0., 0., 0.)
    if not offset.length and not angles.length and not any(hand_angles): return matrices
    pivot = original[side['clavicle']].translation.copy()
    rotation = Quaternion(angles.normalized(), math.radians(angles.length)) if angles.length else Quaternion()
    transform = Matrix.Translation(pivot)@rotation.to_matrix().to_4x4()@Matrix.Translation(-pivot)
    for name in side['branch']: matrices[name] = transform@original[name]
    upper, lower, hand = side['chain']
    s, e, w = (matrices[n].translation.copy() for n in (upper, lower, hand))
    target = original[hand].translation+offset; relative = target-w
    moved = max((matrices[n].translation-original[n].translation).length for n in side['chain'])
    maximum = side['maximum']+moved
    # mathutils is float32; the triangle inequality has a bounded numeric margin.
    if relative.length > maximum+1e-6: raise ValueError('Symmetric worker relative displacement exceeds derived bound')
    if relative.length:
        a, b = (e-s).length, (w-e).length; direction = target-s; distance = direction.length
        if min(a, b) < 1e-5 or not abs(a-b)+1e-7 < distance < a+b-1e-7:
            raise ValueError('Symmetric worker endpoint is unreachable without scaling/clamping')
        axis = direction.normalized(); pole = e-s-axis*(e-s).dot(axis)
        if pole.length < min(a, b)*1e-4: raise ValueError('Symmetric worker has an ambiguous straight-arm pole')
        along = (a*a+distance*distance-b*b)/(2*distance)
        elbow = s+axis*along+pole.normalized()*math.sqrt(max(0., a*a-along*along))
        if (elbow-e).length > maximum+1e-6: raise ValueError('Symmetric worker elbow exceeds derived bound')
        for name, old, new, head in ((upper, e-s, elbow-s, s), (lower, w-e, target-elbow, elbow)):
            delta = old.rotation_difference(new)
            if math.hypot(*angular_velocity(tuple(delta), 1.)) > 30.+1e-5:
                raise ValueError('Symmetric worker relative rotation exceeds derived bound')
            matrices[name] = Matrix.LocRotScale(head, delta@matrices[name].to_quaternion(), Vector((1., 1., 1.)))
    for name in side['descendants']:
        matrices[name] = original[name].copy(); matrices[name].translation += offset
    if side['hand_rotations']: matrices = orient(side, matrices, frame)
    for name in side['branch']:
        maximum = side['maximum']
        if name in side['descendants'] and name != hand and side['hand_rotations']:
            radius = (original[name].translation-original[hand].translation).length
            maximum += 2*radius*math.sin(math.radians(math.hypot(*hand_angles))/2)
        if (matrices[name].translation-original[name].translation).length > maximum+1e-6:
            raise ValueError('Symmetric worker exceeds final source-world displacement bound')
        delta = matrices[name].to_quaternion()@original[name].to_quaternion().inverted()
        if math.hypot(*angular_velocity(tuple(delta), 1.)) > 15.+1e-5:
            raise ValueError('Symmetric worker exceeds final 15-degree source-world bound')
    return matrices


def symmetric_world_poses(plan, source_poses, base_poses, frame):
    """Return fresh matrices, preserving the canonical base outside this layer."""
    if type(frame) is not int or not 1 <= frame <= len(plan['active_frames']):
        raise ValueError('Symmetric worker frame differs')
    original = _matrices(plan['targets'], source_poses); base = _matrices(plan['targets'], base_poses)
    if not plan['active_frames'][frame-1]: return base
    left, right = _side(plan['left'], original, frame), _side(plan['right'], original, frame)
    return {n: left[n] if n in plan['left']['branch'] else right[n] if n in plan['right']['branch'] else original[n]
            for n in plan['targets']}


def audit_symmetric(plan, sources, bases, observed):
    """Check both complete declared branches before the eight-joint timing audit."""
    from mathutils import Vector
    count = len(plan['active_frames'])
    if any(type(rows) is not list or len(rows) != count for rows in (sources, bases, observed)):
        raise ValueError('Symmetric worker requires complete observed timeline')
    names = tuple(n for s in ('left', 'right') for n in (*plan[s]['chain'], plan[s]['clavicle']))
    previous = {}; velocities = {n: Vector() for n in names}; maximum_speed = maximum_acceleration = 0.
    for frame, (source, base, actual) in enumerate(zip(sources, bases, observed), 1):
        expected = symmetric_world_poses(plan, source, base, frame)
        measured = _matrices(plan['targets'], actual); original = _matrices(plan['targets'], source)
        for n in plan['targets']:
            if ((expected[n].translation-measured[n].translation).length > 1e-5 or
                    max(abs(expected[n][i][j]-measured[n][i][j]) for i in range(3) for j in range(3)) > 1e-4):
                raise ValueError('Symmetric worker observed pose differs from declared layer or retained base')
        for n in names:
            correction = measured[n].to_quaternion()@original[n].to_quaternion().inverted()
            velocity = Vector() if frame == 1 else Vector(angular_velocity(tuple(correction@previous[n].inverted()), plan['fps']))
            speed = velocity.length; acceleration = (velocity-velocities[n]).length*plan['fps']
            if speed > 90.+.01 or acceleration > 900.+.1:
                raise ValueError('Symmetric worker correction has discontinuous angular motion')
            maximum_speed = max(maximum_speed, speed); maximum_acceleration = max(maximum_acceleration, acceleration)
            previous[n] = correction; velocities[n] = velocity
    end = max(v.length*plan['fps'] for v in velocities.values())
    if end > 900.+.1: raise ValueError('Symmetric worker ends with discontinuous angular motion')
    return {'frames': count, 'tracked_joints': len(names), 'max_speed_degrees_s': maximum_speed,
            'max_acceleration_degrees_s2': max(maximum_acceleration, end)}
