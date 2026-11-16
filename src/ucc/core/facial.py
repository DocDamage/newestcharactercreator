"""Closed facial intent and bundled-data recipe; no Blender, Qt or model runtime."""
from dataclasses import dataclass
from math import isfinite

from .errors import ValidationError

POLICY = 'BOUNDED_MPFB_NOSE_WIDTH_V1'
FACE_LIMITS = {'nose_width': (0.0, 1.0)}
FACE_DEFAULTS = {'nose_width': 0.5}
MPFB_VERSION = '2.0.18'
FACE_BASE_SHA256 = '8e761e6624b8f54536409135d1636da63b32486a90d4897f84e121d144f6fb4c'
FACE_RIG_SHA256 = '8b949de35c2dd70dbb5094e57a8586c3b9a9f650775a293212581a8f67be6797'


@dataclass(frozen=True, slots=True)
class BundledFaceTarget:
    role: str
    name: str
    filename: str
    sha256: str


NOSE_TARGETS = (
    BundledFaceTarget('narrow', 'nose-scale-horiz-decr', 'nose-scale-horiz-decr.target.gz',
                      '95d8dc4a3589bbb6105191abc6e3cae47c3c424ce189b5f0a611dc098806060d'),
    BundledFaceTarget('wide', 'nose-scale-horiz-incr', 'nose-scale-horiz-incr.target.gz',
                      'ba550cc15c894a4412bb368acc92bd6ad94bbb63d0135c561fe30230ef6344bd'),
)


def validate_face_parameters(raw: object, *, require_all: bool = False) -> dict[str, float]:
    """Empty intent is allowed in metadata; a worker recipe requires explicit intent."""
    if type(raw) is not dict or set(raw)-set(FACE_LIMITS) or (require_all and set(raw) != set(FACE_LIMITS)):
        raise ValidationError('Facial parameters support only explicit nose_width')
    result = {}
    for name, value in raw.items():
        low, high = FACE_LIMITS[name]
        if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
            raise ValidationError(f'{name} must be a finite normalized number between {low:g} and {high:g}')
        result[name] = float(value)
    return result


def nose_weights(value: object) -> tuple[float, float]:
    """0/0.5/1 selects bounded narrow/neutral/wide; target strengths never exceed 0.5."""
    checked = validate_face_parameters({'nose_width': value}, require_all=True)['nose_width']
    return max(0.0, 0.5-checked), max(0.0, checked-0.5)


def _sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def build_face_recipe(master_sha256: str, parameters: object) -> dict:
    if not _sha256(master_sha256):
        raise ValidationError('Facial recipe requires the exact original master SHA-256')
    intent = validate_face_parameters(parameters, require_all=True)
    weights = nose_weights(intent['nose_width'])
    return {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1', 'mpfb_version': MPFB_VERSION,
            'bindings': {'master_sha256': master_sha256,
                         'base_sha256': FACE_BASE_SHA256, 'rig_sha256': FACE_RIG_SHA256,
                         **{target.role+'_target_sha256': target.sha256 for target in NOSE_TARGETS}},
            'parameters': intent,
            'targets': [{'name': target.name, 'file': target.filename, 'weight': weight}
                        for target, weight in zip(NOSE_TARGETS, weights)]}


def validate_face_recipe(raw: object) -> dict:
    """Reject alternate assets, inferred values, partial bindings and arbitrary paths."""
    fields = {'schema_version', 'policy', 'family', 'mpfb_version', 'bindings', 'parameters', 'targets'}
    if (type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int
            or raw['schema_version'] != 1):
        raise ValidationError('Invalid facial recipe fields or version')
    bindings = raw['bindings']
    hashes = {'master_sha256', 'narrow_target_sha256', 'wide_target_sha256', 'base_sha256', 'rig_sha256'}
    if type(bindings) is not dict or set(bindings) != hashes or not all(_sha256(v) for v in bindings.values()):
        raise ValidationError('Facial recipe lacks complete master/asset bindings')
    targets = raw['targets']
    if type(targets) is not list or len(targets) != 2:
        raise ValidationError('Facial recipe requires the two declared bundled targets')
    for target in targets:
        if (type(target) is not dict or set(target) != {'name', 'file', 'weight'}
                or type(target['name']) is not str or type(target['file']) is not str
                or type(target['weight']) not in (int, float) or not 0 <= target['weight'] <= 0.5
                or not isfinite(target['weight'])):
            raise ValidationError('Invalid bounded facial target record')
    expected = build_face_recipe(bindings['master_sha256'], raw['parameters'])
    if raw != expected:
        raise ValidationError('Facial recipe differs from the pinned bundled assets or normalized intent')
    return expected
