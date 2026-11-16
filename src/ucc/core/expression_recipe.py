"""Closed neutral preparation recipe; no runtime or Blender imports."""
from .errors import ValidationError
from .expressions import POLICY, TARGETS, is_sha256
from .facial import FACE_BASE_SHA256, FACE_RIG_SHA256, MPFB_VERSION


def build_expression_recipe(master_sha256: str) -> dict:
    if not is_sha256(master_sha256):
        raise ValidationError('Expression preparation requires an exact original master hash')
    return {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1',
            'mpfb_version': MPFB_VERSION, 'neutral': True,
            'bindings': {'master_sha256': master_sha256, 'base_sha256': FACE_BASE_SHA256,
                         'rig_sha256': FACE_RIG_SHA256},
            'targets': [{'role': t.role, 'family': t.family, 'file': t.staged_name,
                         'key': t.key_name, 'sha256': t.sha256} for t in TARGETS]}


def validate_expression_recipe(raw: object) -> dict:
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'family',
            'mpfb_version', 'neutral', 'bindings', 'targets'}
            or type(raw['schema_version']) is not int or raw['neutral'] is not True):
        raise ValidationError('Invalid closed neutral expression recipe')
    bindings = raw['bindings']
    if (type(bindings) is not dict or set(bindings) != {'master_sha256', 'base_sha256', 'rig_sha256'}
            or not all(is_sha256(v) for v in bindings.values())):
        raise ValidationError('Expression preparation requires complete original and pinned base/rig bindings')
    expected = build_expression_recipe(bindings['master_sha256'])
    if raw != expected:
        raise ValidationError('Expression recipe differs from the twelve pinned neutral targets')
    return expected
