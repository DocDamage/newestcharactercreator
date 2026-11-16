"""Closed private static Unreal request; readiness belongs to actual evidence."""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from .godot_candidate_contract import EngineInputPermission, canonical_bytes

POLICY = 'UCC_PRIVATE_UNREAL_CHARACTER_EXPORT_V1'
PROFILE = 'UCC_UNREAL59_LEGACY_XFORWARD_ZUP_CM_V1'
ENGINE_VERSION = '5.9.0-60351404+++UE5+Release-5.9'
MAX_REQUEST_BYTES = 256 * 1024
READINESS_FLAGS = frozenset({'engine_import_verified', 'source_parity_verified',
    'shader_compilation_verified', 'runtime_gpu_verified', 'pie_verified',
    'player_build_verified', 'visual_quality_approved',
    'distribution_license_review_complete', 'cloud_transmission_authorized',
    'export_published'})


@dataclass(frozen=True, slots=True)
class UnrealExportRequest:
    job_id: str
    project_id: str
    revision: int
    project_sha256: str
    unreal_executable_sha256: str
    unreal_build_version_sha256: str
    toolchain_sha256: str
    source_bindings: tuple[tuple[str, str], ...]
    permissions: tuple[EngineInputPermission, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.job_id) is not str or str(UUID(self.job_id)) != self.job_id:
                raise ValueError('Noncanonical job identity')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError('Unreal export needs a canonical job UUID') from error
        if (type(self.project_id) is not str or not 1 <= len(self.project_id) <= 160
                or self.project_id.strip() != self.project_id
                or any(ord(c) < 32 for c in self.project_id)
                or type(self.revision) is not int or self.revision < 1
                or any(not is_sha256(value) for value in (self.project_sha256,
                    self.unreal_executable_sha256, self.unreal_build_version_sha256,
                    self.toolchain_sha256))):
            raise ValidationError('Unreal export needs saved project, editor and toolchain identities')
        if (type(self.source_bindings) is not tuple or not 3 <= len(self.source_bindings) <= 4
                or any(type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
                       or not is_sha256(row[1]) for row in self.source_bindings)):
            raise ValidationError('Unreal export requires complete prepared-source identities')
        bound = dict(self.source_bindings)
        if (len(bound) != len(self.source_bindings)
                or not {'master', 'expression_library', 'body_material'} <= set(bound)
                or any(name not in {'master', 'expression_library', 'body_material'}
                       and not name.startswith('part:ucc-hand-v1-') for name in bound)
                or type(self.permissions) is not tuple or len(self.permissions) != len(bound)
                or any(type(p) is not EngineInputPermission for p in self.permissions)
                or {p.asset_id for p in self.permissions} != set(bound)):
            raise ValidationError('Every Unreal source needs a distinct explicit per-use permission')
        for permission in self.permissions:
            if permission.source_sha256 != bound[permission.asset_id]:
                raise ValidationError('Unreal permission names different source content')
            permission.require_engine('unreal')
            if (not permission.policy.no_ai or permission.policy.ai_input_allowed
                    or permission.policy.redistribute_source_allowed):
                raise ValidationError('Private Unreal export retains NoAI and original-source privacy')
        object.__setattr__(self, 'source_bindings', tuple(sorted(self.source_bindings)))
        object.__setattr__(self, 'permissions', tuple(sorted(self.permissions, key=lambda p: p.asset_id)))
        if len(canonical_bytes(self.to_dict())) > MAX_REQUEST_BYTES:
            raise ValidationError('Unreal request exceeds its bounded contract')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': POLICY, 'profile': PROFILE,
            'job_id': self.job_id, 'project_id': self.project_id, 'revision': self.revision,
            'project_sha256': self.project_sha256,
            'unreal_executable_sha256': self.unreal_executable_sha256,
            'unreal_build_version_sha256': self.unreal_build_version_sha256,
            'toolchain_sha256': self.toolchain_sha256,
            'source_bindings': dict(self.source_bindings),
            'permissions': [permission.to_dict() for permission in self.permissions],
            'engine_version': ENGINE_VERSION, 'platform': 'WINDOWS_X64',
            'native_lod': 0, 'skin_weight_bits': 16, 'animation_clips': False,
            **{name: False for name in READINESS_FLAGS}}

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, raw: dict) -> 'UnrealExportRequest':
        fields = {'schema_version', 'policy', 'profile', 'job_id', 'project_id', 'revision',
            'project_sha256', 'unreal_executable_sha256', 'unreal_build_version_sha256',
            'toolchain_sha256', 'source_bindings', 'permissions', 'engine_version',
            'platform', 'native_lod', 'skin_weight_bits', 'animation_clips'} | READINESS_FLAGS
        if (type(raw) is not dict or set(raw) != fields
                or type(raw['source_bindings']) is not dict or type(raw['permissions']) is not list):
            raise ValidationError('Malformed closed Unreal request')
        request = cls(raw['job_id'], raw['project_id'], raw['revision'], raw['project_sha256'],
            raw['unreal_executable_sha256'], raw['unreal_build_version_sha256'],
            raw['toolchain_sha256'], tuple(raw['source_bindings'].items()),
            tuple(EngineInputPermission.from_dict(p) for p in raw['permissions']))
        if canonical_bytes(raw) != canonical_bytes(request.to_dict()):
            raise ValidationError('Unreal request changed its profile or unapproved readiness flags')
        return request

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UnrealExportRequest':
        import json
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        if type(data) is not bytes or not 1 <= len(data) <= MAX_REQUEST_BYTES:
            raise ValidationError('Unreal request must be bounded UTF-8 JSON bytes')
        try:
            raw = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
            raise ValidationError('Malformed Unreal request JSON') from error
        return cls.from_dict(raw)
