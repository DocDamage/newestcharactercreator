"""Build the fixed MPFB same-rig map for an independently authenticated original walk."""

from collections.abc import Callable
import math

from ucc.core.errors import ValidationError
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import checked_sha, closed, document_sha256
from .authored_idle_mapping import FRAME_PROFILE, SOURCE_PROFILE, same_rig_profile
from .authored_idle_mapping_math import check_same_rig_full_clock, need
from .fbx_snapshot import _matrix, validate_snapshot
from .native_math import body, point, product, rows
from .native_palms import palm_normal, validate_palm_hierarchy
from .native_profile import validate_native_profile

WALK_WORLD_Z_M = -.045


def _difference(a, b) -> float:
    return max(abs(x - y) for row_a, row_b in zip(a, b, strict=True)
               for x, y in zip(row_a, row_b, strict=True))


def _geometry(profile: dict, points: dict, domain: str) -> tuple[list, float]:
    landmarks = {name: points[pair[domain]] for name, pair in profile['landmarks'].items()}
    left, right, head = (landmarks[name] for name in ('left_hip', 'right_hip', 'head'))
    axes, height = body(left, right, head)
    need(.02 * height < math.dist(left, right) < height,
         'Original walk neutral hip span is incompatible with the body height')
    center = [(a+b)/2 for a,b in zip(left, right, strict=True)]
    for side, sign in (('left', 1), ('right', -1)):
        for joint, limits in (('hand', (-.5, 1.5)), ('foot', (-2., -.1))):
            vector = [a-b for a,b in zip(landmarks[f'{side}_{joint}'], center, strict=True)]
            lateral = sum(value*axis[0] for value,axis in zip(vector, axes, strict=True))
            vertical = sum(value*axis[2] for value,axis in zip(vector, axes, strict=True))
            need(sign*lateral > .02*height and limits[0]*height < vertical < limits[1]*height,
                 'Original walk hand or foot landmark has unsupported sidedness or height')
        plane = profile['hand_reference_planes']['planes'][side]
        corners = {'wrist': landmarks[f'{side}_hand'],
                   **{name: points[pair[domain]] for name, pair in plane.items()}}
        palm_normal(corners, height)
    return axes, height


def _measured_points(frame: dict, bind: list, bone_count: int) -> dict:
    anatomy = closed(frame['anatomy'], {'axes', 'hands', 'bones'})
    bones = anatomy['bones']
    need(type(bones) is list and len(bones) == bone_count,
         'Original walk needs the complete measured neutral rest')
    rig_world = frame['neutral']['rig_world']
    _matrix(rig_world)
    rig_world = rows(rig_world)
    need(_difference(bind, rig_world) <= 1e-6,
         'Original walk FBX static armature bind differs from the measured neutral object')
    points = {}
    hierarchy = []
    for bone in bones:
        name, parent = bone['name'], bone['parent']
        need(type(name) is str and name and name not in points and (parent is None or parent in points),
             'Original walk measured rest hierarchy is duplicated or unordered')
        _matrix(bone['rest_local'])
        _matrix(bone['rest_world'])
        rest = rows(bone['rest_world'])
        head = bone['head_world']
        need(type(head) is list and len(head) == 3
             and all(type(value) in (int, float) and math.isfinite(value) for value in head)
             and math.dist(head, [row[3] for row in rest[:3]]) <= 1e-5
             and _difference(product(rig_world, rows(bone['rest_local'])), rest) <= 1e-4,
             'Original walk measured world and local bone rest disagree')
        points[name] = head
        hierarchy.append({'name': name, 'parent': parent})
    need(frame['skeleton_fingerprint'] == document_sha256({'profile': SOURCE_PROFILE, 'bones': hierarchy}),
         'Original walk measured skeleton fingerprint differs from the exact hierarchy')
    return points


def _check_tips(profile: dict, parents: dict) -> None:
    # Source and target have the same named hierarchy and identity pairs.
    # The virtual exported object is the sole exception and has no bone tip.
    for pair in profile['pairs'][1:]:
        tip = pair['source_tip']
        if tip is None:
            continue
        ancestor = parents.get(tip)
        while ancestor is not None and ancestor != pair['source']:
            ancestor = parents[ancestor]
        need(ancestor is not None, 'Original walk anatomical tip must descend from its mapped joint')


def _build_profile(frame: dict, snapshot: dict, source_sha256: str, snapshot_sha256: str,
                   target_master_sha256: str, cancel_check: Callable[[], None]) -> dict:
    for pin in (source_sha256, snapshot_sha256, target_master_sha256):
        checked_sha(pin)
    cancel_check()
    measured = closed(frame, {'schema_version', 'profile', 'source_profile', 'target',
                              'skeleton_fingerprint', 'anatomy', 'neutral', 'sole_patches'})
    target = TargetActionTarget.from_dict(measured['target'])
    need(type(measured['schema_version']) is int and measured['schema_version'] == 1
         and measured['profile'] == FRAME_PROFILE and measured['source_profile'] == SOURCE_PROFILE
         and target.master_sha256 == target_master_sha256,
         'Original walk needs the measured neutral frame of the selected exact master')
    observed = validate_snapshot(snapshot, source_sha256, cancel_check=cancel_check)
    need(tuple(observed[key] for key in ('bone_count','root_count','frame_count','first_frame','last_frame','fps'))
         == (163, 1, 300, 2, 301, 30.),
         'Original walk needs one complete MPFB skeleton and all 300 source samples at 30 Hz')

    profile = same_rig_profile(source_sha256, snapshot_sha256, target_master_sha256)
    validate_native_profile(profile, source_sha256, snapshot_sha256, target_master_sha256)
    bind = rows(snapshot['armature_rest_world'])
    target_points = _measured_points(measured, bind, observed['bone_count'])
    source = {bone['name']: point(bind, bone['head']) for bone in snapshot['bones']}
    source_axes, source_height = _geometry(profile, source, 'source')
    target_axes, target_height = _geometry(profile, target_points, 'target')
    need(.9999 <= target_height/source_height <= 1.0001 and _difference(source_axes, target_axes) <= 1e-4,
         'Original walk source and target rest body basis or height differ')

    static_scale = math.hypot(*(row[0] for row in bind[:3]))
    mapped = {pair['source'] for pair in profile['pairs'][1:]}
    check_same_rig_full_clock(snapshot, measured, mapped,
                              cancel_check=cancel_check, armature_world_z_offset_m=WALK_WORLD_Z_M,
                              source_height_m=source_height / static_scale)
    parents = {bone['name']: bone['parent'] for bone in snapshot['bones']}
    _check_tips(profile, parents)
    validate_palm_hierarchy(profile, parents, 'source')
    validate_palm_hierarchy(profile, parents, 'target')
    cancel_check()
    return profile


def build_original_walk_profile(frame: dict, snapshot: dict, *, source_sha256: str, snapshot_sha256: str,
                                target_master_sha256: str, cancel_check: Callable[[], None]) -> dict:
    """Check the full walking snapshot and describe its same-rig target mapping.

    The caller authenticates the original bytes and provenance. The supplied SHA
    pins that native snapshot representation, which need not be canonical JSON.
    This check performs no I/O or animation admission.
    """
    try:
        return _build_profile(frame, snapshot, source_sha256, snapshot_sha256, target_master_sha256, cancel_check)
    except ValidationError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError) as error:
        raise ValidationError('Malformed or incomplete original walk mapping inputs') from error
