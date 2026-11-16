"""Metadata eligibility/history only; real material admission stays in jobs."""
from dataclasses import replace
import re
from .models import CharacterProject
from .skin_material import APPEARANCE_KEY
from .expressions import is_sha256,validate_expression_part_rebind
from .errors import ValidationError


def supports_skin_material_input(project: CharacterProject) -> bool:
    if (project.family!='humanoid.v1' or project.base_provider!='mpfb' or project.master_blend is None
            or project.expression is None or project.animations or len(project.parts)>1):return False
    identity=dict(project.appearance).get(APPEARANCE_KEY)
    if identity is not None and not is_sha256(identity):return False
    return not project.parts or (project.parts[0].slot=='hand.L' and project.parts[0].visible is True
        and project.parts[0].status=='proposed'
        and re.fullmatch(r'ucc-hand-v1-[a-f0-9]{64}-(shorter|longer)',project.parts[0].part_asset_id) is not None)


def supports_material_master_intent(project: CharacterProject) -> bool:
    return supports_skin_material_input(project) and is_sha256(dict(project.appearance).get(APPEARANCE_KEY))


def validate_material_master_adoption(before: CharacterProject,saved: CharacterProject,*,initial_assignment: bool=False) -> None:
    source_ok=supports_material_master_intent(before) or (initial_assignment is True and supports_skin_material_input(before)
        and APPEARANCE_KEY not in dict(before.appearance))
    if not source_ok or not supports_material_master_intent(saved):
        raise ValidationError('Material-aware adoption requires the supported prepared character and hand')
    if (saved.revision!=before.revision+1 or saved.master_blend==before.master_blend
            or saved.geometry_state!='generated_unverified' or saved.rig_profile is not None
            or dict(saved.appearance)[APPEARANCE_KEY]==dict(before.appearance).get(APPEARANCE_KEY)):
        raise ValidationError('Material-aware master and appearance must extend the current revision together')
    validate_expression_part_rebind(before.parts,saved.parts)
    expected_appearance=dict(before.appearance);expected_appearance[APPEARANCE_KEY]=dict(saved.appearance)[APPEARANCE_KEY]
    expected=replace(before,master_blend=saved.master_blend,parts=saved.parts,appearance=tuple(sorted(expected_appearance.items())),
        revision=saved.revision,geometry_state='generated_unverified',rig_profile=None)
    if expected!=saved:raise ValidationError('Material-aware master changed unrelated character intent')
