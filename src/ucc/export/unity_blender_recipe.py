"""Closed Blender job recipe for source-bound private Unity export."""
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from .unity_contract import UnityExportRequest
from .godot_candidate_contract import canonical_bytes

POLICY='UCC_UNITY_BLENDER_SOURCE_V1'
STAGE='stage_mpfb_unity_source'
VERIFY='verify_mpfb_unity_source'
FILES={'character.fbx':512*1024*1024,'source_reference.json':64*1024*1024,
       'source_weights.json':8*1024*1024,'unity_source_stage.json':64*1024}


def recipe(request: UnityExportRequest,spec: SkinMaterialSpec) -> dict:
    if type(request) is not UnityExportRequest or type(spec) is not SkinMaterialSpec:
        raise ValidationError('Unity source recipe requires reviewed source and material contracts')
    return {'schema_version':1,'policy':POLICY,'export_request':request.to_dict(),'material_spec':spec.to_dict()}


def validate_recipe(raw: dict) -> tuple[UnityExportRequest,SkinMaterialSpec]:
    if type(raw) is not dict or set(raw)!={'schema_version','policy','export_request','material_spec'}:
        raise ValidationError('Malformed Unity source recipe')
    request=UnityExportRequest.from_dict(raw['export_request']);spec=SkinMaterialSpec.from_dict(raw['material_spec'])
    if canonical_bytes(raw)!=canonical_bytes(recipe(request,spec)):
        raise ValidationError('Unity source recipe changed its version, capabilities or material')
    return request,spec


def validate_job(operation: str,input_project: str,options: dict) -> None:
    fields={'master_sha256','recipe_sha256'}
    if operation==VERIFY:fields|={name.replace('.','_')+'_sha256' for name in FILES}
    if (operation not in {STAGE,VERIFY} or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or any(not is_sha256(value) for value in options.values())):
        raise ValidationError('Unity source job requires fixed staged filenames and complete SHA bindings')
