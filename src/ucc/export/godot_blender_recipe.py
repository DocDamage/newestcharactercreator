"""Closed production Blender-candidate source contract, separate from export approval."""
from ucc.core.errors import ValidationError
from ucc.core.expression_clip import validate_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import is_sha256, TARGETS
from .godot_candidate_contract import EngineInputPermission, canonical_bytes

POLICY = 'MPFB_GODOT_CANDIDATE_SOURCE_V1'
OPERATIONS = frozenset({'stage_mpfb_godot_candidate', 'verify_mpfb_godot_candidate'})
OUTPUTS = {'character.glb': 'candidate_sha256', 'source_review.blend': 'review_scene_sha256',
           'blender_stage.json': 'stage_report_sha256', 'source_positions.bin': 'positions_sha256',
           'bind_positions.bin': 'bind_positions_sha256', 'source_bones.bin': 'bones_sha256',
           'source_action.json': 'action_report_sha256'}


def build_recipe(project, project_file_sha256: str, master_sha256: str,
                 motion_asset_id: str, source_bindings: dict[str, str],
                 permissions: tuple[EngineInputPermission, ...], clip: dict) -> dict:
    if (not is_sha256(project_file_sha256) or not is_sha256(master_sha256)
            or project.master_blend != 'master/versions/'+master_sha256+'.blend'
            or project.animations or project.expression is None or any(not part.visible for part in project.parts)):
        raise ValidationError('Godot producer requires an exact prepared saved master without source-only animation references')
    checked = validate_expression_clip(clip)
    if checked['source'] != {'project_id': project.project_id, 'revision': project.revision,
            'project_snapshot_sha256': canonical_digest(project.to_dict()), 'master_sha256': master_sha256,
            'library_sha256': project.expression.library_sha256}:
        raise ValidationError('Godot producer facial controls belong to another saved character')
    if (type(motion_asset_id) is not str or not motion_asset_id.startswith('motion:')
            or type(source_bindings) is not dict or not 3 <= len(source_bindings) <= 128
            or source_bindings.get('master') != master_sha256
            or source_bindings.get('expression_library') != project.expression.library_sha256
            or motion_asset_id not in source_bindings
            or any(type(name) is not str or not name or len(name) > 160 or not is_sha256(value)
                   for name, value in source_bindings.items())):
        raise ValidationError('Godot producer lacks exact complete source and selected motion identities')
    required = {'master', 'expression_library', motion_asset_id} | {'part:'+p.part_asset_id for p in project.parts}
    if set(source_bindings) != required or type(permissions) is not tuple:
        raise ValidationError('Godot producer source coverage differs from the registered character')
    if (any(not isinstance(item, EngineInputPermission) for item in permissions)
            or len(permissions) != len(required) or {item.asset_id for item in permissions} != required):
        raise ValidationError('Every producer input needs its own explicit engine permission')
    for item in permissions:
        if item.source_sha256 != source_bindings[item.asset_id]:
            raise ValidationError('Producer engine policy is for another input version')
        item.require_godot()
        if item.asset_id not in {'master', motion_asset_id} and (not item.policy.no_ai or item.policy.ai_input_allowed):
            raise ValidationError('Producer engine policy cannot remove library NoAI restrictions')
    result = {'schema_version': 1, 'policy': POLICY,
            'project': {'project_id': project.project_id, 'revision': project.revision,
                        'project_file_sha256': project_file_sha256,
                        'project_snapshot_sha256': canonical_digest(project.to_dict())},
            'source_bindings': dict(source_bindings), 'motion_asset_id': motion_asset_id,
            'permissions': [item.to_dict() for item in permissions],
            'expression_clip_sha256': canonical_digest(checked),
            'timeline': {'fps': 24, 'first_frame': 1, 'last_frame': 25},
            'source_role': 'TARGET_ACTION_ONLY_AUTHORITATIVE_MASTER_GEOMETRY_V1',
            'engine_import_verified': False, 'visual_quality_approved': False,
            'source_redistribution_authorized': False, 'cloud_transmission_authorized': False}
    if len(canonical_bytes(result)) > 256*1024:
        raise ValidationError('Godot Blender source recipe exceeds its bounded JSON contract')
    return result


def validate_recipe(raw: object, project, clip: dict) -> dict:
    if type(raw) is not dict or type(raw.get('permissions')) is not list:
        raise ValidationError('Invalid Godot Blender source recipe')
    try:
        expected = build_recipe(project, raw['project']['project_file_sha256'],
            raw['source_bindings']['master'], raw['motion_asset_id'], raw['source_bindings'],
            tuple(EngineInputPermission.from_dict(item) for item in raw['permissions']), clip)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValidationError('Incomplete Godot Blender source recipe') from error
    if canonical_bytes(raw) != canonical_bytes(expected):
        raise ValidationError('Godot Blender source recipe changed its closed policy or bindings')
    return expected


def validate_job(operation: str, input_project: object, options: object) -> None:
    fields = {'master_sha256', 'target_motion_sha256', 'export_recipe_sha256', 'clip_sha256'}
    fields |= {target.role+'_'+target.family+'_sha256' for target in TARGETS}
    if operation == 'verify_mpfb_godot_candidate':
        fields |= set(OUTPUTS.values())
    if (operation not in OPERATIONS or input_project != 'candidate.blend' or type(options) is not dict
            or set(options) != fields or any(not is_sha256(value) for value in options.values())
            or any(options[target.role+'_'+target.family+'_sha256'] != target.sha256 for target in TARGETS)):
        raise ValidationError('Godot Blender job requires fixed filenames and every exact source/output hash')
