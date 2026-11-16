"""Bounded original-source runtime diagnostics; no engine or model imports."""
from ucc.core.errors import ValidationError
from ucc.core.expressions import validate_expression_parameters,is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from .unity_contract import UnityExportRequest
from .godot_candidate_contract import canonical_bytes

POLICY='UCC_UNITY_RUNTIME_SOURCE_V1'
STAGE='stage_mpfb_unity_runtime_source'
VERIFY='verify_mpfb_unity_runtime_source'
VERTICES=13380
CASES=178
VECTOR_BYTES=VERTICES*3*4
BINARY_BYTES=CASES*VECTOR_BYTES*2
FILES={'unity_runtime_source.bin':BINARY_BYTES,'unity_runtime_source.json':2*1024*1024}


def recipe(request: UnityExportRequest,spec: SkinMaterialSpec,parameters: dict,bind_sha256: str) -> dict:
    if type(request) is not UnityExportRequest or type(spec) is not SkinMaterialSpec or not is_sha256(bind_sha256):
        raise ValidationError('Unity runtime source requires reviewed source, material and bind reference identities')
    return {'schema_version':1,'policy':POLICY,'export_request':request.to_dict(),'material_spec':spec.to_dict(),
        'expression_parameters':validate_expression_parameters(parameters),'bind_reference_sha256':bind_sha256}


def validate_recipe(raw: object) -> tuple[UnityExportRequest,SkinMaterialSpec,dict]:
    if type(raw) is not dict or set(raw)!={'schema_version','policy','export_request','material_spec','expression_parameters','bind_reference_sha256'}:
        raise ValidationError('Malformed Unity runtime source recipe')
    request=UnityExportRequest.from_dict(raw['export_request']);spec=SkinMaterialSpec.from_dict(raw['material_spec'])
    expected=recipe(request,spec,raw['expression_parameters'],raw['bind_reference_sha256'])
    if canonical_bytes(raw)!=canonical_bytes(expected):raise ValidationError('Unity runtime source recipe changed its closed policy or bindings')
    return request,spec,expected['expression_parameters']


def validate_job(operation: str,input_project: str,options: dict) -> None:
    fields={'master_sha256','recipe_sha256','bind_reference_sha256'}
    if operation==VERIFY:fields|={n.replace('.','_')+'_sha256' for n in FILES}
    if (operation not in {STAGE,VERIFY} or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or any(not is_sha256(v) for v in options.values())):
        raise ValidationError('Unity runtime source job requires fixed inputs and complete SHA bindings')
