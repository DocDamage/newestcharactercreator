"""Closed, project-bound one-second facial preview recipe; no runtime imports."""
from .errors import ValidationError
from .expression_library import canonical_digest
from .expression_recipe import build_expression_recipe
from .expressions import is_sha256, validate_expression_parameters

CLIP_POLICY = 'BOUNDED_MPFB_EXPRESSION_CLIP_V1'
TIMELINE = {'fps': 24, 'first_frame': 1, 'last_frame': 25, 'keyframes': [1, 13, 25], 'interpolation': 'LINEAR'}


def _recipe(source: dict, parameters: dict) -> dict:
    prepared = build_expression_recipe(source['master_sha256'])
    return {'schema_version': 1, 'policy': CLIP_POLICY, 'mpfb_version': '2.0.18',
            'source': source, 'parameters': validate_expression_parameters(parameters),
            'timeline': {**TIMELINE, 'keyframes': list(TIMELINE['keyframes'])},
            'base_sha256': prepared['bindings']['base_sha256'], 'rig_sha256': prepared['bindings']['rig_sha256'],
            'targets': prepared['targets']}


def build_expression_clip(project, master_sha256: str) -> dict:
    if (not is_sha256(master_sha256) or project.expression is None or project.master_blend != 'master/versions/'+master_sha256+'.blend'
            or project.family != 'humanoid.v1' or project.base_provider != 'mpfb' or project.animations):
        raise ValidationError('Expression preview requires the exact prepared unanimated MPFB project/master')
    source = {'project_id': project.project_id, 'revision': project.revision,
              'project_snapshot_sha256': canonical_digest(project.to_dict()), 'master_sha256': master_sha256,
              'library_sha256': project.expression.library_sha256}
    return validate_expression_clip(_recipe(source, dict(project.expression.parameters)))


def validate_expression_clip(raw: object) -> dict:
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'mpfb_version', 'source',
            'parameters', 'timeline', 'base_sha256', 'rig_sha256', 'targets'}
            or type(raw['schema_version']) is not int):
        raise ValidationError('Invalid closed expression clip recipe')
    source = raw['source']
    if (type(source) is not dict or set(source) != {'project_id', 'revision', 'project_snapshot_sha256',
            'master_sha256', 'library_sha256'} or type(source['project_id']) is not str
            or not source['project_id'].strip() or len(source['project_id']) > 160
            or any(ord(c) < 32 for c in source['project_id']) or type(source['revision']) is not int
            or source['revision'] < 1 or not all(is_sha256(source[k]) for k in
                ('project_snapshot_sha256', 'master_sha256', 'library_sha256'))):
        raise ValidationError('Expression clip requires the complete saved project and master identity')
    expected = _recipe(dict(source), raw['parameters'])
    if canonical_digest(raw) != canonical_digest(expected):
        raise ValidationError('Expression clip differs from the pinned complete 25-frame contract')
    return expected
