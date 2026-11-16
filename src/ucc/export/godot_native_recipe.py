"""Closed source recipe for native runtime production; no readiness upgrade."""
from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject
from ucc.core.expression_library import canonical_digest
from .godot_candidate_contract import EngineInputPermission, canonical_bytes, _hash
from .godot_runtime_contract import CODE_FILES, CAPABILITY

POLICY = 'MPFB_NATIVE_RUNTIME_SOURCE_V1'
OPERATIONS = frozenset({'stage_native_godot_runtime', 'verify_native_godot_runtime','sample_native_godot_runtime'})
INPUTS = {'candidate.blend': 'master_sha256', 'source.fbx': 'source_sha256',
    'review_motion.blend': 'review_sha256', 'target_timeline.json': 'timeline_sha256',
    'source_snapshot.json': 'snapshot_sha256', 'native_mapping.json': 'mapping_sha256'}
REFERENCES = {'runtime_source.blend', 'native_stage.json', 'native_positions.bin', 'native_normals.bin', 'native_bones.bin', 'runtime_edges.u32','source_vertex_ids.u32'}


def build_native_recipe(project: CharacterProject, project_file_sha256: str,
        source_bindings: dict[str, str], evidence_bindings: dict[str, str],
        implementation: dict[str, str], permissions: tuple[EngineInputPermission, ...],
        motion_asset_id: str, capability: str) -> dict:
    if (not isinstance(project, CharacterProject) or not _hash(project_file_sha256)
            or project.family != 'humanoid.v1' or project.animations or project.expression is None
            or any(not part.visible for part in project.parts) or capability != CAPABILITY):
        raise ValidationError('Native runtime production needs the explicit supported prepared character/capability')
    if type(motion_asset_id) is not str or not motion_asset_id.startswith('motion:'):
        raise ValidationError('Native producer needs an explicit original motion identity')
    expected_sources = {'master', 'expression_library', motion_asset_id} | {'part:'+p.part_asset_id for p in project.parts}
    if (type(source_bindings) is not dict or set(source_bindings) != expected_sources
            or any(not _hash(value) for value in source_bindings.values())
            or project.master_blend != 'master/versions/'+source_bindings['master']+'.blend'
            or project.expression.library_sha256 != source_bindings['expression_library']):
        raise ValidationError('Native producer original sources differ from the exact saved character')
    if (type(evidence_bindings) is not dict or set(evidence_bindings) != {'native_review','native_timeline','source_snapshot','native_mapping'}
            or any(not _hash(value) for value in evidence_bindings.values())
            or type(implementation) is not dict or set(implementation) != CODE_FILES
            or any(not _hash(value) for value in implementation.values())):
        raise ValidationError('Native producer needs complete content-bound native evidence and private implementation')
    if (type(permissions) is not tuple or len(permissions) != len(expected_sources)
            or any(not isinstance(p, EngineInputPermission) for p in permissions)
            or {p.asset_id for p in permissions} != expected_sources):
        raise ValidationError('Native producer requires separate engine permission for every original source')
    for permission in permissions:
        if permission.source_sha256 != source_bindings[permission.asset_id]:
            raise ValidationError('Native producer permission is bound to different content')
        permission.require_godot()
        if permission.asset_id not in {'master',motion_asset_id} and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
            raise ValidationError('Native producer cannot remove registered library NoAI restrictions')
    result = {'schema_version':1,'policy':POLICY,'project_snapshot':project.to_dict(),
        'project_snapshot_sha256':canonical_digest(project.to_dict()),'project_file_sha256':project_file_sha256,
        'source_bindings':dict(source_bindings),'evidence_bindings':dict(evidence_bindings),
        'implementation':dict(implementation),'permissions':[p.to_dict() for p in permissions],
        'motion_asset_id':motion_asset_id,'requested_capability':capability,
        'timeline':{'first_frame':1,'last_frame':300,'fps':30},
        'source_role':'AUTHORITATIVE_MASTER_AND_REOPENED_NATIVE_REVIEW_V1',
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False,
        'source_redistribution_authorized':False,'cloud_transmission_authorized':False}
    if len(canonical_bytes(result))>256*1024:raise ValidationError('Native producer recipe is oversized')
    return result


def validate_native_recipe(raw: object) -> dict:
    if type(raw) is not dict:raise ValidationError('Native producer recipe must be an object')
    try:
        expected = build_native_recipe(CharacterProject.from_dict(raw['project_snapshot']),raw['project_file_sha256'],
            raw['source_bindings'],raw['evidence_bindings'],raw['implementation'],
            tuple(EngineInputPermission.from_dict(p) for p in raw['permissions']),raw['motion_asset_id'],raw['requested_capability'])
    except (KeyError, TypeError, AttributeError) as error:
        raise ValidationError('Malformed native producer recipe') from error
    if canonical_bytes(raw)!=canonical_bytes(expected):raise ValidationError('Native producer recipe changed its closed contract')
    return expected


def validate_native_job(operation: str, input_project: object, options: object) -> None:
    fields = set(INPUTS.values()) | {'native_recipe_sha256'}
    if operation in {'verify_native_godot_runtime','sample_native_godot_runtime'}:fields.add('native_stage_sha256')
    if operation=='sample_native_godot_runtime':
        fields|={'native_verification_sha256','runtime_request_sha256','production_receipt_sha256'}
    if (operation not in OPERATIONS or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or any(not _hash(value) for value in options.values())):
        raise ValidationError('Native runtime worker needs fixed files and exact closed source hashes')
