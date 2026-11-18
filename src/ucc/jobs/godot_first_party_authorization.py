"""Read the exact local declaration shared by Godot CLI and desktop export."""
from dataclasses import dataclass
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_text
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_runtime_admission import permission_bytes
from .godot_registered_runtime_files import read_metadata
from .target_action_context import Budget, protected


POLICY = 'UCC_PRIVATE_FIRST_PARTY_GODOT_AUTHORIZATION_V1'


@dataclass(frozen=True, slots=True)
class FirstPartyGodotAuthorization:
    selection: RegisteredInputSelection
    permissions: tuple[EngineInputPermission, ...]
    purpose: str
    sha256: str


def load_first_party_godot_authorization(path: Path) -> FirstPartyGodotAuthorization:
    raw, _, digest = read_metadata(protected(path), 256 * 1024, Budget(None, 5))
    if (set(raw) != {'schema_version', 'policy', 'selection', 'permissions', 'purpose',
                    'private_local_execution_confirmed'}
            or type(raw['schema_version']) is not int or raw['schema_version'] != 1
            or raw['policy'] != POLICY
            or type(raw['permissions']) is not list or not 3 <= len(raw['permissions']) <= 4
            or raw['private_local_execution_confirmed'] is not True):
        raise ValidationError('Select the current private Godot authorization for this exact animation')
    selection = RegisteredInputSelection.from_dict(raw['selection'])
    permissions = tuple(EngineInputPermission.from_dict(row) for row in raw['permissions'])
    permission_bytes(permissions)
    return FirstPartyGodotAuthorization(selection, permissions, checked_text(raw['purpose'], 500), digest)
