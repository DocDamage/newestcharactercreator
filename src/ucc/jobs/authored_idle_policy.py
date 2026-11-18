"""Explicit per-source idle-use records; hashes never establish legal rights."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ucc.core.errors import ProjectConflict, ValidationError
from ucc.core.target_action_format import checked_sha, checked_text, closed, read_document
from .target_action_context import protected

POLICY = 'UCC_IDLE_AUTHORING_SOURCE_POLICY_V1'
FLAGS = {'reviewed': True, 'authoring_and_derived_rig_allowed': True,
    'private_local_only': True, 'no_ai': True, 'ue_only': False,
    'ai_input_allowed': False, 'source_redistribution_allowed': False,
    'sprite_rights_granted': False, 'engine_rights_granted': False,
    'origin_declaration_is_authorship_proof': False}


@dataclass(frozen=True, slots=True)
class IdleSourcePolicyRecord:
    """Caller-selected reviewed declaration, separate from per-use confirmation.

    A matching digest only pins those bytes. The host independently corroborates
    the actual source and registered provenance, and requires the new per-use
    IdleAuthoringPermission; no engine/preview flag is promoted into that grant.
    """
    asset_id: str
    path: Path
    sha256: str

    def __post_init__(self):
        checked_text(self.asset_id, 200); checked_sha(self.sha256)
        if not isinstance(self.path, Path):
            raise ValidationError('Select an explicit local idle source-policy record')

    def read(self, source_sha256: str, provenance_sha256: str, budget) -> dict:
        budget.check(); path = protected(self.path)
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValidationError('Idle policy must be one canonical single-link file')
        with path.open('rb') as stream:
            payload = stream.read(256*1024+1)
        if len(payload) > 256*1024 or sha256(payload).hexdigest() != self.sha256:
            raise ProjectConflict('The selected idle source-policy record changed')
        value = closed(read_document(payload), {'schema_version', 'policy', 'asset_id',
            'source_sha256', 'provenance_sha256', 'review_note', *FLAGS})
        checked_text(value['review_note'], 2000)
        if (type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['policy'] != POLICY or value['asset_id'] != self.asset_id
                or value['source_sha256'] != source_sha256
                or value['provenance_sha256'] != provenance_sha256
                or any(value[key] is not expected for key, expected in FLAGS.items())):
            raise ProjectConflict('Idle policy differs from the exact current source, provenance or explicit use')
        return value


def admit_policies(request, sources, records, budget) -> tuple[dict, ...]:
    expected = tuple(row.asset_id for row in sources)
    if (type(records) is not tuple or len(records) != len(expected)
            or any(type(row) is not IdleSourcePolicyRecord for row in records)
            or tuple(row.asset_id for row in records) != expected):
        raise ValidationError('Select exactly one idle policy record per consumed source in canonical order')
    permissions = {row.asset_id: row for row in request.permissions}
    result = []
    for source, record in zip(sources, records):
        if permissions[source.asset_id].source_policy_sha256 != record.sha256:
            raise ProjectConflict('Idle per-use confirmation pins a different source-policy record')
        result.append(record.read(source.sha256, source.provenance_sha256, budget))
    return tuple(result)
