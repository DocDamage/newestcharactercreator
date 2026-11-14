"""Independent, closed Blender-side admission for the bundled facial recipe.

This module deliberately does not import ucc-core. Fixed staged basenames and
asset digests prevent a recipe from selecting arbitrary files or shape keys.
"""
from hashlib import sha256
import json
import math
from pathlib import Path

POLICY = 'BOUNDED_MPFB_NOSE_WIDTH_V1'
VERSION = '2.0.18'
BASE_SHA = '8e761e6624b8f54536409135d1636da63b32486a90d4897f84e121d144f6fb4c'
RIG_SHA = '8b949de35c2dd70dbb5094e57a8586c3b9a9f650775a293212581a8f67be6797'
TARGETS = (
    ('narrow', 'nose-scale-horiz-decr', '95d8dc4a3589bbb6105191abc6e3cae47c3c424ce189b5f0a611dc098806060d'),
    ('wide', 'nose-scale-horiz-incr', 'ba550cc15c894a4412bb368acc92bd6ad94bbb63d0135c561fe30230ef6344bd'),
)
TOPOLOGY_SHA = 'c4f5340980d1dc75825da4dc1a8c2a8befa31b38be88f4838ea1688452a26989'


def digest(path: Path) -> str:
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate facial JSON field: '+key)
        result[key] = value
    return result


def read_json(path: Path, expected: str, limit: int = 65536):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit or digest(path) != expected:
        raise ValueError('Missing, oversized or changed facial input: '+path.name)
    def bad_constant(value):
        raise ValueError('Nonfinite facial JSON constant: '+value)
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs, parse_constant=bad_constant)


def recipe(raw: object, master_sha: str) -> dict:
    fields = {'schema_version', 'policy', 'family', 'mpfb_version', 'bindings', 'parameters', 'targets'}
    if type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int:
        raise ValueError('Invalid facial recipe fields')
    params = raw['parameters']
    if type(params) is not dict or set(params) != {'nose_width'}:
        raise ValueError('Facial recipe requires explicit nose_width')
    value = params['nose_width']
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError('Facial nose_width is outside its finite bounds')
    bindings = {'master_sha256': master_sha, 'base_sha256': BASE_SHA, 'rig_sha256': RIG_SHA,
                **{role+'_target_sha256': sha for role, _, sha in TARGETS}}
    weights = (max(0., .5-value), max(0., value-.5))
    targets = raw['targets']
    if type(targets) is not list or len(targets) != 2 or any(
            type(t) is not dict or type(t.get('weight')) not in (int, float) for t in targets):
        raise ValueError('Invalid facial target records')
    expected = {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1', 'mpfb_version': VERSION,
                'bindings': bindings, 'parameters': {'nose_width': float(value)},
                'targets': [{'name': name, 'file': name+'.target.gz', 'weight': weight}
                            for (_, name, _), weight in zip(TARGETS, weights)]}
    if raw != expected:
        raise ValueError('Facial recipe differs from independent pinned policy')
    return expected


def check_inputs(root: Path, options: dict, *, verify: bool = False) -> dict:
    names = {'candidate.blend': 'master_sha256', 'face_recipe.json': 'recipe_sha256',
             **{name+'.target.gz': role+'_target_sha256' for role, name, _ in TARGETS}}
    if verify:
        names.update({'faced_human.blend': 'face_sha256', 'face_report.json': 'report_sha256'})
    if type(options) is not dict or set(options) != set(names.values()) or any(
            type(v) is not str or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
            for v in options.values()):
        raise ValueError('Facial worker requires complete exact SHA-256 bindings')
    for role, _, sha in TARGETS:
        if options[role+'_target_sha256'] != sha:
            raise ValueError('Facial target is not the pinned bundled asset')
    for filename, key in names.items():
        path = root/filename
        if path.is_symlink() or not path.is_file() or digest(path) != options[key]:
            raise ValueError('Changed facial worker input: '+filename)
    return recipe(read_json(root/'face_recipe.json', options['recipe_sha256']), options['master_sha256'])
