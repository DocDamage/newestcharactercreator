"""Closed private Godot-candidate job contract; no readiness or rights upgrade.

Each input permission is supplied explicitly for this use and exact content.
Existing local-preview catalogs and source-only bindings are never rewritten.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from ucc.core.errors import ValidationError
from ucc.library.provenance import AssetPolicyError, LicensePolicy

POLICY = 'UCC_PRIVATE_GODOT_CANDIDATE_JOB_V1'
FILES = frozenset({'character.glb', 'skin_plan.json', 'blender_stage.json',
                   'source_positions.bin', 'bind_source_indices.json',
                   'bind_positions.bin', 'blender_verification.json'})
MAX_REQUEST_BYTES = 256 * 1024
_HASH = re.compile(r'[0-9a-f]{64}\Z')


def _hash(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _text(value: object, limit: int = 160) -> bool:
    return (type(value) is str and 0 < len(value) <= limit and value.strip() == value
            and all(ord(char) >= 32 for char in value))


def _closed(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValidationError('Godot candidate has missing or unknown contract fields')
    return value


def canonical_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValidationError('Godot candidate requires finite bounded JSON') from error


@dataclass(frozen=True, slots=True)
class EngineInputPermission:
    asset_id: str
    source_sha256: str
    policy: LicensePolicy
    source_only: bool = True

    def __post_init__(self) -> None:
        if not _text(self.asset_id) or not _hash(self.source_sha256) or not isinstance(self.policy, LicensePolicy):
            raise ValidationError('Engine permission requires an exact named input and reviewed policy')
        if type(self.source_only) is not bool:
            raise ValidationError('Source-only permission flag must be Boolean')

    def require_godot(self) -> None:
        self.require_engine('godot')

    def require_engine(self, engine: str) -> None:
        """Check this exact per-use input for the named engine, without promotion."""
        if type(engine) is not str or engine not in {'godot', 'unity', 'unreal'}:
            raise AssetPolicyError('Engine permission requires a recognized explicit target')
        if self.source_only:
            raise AssetPolicyError('Source-only input cannot become an engine action or asset: '+self.asset_id)
        allowed, reason = self.policy.allow('engine_export', engine)
        if not allowed:
            raise AssetPolicyError(engine.title()+' input '+self.asset_id+': '+reason)

    def to_dict(self) -> dict[str, Any]:
        return {'asset_id': self.asset_id, 'source_sha256': self.source_sha256,
                'source_only': self.source_only, 'policy': self.policy.to_dict()}

    @classmethod
    def from_dict(cls, raw: object) -> 'EngineInputPermission':
        raw = _closed(raw, {'asset_id', 'source_sha256', 'source_only', 'policy'})
        if type(raw['policy']) is not dict or set(raw['policy']) != set(LicensePolicy.__dataclass_fields__):
            raise ValidationError('Engine job must retain the complete input license policy')
        return cls(raw['asset_id'], raw['source_sha256'], LicensePolicy.from_dict(raw['policy']), raw['source_only'])


@dataclass(frozen=True, slots=True)
class GodotCandidateRequest:
    job_id: str
    project_id: str
    revision: int
    project_file_sha256: str
    master_sha256: str
    files: tuple[tuple[str, str], ...]
    permissions: tuple[EngineInputPermission, ...]
    source_bindings: tuple[tuple[str, str], ...]
    fps: int = 24
    frame_count: int = 25

    def __post_init__(self) -> None:
        try:
            if type(self.job_id) is not str or str(UUID(self.job_id)) != self.job_id:
                raise ValueError('Noncanonical job identity')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError('Godot job requires a canonical UUID') from error
        if (not _text(self.project_id) or type(self.revision) is not int or self.revision < 1
                or not _hash(self.project_file_sha256) or not _hash(self.master_sha256)):
            raise ValidationError('Godot job requires exact saved project, revision and master identities')
        if type(self.fps) is not int or self.fps != 24 or type(self.frame_count) is not int or self.frame_count != 25:
            raise ValidationError('This first verified Godot profile requires complete 25-frame/24fps input')
        for rows, label in ((self.files, 'files'), (self.source_bindings, 'source bindings')):
            if (type(rows) is not tuple or not 1 <= len(rows) <= 128
                    or any(type(row) is not tuple or len(row) != 2 or not _text(row[0]) or not _hash(row[1]) for row in rows)
                    or len(dict(rows)) != len(rows)):
                raise ValidationError('Godot job has invalid or duplicate '+label)
        if set(dict(self.files)) != FILES:
            raise ValidationError('Godot job requires its complete fixed candidate files')
        if (type(self.permissions) is not tuple or not 1 <= len(self.permissions) <= 128
                or any(not isinstance(item, EngineInputPermission) for item in self.permissions)
                or len({item.asset_id for item in self.permissions}) != len(self.permissions)):
            raise ValidationError('Godot job has invalid or duplicate input permissions')
        bound = dict(self.source_bindings)
        if bound.get('master') != self.master_sha256 or {item.asset_id for item in self.permissions} != set(bound):
            raise ValidationError('Every source input, including the master, needs a distinct bound engine permission')
        for item in self.permissions:
            if item.source_sha256 != bound[item.asset_id]:
                raise ValidationError('Engine permission is for different source content: '+item.asset_id)
            item.require_godot()
        if len(canonical_bytes(self.to_dict())) > MAX_REQUEST_BYTES:
            raise ValidationError('Godot candidate request exceeds its bounded contract')

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': 1, 'policy': POLICY, 'job_id': self.job_id,
                'project_id': self.project_id, 'revision': self.revision,
                'project_file_sha256': self.project_file_sha256, 'master_sha256': self.master_sha256,
                'files': dict(self.files), 'source_bindings': dict(self.source_bindings),
                'permissions': [item.to_dict() for item in self.permissions],
                'fps': self.fps, 'frame_count': self.frame_count,
                'import_profile': {'animation_fps': 24, 'optimizer_enabled': False,
                                   'compression_enabled': False, 'animation_player_import_id': 'PATH:AnimationPlayer'},
                'engine_import_verified': False, 'visual_quality_approved': False,
                'source_redistribution_authorized': False, 'cloud_transmission_authorized': False}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, raw: object) -> 'GodotCandidateRequest':
        required = {'schema_version', 'policy', 'job_id', 'project_id', 'revision',
                    'project_file_sha256', 'master_sha256', 'files', 'source_bindings',
                    'permissions', 'fps', 'frame_count', 'import_profile', 'engine_import_verified',
                    'visual_quality_approved', 'source_redistribution_authorized', 'cloud_transmission_authorized'}
        raw = _closed(raw, required)
        if (type(raw['schema_version']) is not int or raw['schema_version'] != 1 or raw['policy'] != POLICY
                or type(raw['files']) is not dict or type(raw['source_bindings']) is not dict
                or type(raw['permissions']) is not list):
            raise ValidationError('Unsupported or malformed Godot candidate contract')
        request = cls(raw['job_id'], raw['project_id'], raw['revision'], raw['project_file_sha256'],
                      raw['master_sha256'], tuple(raw['files'].items()),
                      tuple(EngineInputPermission.from_dict(item) for item in raw['permissions']),
                      tuple(raw['source_bindings'].items()), raw['fps'], raw['frame_count'])
        if canonical_bytes(raw) != canonical_bytes(request.to_dict()):
            raise ValidationError('Godot candidate changed required import settings or unapproved readiness flags')
        return request

    @classmethod
    def from_bytes(cls, data: bytes) -> 'GodotCandidateRequest':
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        if type(data) is not bytes or not 2 <= len(data) <= MAX_REQUEST_BYTES:
            raise ValidationError('Godot request is missing or oversized')
        try:
            raw = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValidationError('Malformed Godot candidate JSON') from error
        return cls.from_dict(raw)
