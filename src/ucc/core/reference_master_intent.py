"""Metadata eligibility only; real master admission belongs to the job layer."""
import re

from .models import CharacterProject
from ucc.animations.project_references import MAX_PROJECT_REFERENCES


def supports_referenced_master_intent(project: CharacterProject) -> bool:
    if (project.family != 'humanoid.v1' or project.base_provider != 'mpfb'
            or project.master_blend is None
            or not 0 < len(project.animations) <= MAX_PROJECT_REFERENCES or len(project.parts) > 1):
        return False
    if not project.parts:
        return True
    part = project.parts[0]
    return (part.slot == 'hand.L' and part.visible is True and part.status == 'proposed'
            and re.fullmatch(r'ucc-hand-v1-[a-f0-9]{64}-(shorter|longer)', part.part_asset_id) is not None)
