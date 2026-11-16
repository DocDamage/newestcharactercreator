"""Additive normal/material stream; original facial geometry contract stays V1."""
from .errors import ValidationError
from .expressions import TARGETS,is_sha256
from .skin_material import SkinMaterialSpec

POLICY='UCC_EXPRESSION_MATERIAL_NORMALS_V1'
STAGE='stage_mpfb_expression_normals'
VERIFY='verify_mpfb_expression_normals'
BASE_FIELDS={'master_sha256','clip_sha256','motion_sha256','motion_report_sha256','cache_sha256','cache_manifest_sha256'}|{t.role+'_'+t.family+'_sha256' for t in TARGETS}
NORMAL_FIELDS={'normals_sha256','normals_manifest_sha256'}


def validate_normal_job(operation: str,input_project: str,options: dict) -> None:
    fields=BASE_FIELDS|{'owned_material_spec'}|(NORMAL_FIELDS if operation==VERIFY else set())
    if (operation not in {STAGE,VERIFY} or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or any(not is_sha256(options[k]) for k in fields-{'owned_material_spec'})
            or any(options[t.role+'_'+t.family+'_sha256']!=t.sha256 for t in TARGETS)):
        raise ValidationError('Expression material normals require complete pinned geometry identities')
    SkinMaterialSpec.from_dict(options['owned_material_spec'])
