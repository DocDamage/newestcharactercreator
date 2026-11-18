"""Full-clock identity-omission checks for one admitted original MPFB source."""
import math

from ucc.core.errors import ValidationError
from .fbx_snapshot import _matrix
from .native_math import inverse, product, rows


def need(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def _difference(a: list, b: list) -> float:
    return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def _unit_scale(matrix: list) -> None:
    lengths = [math.sqrt(sum(matrix[i][j]**2 for i in range(3))) for j in range(3)]
    need(max(abs(value-1) for value in lengths) <= 1e-4,
         'Original idle mapping cannot drop source scale')


def check_same_rig_full_clock(snapshot: dict, frame: dict, mapped_sources: set[str]) -> None:
    """Compare imported rest to measured target, never infer rig from a filename.

    Caller first validates the complete native snapshot and authenticates the
    frame through the current candidate loader. An omitted bone must retain its
    local neutral transform at EVERY sample, even if all mapped joints match.
    The source's armature-object root remains fixed throughout this idle.
    """
    anatomy = frame.get('anatomy')
    need(type(anatomy) is dict and type(anatomy.get('bones')) is list,
         'Original idle mapping needs actual complete measured anatomy')
    measured = anatomy['bones']
    source = snapshot['bones']
    need(len(measured) == len(source) == 163,
         'Original idle mapping supports the measured complete 163-bone MPFB rig')
    expected = {}
    for item in measured:
        need(type(item) is dict and set(item) == {'name','parent','head_world','tail_world','rest_local','rest_world'}
             and type(item['name']) is str and item['name'] not in expected,
             'Original idle measured topology is incomplete or duplicated')
        expected[item['name']] = item
        # Source matrices were checked by validate_snapshot. Frame matrices
        # need the same finite/proper-rotation guard before max/difference;
        # an authenticated hash never replaces numerical validity.
        for key in ('rest_local','rest_world'):
            _matrix(item[key])
            _unit_scale(rows(item[key]))
    neutral = frame.get('neutral')
    need(type(neutral) is dict, 'Original idle measured neutral state is missing')
    for key in ('rig_world','human_world'):
        need(key in neutral, 'Original idle measured neutral transforms are missing')
        _matrix(neutral[key])
        _unit_scale(rows(neutral[key]))
    need(set(expected) == {item['name'] for item in source},
         'Original idle source and measured target bone membership differ')
    armature_rest = rows(snapshot['armature_rest_world'])
    _unit_scale(armature_rest)
    rest = {}
    parents = {}
    for item in source:
        name = item['name']; measured_bone = expected[name]
        need(item['parent'] == measured_bone['parent'],
             'Original idle source and measured target parent hierarchy differ')
        parents[name] = item['parent']
        rest[name] = rows(item['matrix'])
        target_world = measured_bone['rest_world']
        need(type(target_world) is list and len(target_world) == 16
             and all(type(v) in (int,float) and math.isfinite(v) for v in target_world),
             'Original idle measured rest matrix is malformed')
        need(_difference(product(armature_rest, rest[name]), rows(target_world)) <= 1e-4,
             'Original idle source rest differs from the exact measured target')
    need(parents.get('root', 'missing') is None and sum(v is None for v in parents.values()) == 1,
         'Original idle mapping needs the actual single MPFB root')
    local_rest = {name: product(inverse(rest[parent]), rest[name]) if parent else rest[name]
                  for name,parent in parents.items()}
    for matrix in local_rest.values():
        _unit_scale(matrix)
    need(mapped_sources <= set(parents) and 'root' not in mapped_sources,
         'Original idle source root must remain an independently checked identity omission')
    for sample in snapshot['frames']:
        world = rows(sample['armature_world'])
        _unit_scale(world)
        need(_difference(world, armature_rest) <= 1e-6,
             'Original idle source moved its neutral armature-object root')
        poses = {item['name']: rows(pose) for item,pose in zip(source,sample['poses'])}
        for name,parent in parents.items():
            local = product(inverse(poses[parent]), poses[name]) if parent else poses[name]
            _unit_scale(local)
            neutral = local_rest[name]
            need(max(abs(local[i][3]-neutral[i][3]) for i in range(3)) <= 1e-5,
                 'Original idle source has unsupported animated local translation')
            if name not in mapped_sources:
                need(_difference(local, neutral) <= 1e-5,
                     'Original idle mapping would silently drop an animated source bone')
