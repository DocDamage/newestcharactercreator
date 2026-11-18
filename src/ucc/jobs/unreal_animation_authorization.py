"""Private Unreal use for one exact registered target animation."""
from dataclasses import dataclass
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_text
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_runtime_files import read_metadata
from .target_action_context import Budget, protected


POLICY = 'UCC_PRIVATE_REGISTERED_UNREAL_ANIMATION_AUTHORIZATION_V1'


@dataclass(frozen=True, slots=True)
class UnrealAnimationAuthorization:
    selection: RegisteredInputSelection
    permissions: tuple[EngineInputPermission, ...]
    purpose: str

    def __post_init__(self) -> None:
        if type(self.selection) is not RegisteredInputSelection:
            raise ValidationError('Choose one exact saved Unreal animation')
        checked_text(self.purpose, 500)
        if (type(self.permissions) is not tuple or not 3 <= len(self.permissions) <= 4
                or any(type(row) is not EngineInputPermission for row in self.permissions)):
            raise ValidationError('Choose separate Unreal permissions for each consumed asset')
        roles = {row.asset_id for row in self.permissions}
        if (len(roles) != len(self.permissions) or not {'master', 'expression_library'} <= roles
                or sum(role.startswith('motion:') and len(role) > 7 for role in roles) != 1
                or sum(role.startswith('part:') and len(role) > 5 for role in roles) != len(roles) - 3):
            raise ValidationError('Unreal animation needs master, expression, motion and any used part permission')
        for permission in self.permissions:
            permission.require_engine('unreal')
            if permission.policy.ue_only:
                raise ValidationError('This Unreal export needs inputs licensed for the Blender preparation step')
            if (not permission.policy.no_ai or permission.policy.ai_input_allowed
                    or permission.policy.redistribute_source_allowed):
                raise ValidationError('Choose Unreal permissions scoped to private local rendering')


def load_unreal_animation_authorization(path: Path) -> UnrealAnimationAuthorization:
    raw, _, _ = read_metadata(protected(path), 256 * 1024, Budget(None, 5))
    if (set(raw) != {'schema_version', 'policy', 'engine', 'selection', 'permissions', 'purpose',
                    'private_local_execution_confirmed'}
            or type(raw['schema_version']) is not int or raw['schema_version'] != 1
            or raw['policy'] != POLICY or raw['engine'] != 'unreal'
            or type(raw['permissions']) is not list or not 3 <= len(raw['permissions']) <= 4
            or raw['private_local_execution_confirmed'] is not True):
        raise ValidationError('Choose private Unreal authority for this exact saved animation')
    return UnrealAnimationAuthorization(RegisteredInputSelection.from_dict(raw['selection']),
        tuple(EngineInputPermission.from_dict(row) for row in raw['permissions']), raw['purpose'])
