"""Bounded source-backed wrist transition correction for private previews."""

import math

from ucc.core.errors import ValidationError

from . import native_math as nm
from .native_skin_policy import CORRECTIVE_POLICIES


def validate_wrist_transitions(profile: dict) -> None:
    if 'wrist_transitions' not in profile:
        return
    if profile.get('skin_deformation_policy') not in CORRECTIVE_POLICIES:
        raise ValidationError('Wrist transitions require saved-skin preview verification')
    declaration = profile['wrist_transitions']
    if (type(declaration) is not dict or set(declaration) != {'schema_version', 'windows'}
            or type(declaration['schema_version']) is not int or declaration['schema_version'] != 1
            or type(declaration['windows']) is not list or not 1 <= len(declaration['windows']) <= 8):
        raise ValidationError('Invalid private wrist transition declaration')
    ends: dict[str, int] = {}
    for window in declaration['windows']:
        if (type(window) is not dict or set(window) != {'side', 'first_frame', 'last_frame'}
                or window['side'] not in ('left', 'right')
                or any(type(window[k]) is not int or abs(window[k]) > 100_000
                       for k in ('first_frame', 'last_frame'))):
            raise ValidationError('Wrist transition needs an exact side and integer frame endpoints')
        first, last, side = window['first_frame'], window['last_frame'], window['side']
        if not 2 <= last - first <= 4 or first <= ends.get(side, -100_001):
            raise ValidationError('Wrist transitions must be ordered, disjoint, and span two to four steps')
        ends[side] = last


def _flatten(matrix: list[list[float]]) -> list[float]:
    return [value for row in matrix for value in row]


def _relative_angle(first: list[list[float]], last: list[list[float]]) -> float:
    relative = nm.product(nm.transposed(first), last)
    trace = sum(relative[i][i] for i in range(3))
    return math.acos(max(-1., min(1., (trace - 1.) / 2.)))


def _shortest_arc(first: list[list[float]], last: list[list[float]], fraction: float) -> list[list[float]]:
    relative = nm.product(nm.transposed(first), last)
    angle = _relative_angle(first, last)
    divisor = 2. * math.sin(angle)
    x, y, z = nm.unit([(relative[2][1] - relative[1][2]) / divisor,
                       (relative[0][2] - relative[2][0]) / divisor,
                       (relative[1][0] - relative[0][1]) / divisor])
    cosine = math.cos(angle * fraction)
    sine = math.sin(angle * fraction)
    complement = 1. - cosine
    step = [
        [cosine + x*x*complement, x*y*complement - z*sine, x*z*complement + y*sine],
        [y*x*complement + z*sine, cosine + y*y*complement, y*z*complement - x*sine],
        [z*x*complement - y*sine, z*y*complement + x*sine, cosine + z*z*complement],
    ]
    return nm.product(first, step)


def preview_source_motion(source: dict, profile: dict) -> dict:
    """Derive preview poses from the already authenticated, unmodified snapshot."""
    if 'wrist_transitions' not in profile:
        return source
    validate_wrist_transitions(profile)
    names = {bone['name']: index for index, bone in enumerate(source['bones'])}
    parents = [names.get(bone['parent']) for bone in source['bones']]
    frames = source['frames']
    derived_frames = frames[:]
    for window in profile['wrist_transitions']['windows']:
        wrist_name = profile['landmarks'][window['side'] + '_hand']['source']
        wrist = names.get(wrist_name)
        if wrist is None or parents[wrist] is None:
            raise ValidationError('Wrist transition requires a measured wrist and parent')
        parent = parents[wrist]
        first = window['first_frame'] - source['first_frame']
        last = window['last_frame'] - source['first_frame']
        if not 0 <= first < last < len(frames):
            raise ValidationError('Wrist transition falls outside the measured source clock')

        subtree = {wrist}
        for index, owner in enumerate(parents):
            if owner in subtree:
                subtree.add(index)
        if len(subtree) == 1:
            raise ValidationError('Wrist transition requires measured hand descendants')

        rotations = []
        for index in range(first, last + 1):
            poses = frames[index]['poses']
            parent_inverse = nm.inverse(nm.rows(poses[parent]))
            local = nm.product(parent_inverse, nm.rows(poses[wrist]))
            rotations.append(nm.rotation(_flatten(local), target_noise=True)[0])
        step_limit = math.radians(80.)
        endpoint_angle = _relative_angle(rotations[0], rotations[-1])
        if (not any(_relative_angle(a, b) > step_limit for a, b in zip(rotations, rotations[1:]))
                or not 1e-6 < endpoint_angle < math.radians(175.)
                or endpoint_angle / (last - first) > step_limit):
            raise ValidationError('Wrist transition does not bound a measured discontinuity')

        for index in range(first + 1, last):
            row = derived_frames[index]
            poses = row['poses'][:]
            parent_pose = nm.rows(poses[parent])
            wrist_pose = nm.rows(poses[wrist])
            local = nm.product(nm.inverse(parent_pose), wrist_pose)
            rotation = _shortest_arc(rotations[0], rotations[-1], (index - first) / (last - first))
            scales = [math.sqrt(sum(local[i][j]**2 for i in range(3))) for j in range(3)]
            basis = [[rotation[i][j]*scales[j] for j in range(3)] + [local[i][3]]
                     for i in range(3)] + [[0., 0., 0., 1.]]
            corrected = nm.product(parent_pose, basis)
            delta = nm.product(corrected, nm.inverse(wrist_pose))
            for descendant in subtree - {wrist}:
                poses[descendant] = _flatten(nm.product(delta, nm.rows(poses[descendant])))
            poses[wrist] = _flatten(corrected)
            derived_frames[index] = {**row, 'poses': poses,
                                     'pose_sha256': nm.pose_digest(row['armature_world'], poses)}
    return {**source, 'frames': derived_frames}
