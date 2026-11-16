"""Immutable material proof binding, separate from render or export approval."""
from pathlib import Path
from threading import Event
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec,canonical_bytes
from ucc.core.expressions import is_sha256
from .expression_storage import safe_directory,_install_bytes,_read_json
from .master_preview import _digest
from .skin_material_preparation import checked_material_reports

POLICY='UCC_PUBLISHED_BODY_MATERIAL_V1'
FIELDS={'schema_version','policy','project_id','spec','source_master_sha256','material_master_sha256',
    'final_master_sha256','expression_library_sha256','hand_manifest_sha256','recipe_sha256',
    'stage_sha256','verification_sha256','glb_sha256','visual_quality_approved','engine_import_verified','source_rights_changed'}


def validate_binding(raw: object) -> dict:
    if (type(raw) is not dict or set(raw)!=FIELDS or type(raw['schema_version']) is not int or raw['schema_version']!=1
            or raw['policy']!=POLICY or type(raw['project_id']) is not str or not raw['project_id']
            or any(not is_sha256(raw[name]) for name in FIELDS if name.endswith('_sha256') and name!='hand_manifest_sha256')
            or (raw['hand_manifest_sha256'] is not None and not is_sha256(raw['hand_manifest_sha256']))
            or any(raw[name] is not False for name in ('visual_quality_approved','engine_import_verified','source_rights_changed'))):
        raise ValidationError('Invalid closed material publication binding')
    SkinMaterialSpec.from_dict(raw['spec'])
    return raw


def install_binding(store,record: dict,candidate: Path,cancel: Event | None=None) -> str:
    validate_binding(record)
    for name,key in [('material_recipe.json','recipe_sha256'),('material_stage.json','stage_sha256'),('material_verification.json','verification_sha256')]:
        source=candidate/name
        if source.is_symlink() or not source.is_file() or _digest(source,cancel)!=record[key]:
            raise ProjectStorageError('Material publication proof changed before installation')
        _install_bytes(safe_directory(store,'materials','proofs',create=True),record[key],source.read_bytes(),cancel)
    from hashlib import sha256
    data=canonical_bytes(record);identity=sha256(data).hexdigest()
    _install_bytes(safe_directory(store,'materials','manifests',create=True),identity,data,cancel)
    return identity


def material_binding_metadata(store,project,cancel: Event | None=None) -> dict | None:
    """Bound metadata for display only; not physical source or shader admission."""
    identity=dict(project.appearance).get(APPEARANCE_KEY)
    if identity is None:return None
    if not is_sha256(identity):raise ValidationError('Appearance requires an immutable material binding')
    raw=validate_binding(_read_json(safe_directory(store,'materials','manifests')/(identity+'.json'),identity,64*1024,cancel))
    from hashlib import sha256
    if (sha256(canonical_bytes(raw)).hexdigest()!=identity or raw['project_id']!=project.project_id
            or project.master_blend!='master/versions/'+raw['final_master_sha256']+'.blend'
            or project.expression is None or project.expression.library_sha256!=raw['expression_library_sha256']):
        raise ProjectStorageError('Appearance material binding differs from this saved character')
    return raw


def registered_material_binding(store,project,cancel: Event | None=None) -> dict | None:
    raw=material_binding_metadata(store,project,cancel)
    if raw is None:return None
    expected_parts=() if raw['hand_manifest_sha256'] is None else ('ucc-hand-v1-'+raw['hand_manifest_sha256']+'-',)
    if ((not expected_parts and project.parts) or (expected_parts and (len(project.parts)!=1
            or not project.parts[0].part_asset_id.startswith(expected_parts[0])))):
        raise ProjectStorageError('Material publication hand identity differs from the current character')
    proof=safe_directory(store,'materials','proofs')
    recipe=_read_json(proof/(raw['recipe_sha256']+'.json'),raw['recipe_sha256'],256*1024,cancel)
    from ucc.core.skin_material import validate_material_recipe
    recipe=validate_material_recipe(recipe)
    if (recipe['spec']!=raw['spec'] or recipe['project_snapshot']['project_id']!=project.project_id
            or recipe['source_bindings']['master']!=raw['source_master_sha256']
            or recipe['source_bindings']['expression_library']!=raw['expression_library_sha256']):
        raise ProjectStorageError('Material binding differs from its explicit source recipe')
    stage=_read_json(proof/(raw['stage_sha256']+'.json'),raw['stage_sha256'],4*1024*1024,cancel)
    fresh=_read_json(proof/(raw['verification_sha256']+'.json'),raw['verification_sha256'],4*1024*1024,cancel)
    checked_material_reports(stage,fresh,source_sha=raw['source_master_sha256'],recipe_sha=raw['recipe_sha256'],
        spec=SkinMaterialSpec.from_dict(raw['spec']),master_sha=raw['material_master_sha256'],glb_sha=raw['glb_sha256'],stage_sha=raw['stage_sha256'])
    for key in ('source_master_sha256','material_master_sha256','final_master_sha256'):
        path=safe_directory(store,'master','versions')/(raw[key]+'.blend')
        if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=raw[key]:
            raise ProjectStorageError('Material publication master ancestry changed')
    from .expression_verification import registered_expression_source
    registered_expression_source(store,project,cancel)
    return raw


def copy_binding(source,destination,project,cancel: Event | None=None) -> None:
    record=registered_material_binding(source,project,cancel)
    if record is None:return
    identity=dict(project.appearance)[APPEARANCE_KEY]
    for directory,identities in [('manifests',[identity]),('proofs',[record[k] for k in ('recipe_sha256','stage_sha256','verification_sha256')])]:
        for sha in identities:
            path=safe_directory(source,'materials',directory)/(sha+'.json')
            _install_bytes(safe_directory(destination,'materials',directory,create=True),sha,path.read_bytes(),cancel)
