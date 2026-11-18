"""Admit Unreal native poses, CPU skin and the ordinary preview-world loop."""
from math import isfinite
from struct import Struct
from typing import Callable

from ucc.core.errors import ValidationError
from .unreal_animation_evidence import SOURCE_FRAMES, UnrealAnimationComparison, compare_unreal_animation
from .unreal_bind_math import expected_bone_name


STAGE_POLICY = 'UCC_UNREAL_NATIVE_ANIMATION_STAGE_V1'
OBSERVATION_POLICY = 'UCC_UNREAL_NATIVE_ANIMATION_OBSERVATION_V1'
ASSET_FIELDS = {'mesh', 'skeleton', 'clip'}
FPS = 30
DURATION = SOURCE_FRAMES // FPS
_TICK_MATRIX = Struct('<16f')
_BASIS_NAME = 'UccAnimationBasis'
_BASIS_MATRIX = (0, 100, 0, 0, -100, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 1)


def admit_unreal_animation(*, stage: dict, observation: dict, native_bind: dict, source_bind: dict,
        original_pose: bytes, original_skin: bytes, native_pose: bytes, native_skin: bytes,
        check: Callable[[], None]) -> UnrealAnimationComparison:
    """Bind the fresh observation to one staged set of native assets and source data."""
    stage_fields = ASSET_FIELDS | {'schema_version', 'policy'}
    if (type(stage) is not dict or set(stage) != stage_fields or type(stage['schema_version']) is not int
            or stage['schema_version'] != 1 or stage['policy'] != STAGE_POLICY):
        raise ValidationError('Unreal stage did not report one admitted native animation asset set')
    identities = {stage[key] for key in ASSET_FIELDS if type(stage[key]) is str
                  and stage[key].startswith('/Game/UccAnimation/') and len(stage[key]) <= 256}
    if len(identities) != len(ASSET_FIELDS):
        raise ValidationError('Unreal animation has missing, duplicate or unexpected native package paths')
    fixed = {**{key: stage[key] for key in ASSET_FIELDS},
             'schema_version': 1, 'policy': OBSERVATION_POLICY, 'frames': SOURCE_FRAMES, 'fps': FPS,
             'native_keys': SOURCE_FRAMES + 1, 'endpoint_matches': True,
             'bone_compression': 'AnimCompress_LeastDestructive'}
    if (type(observation) is not dict or set(observation) != set(fixed) | {'bones', 'native_vertices', 'preview_world_ticks'}
            or any(type(observation[key]) is not type(value) or observation[key] != value for key, value in fixed.items())
            or type(observation['bones']) is not int or not 2 <= observation['bones'] <= 512
            or type(observation['native_vertices']) is not int or not 1 <= observation['native_vertices'] <= 100000):
        raise ValidationError('Fresh Unreal observation lacks the exact native 30 Hz clip, endpoint or asset set')
    bind_fields = {'schema_version', 'units', 'bones', 'positions_cm', 'used_skin_bones', 'morph_names'}
    if (type(native_bind) is not dict or set(native_bind) != bind_fields
            or type(native_bind['schema_version']) is not int or native_bind['schema_version'] != 1
            or native_bind['units'] != 'unreal_world_centimeters'
            or type(native_bind['bones']) is not list or len(native_bind['bones']) != observation['bones']
            or type(native_bind['positions_cm']) is not list or len(native_bind['positions_cm']) != observation['native_vertices']):
        raise ValidationError('Unreal bind has an unsupported coordinate system or incomplete native inventory')
    raw_bones = native_bind['bones']
    used = native_bind['used_skin_bones']
    if (type(used) is not list or not used or any(type(i) is not int or not 1 <= i < len(raw_bones) for i in used)
            or sorted(set(used)) != used):
        raise ValidationError('Unreal skin influences must exclude the dedicated import basis')
    for index, row in enumerate(raw_bones):
        if (type(row) is not dict or set(row) != {'name', 'parent', 'rest_world'}
                or type(row['name']) is not str
                or type(row['parent']) is not int or not -1 <= row['parent'] < index):
            raise ValidationError('Unreal bind has an invalid parent-first skeletal hierarchy')
    basis = raw_bones[0]
    rest = basis['rest_world']
    if (basis['name'] != _BASIS_NAME or basis['parent'] != -1 or type(rest) is not list or len(rest) != 16
            or any(not _finite_number(x) or abs(x-y) > .0002 for x, y in zip(rest, _BASIS_MATRIX, strict=True))
            or any(row['parent'] < 0 or row['name'] == _BASIS_NAME for row in raw_bones[1:])):
        raise ValidationError('Unreal animation requires one fixed centimetre/axis import basis')
    if (type(source_bind) is not dict or type(source_bind.get('bones')) is not list
            or type(source_bind.get('vertices')) is not list
            or len(source_bind['bones']) != len(raw_bones) - 1
            or any(type(row) is not dict or type(row.get('name')) is not str for row in source_bind['bones'])
            or not 1 <= len(source_bind['vertices']) <= observation['native_vertices']):
        raise ValidationError('Unreal animation needs the independently reopened Blender bind')
    name_map = {expected_bone_name(row['name']): row['name'] for row in source_bind['bones']}
    if (len({name.casefold() for name in name_map}) != len(raw_bones) - 1
            or set(name_map) != {row['name'] for row in raw_bones[1:]}):
        raise ValidationError('Unreal bone translation requires an exact bijective legacy FBX name map')
    bones = []
    for row in raw_bones[1:]:
        parent = row['parent']
        bones.append({'name': name_map[row['name']],
                      'parent': None if parent == 0 else name_map[raw_bones[parent]['name']],
                      'rest_world': row['rest_world']})
    native_morphs, source_morphs = native_bind['morph_names'], source_bind.get('morphs', {})
    if (type(native_morphs) is not list or type(source_morphs) is not dict
            or any(type(name) is not str for name in native_morphs)
            or len(native_morphs) != len(source_morphs) or set(native_morphs) != set(source_morphs)):
        raise ValidationError('Unreal animation mesh lost an original Blender facial control')
    sample_bytes = _TICK_MATRIX.size * len(raw_bones)
    if len(native_pose) != SOURCE_FRAMES*sample_bytes:
        raise ValidationError('Unreal animation is missing its native basis transform samples')
    trimmed = bytearray()
    for frame in range(SOURCE_FRAMES):
        check()
        start = frame*sample_bytes
        values = _TICK_MATRIX.unpack_from(native_pose, start)
        if any(not _finite_number(x) or abs(x-y) > .0002 for x, y in zip(values, rest, strict=True)):
            raise ValidationError(f'Unreal import basis moved during native sample {frame + 1}')
        trimmed.extend(native_pose[start + _TICK_MATRIX.size:start+sample_bytes])
    comparison = compare_unreal_animation(source_bind_points_m=source_bind['vertices'],
        native_bind_points_cm=native_bind['positions_cm'], source_bones=source_bind['bones'], native_bones=bones,
        source_pose_samples=original_pose, native_pose_samples=bytes(trimmed), source_raw_samples=original_skin,
        native_raw_samples=native_skin, check=check)
    _check_preview(observation['preview_world_ticks'], native_pose, len(raw_bones), check)
    return comparison


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and abs(value) <= 1e8 and isfinite(value)


