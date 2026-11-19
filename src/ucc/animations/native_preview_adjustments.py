"""Closed source-pose adjustments for authenticated native library previews."""
import math

from ucc.core.errors import ValidationError

from . import native_math as nm
from .native_skin_policy import CORRECTIVE_POLICIES
from .planted_knee import apply_planted_knee, validate_planted_knee
from .wrist_transitions import preview_source_motion, validate_wrist_transitions


PREVIEW_ADJUSTMENT_KEYS = ('wrist_transitions', 'forearm_roll', 'planted_knee')
_MAX_ROLL_TENTHS = 60
_MAX_STEP_TENTHS = 15


def preview_adjustment_declarations(data: dict) -> dict:
    return {key: data[key] for key in PREVIEW_ADJUSTMENT_KEYS if key in data}


def _forearm_pair(profile: dict, side: str) -> tuple[str, str]:
    hand = profile['landmarks'][side + '_hand']
    matches = [row['source'] for row in profile['pairs']
               if row['source_tip'] == hand['source'] and row['target_tip'] == hand['target']]
    if len(matches) != 1:
        raise ValidationError('Forearm roll needs one measured mapped forearm ending at the hand')
    return matches[0], hand['source']


def validate_preview_adjustments(profile: dict) -> None:
    validate_wrist_transitions(profile)
    validate_planted_knee(profile)
    if 'forearm_roll' not in profile:
        return
    if (profile.get('skin_deformation_policy') not in CORRECTIVE_POLICIES
            or 'hand_reference_planes' not in profile):
        raise ValidationError('Forearm roll requires measured hands and saved-skin preview verification')
    declaration = profile['forearm_roll']
    if (type(declaration) is not dict or type(declaration.get('schema_version')) is not int
            or declaration['schema_version'] not in (1,2)):
        raise ValidationError('Invalid private forearm roll declaration')
    calibrated = declaration['schema_version'] == 2
    keys = {'schema_version','windows','baseline_tenths'} if calibrated else {'schema_version','windows'}
    if (set(declaration) != keys or type(declaration['windows']) is not list
            or not (0 if calibrated else 1) <= len(declaration['windows']) <= 4):
        raise ValidationError('Invalid private forearm roll declaration')
    baseline = declaration.get('baseline_tenths',{})
    if calibrated and (type(baseline) is not dict or not baseline or set(baseline)-{'left','right'}
                       or any(type(angle) is not int or not 0 < abs(angle) <= 80 for angle in baseline.values())):
        raise ValidationError('Forearm calibration requires a bounded signed offset for each named side')
    for side in baseline:
        _forearm_pair(profile,side)
    ends: dict[str, int] = {}
    for window in declaration['windows']:
        if (type(window) is not dict or set(window) != {'side', 'first_frame', 'angle_tenths'}
                or window['side'] not in ('left', 'right') or type(window['first_frame']) is not int
                or abs(window['first_frame']) > 100_000):
            raise ValidationError('Forearm roll needs an exact side and integer starting source frame')
        angles = window['angle_tenths']
        if (type(angles) is not list or not 3 <= len(angles) <= 16
                or any(type(angle) is not int or abs(angle) > _MAX_ROLL_TENTHS for angle in angles)
                or angles[0] != 0 or angles[-1] != 0 or not any(angles)
                or any(abs(a - b) > _MAX_STEP_TENTHS for a, b in zip(angles, angles[1:]))):
            raise ValidationError('Forearm roll needs a bounded sequence that starts and ends at zero')
        side, start = window['side'], window['first_frame']
        if any(abs(angle+baseline.get(side,0)) > 90 for angle in angles):
            raise ValidationError('Combined forearm correction exceeds its calibrated roll range')
        if start <= ends.get(side, -100_001):
            raise ValidationError('Forearm roll windows must be ordered and disjoint for each side')
        ends[side] = start + len(angles) - 1
        _forearm_pair(profile, side)


def _roll_basis(forearm: list[float], hand: list[float], angle_tenths: int) -> list[float]:
    arm = nm.rows(forearm)
    x, y, z = nm.unit([hand[i] - forearm[i] for i in (3, 7, 11)])
    angle = math.radians(angle_tenths / 10.)
    c, s = math.cos(angle), math.sin(angle)
    v = 1. - c
    roll = [
        [c + x*x*v, x*y*v - z*s, x*z*v + y*s],
        [y*x*v + z*s, c + y*y*v, y*z*v - x*s],
        [z*x*v - y*s, z*y*v + x*s, c + z*z*v],
    ]
    rotation = nm.product(roll, [row[:3] for row in arm[:3]])
    return [value for row, original in zip(rotation, arm) for value in (*row, original[3])] + arm[3]


def adjusted_native_preview_source(source: dict, profile: dict) -> dict:
    """Leave the measured snapshot and all distal world poses untouched."""
    source = preview_source_motion(source, profile)
    if 'planted_knee' in profile:
        validate_planted_knee(profile)
        source = apply_planted_knee(source, profile)
    if 'forearm_roll' not in profile:
        return source
    # The worker and the independent host evidence reader also check the declaration
    # at intake. This keeps direct callers within the same preview limits.
    validate_preview_adjustments(profile)
    indexes = {bone['name']: i for i, bone in enumerate(source['bones'])}
    frames = source['frames'][:]
    declared = profile['forearm_roll']
    baseline = declared.get('baseline_tenths',{})
    if baseline and len(frames) > 600:
        raise ValidationError('Forearm calibration exceeds the bounded preview clock')
    corrections = [
        (side,0,[angle]*len(frames)) for side,angle in baseline.items()
    ] + [
        (window['side'],window['first_frame']-source['first_frame'],window['angle_tenths'])
        for window in declared['windows']
    ]
    for side,first,angles in corrections:
        forearm_name, hand_name = _forearm_pair(profile,side)
        arm, hand = indexes.get(forearm_name), indexes.get(hand_name)
        if arm is None or hand is None or source['bones'][hand]['parent'] != forearm_name:
            raise ValidationError('Forearm roll requires a measured forearm and its direct hand child')
        if first < 0 or first + len(angles) > len(frames):
            raise ValidationError('Forearm roll falls outside the measured source clock')
        for index, angle in enumerate(angles, first):
            if not angle:
                continue
            row = frames[index]
            poses = row['poses'][:]
            poses[arm] = _roll_basis(poses[arm], poses[hand], angle)
            frames[index] = {**row, 'poses': poses,
                             'pose_sha256': nm.pose_digest(row['armature_world'], poses)}
    return {**source, 'frames': frames}