def _check_preview(rows: object, fixed_pose: bytes, bone_count: int, check: Callable[[], None]) -> None:
    if type(rows) is not list or len(rows) != 7:
        raise ValidationError('Unreal preview did not record a complete tick sequence across the loop')
    previous = 0.
    wrapped = False
    max_change = 0.
    first_pose = None
    for tick, row in enumerate(rows, 1):
        check()
        if (type(row) is not dict or set(row) != {'time_seconds', 'pose_world'}
                or not _finite_number(row['time_seconds'])
                or not 0 <= row['time_seconds'] <= DURATION + .001
                or type(row['pose_world']) is not list or len(row['pose_world']) != bone_count*16
                or any(not _finite_number(value) for value in row['pose_world'])):
            raise ValidationError('Unreal preview tick has an invalid clock or incomplete world pose')
        clock = row['time_seconds']
        sample = (SOURCE_FRAMES - 3 + tick) % SOURCE_FRAMES
        expected_clock = sample / FPS
        difference = abs(clock - expected_clock)
        if difference >= .001 and abs(difference - DURATION) >= .001:
            raise ValidationError('Unreal ordinary preview clock failed to follow the native sequence')
        if clock < previous:
            wrapped = True
        previous = clock
        matrices = row['pose_world']
        if first_pose is None:
            first_pose = matrices
        else:
            max_change = max(max_change, max(abs(x-y) for x, y in zip(first_pose, matrices, strict=True)))
        for bone in range(bone_count):
            offset = (sample * bone_count + bone) * _TICK_MATRIX.size
            expected = _TICK_MATRIX.unpack_from(fixed_pose, offset)
            observed = matrices[bone*16:(bone+1)*16]
            if any(abs(x-y) > (.02 if axis in {3, 7, 11} else .002)
                   for axis, (x, y) in enumerate(zip(expected, observed, strict=True))):
                raise ValidationError('Unreal world-ticked pose differs from the independently checked clock sample')
    if not wrapped or max_change <= 1e-5:
        raise ValidationError('Unreal ordinary preview failed to show a moving native loop wrap')
