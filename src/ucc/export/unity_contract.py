"""Closed private Unity request; actual import/runtime evidence remains required."""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from .godot_candidate_contract import EngineInputPermission, canonical_bytes

POLICY = 'UCC_PRIVATE_UNITY_CHARACTER_EXPORT_V1'
PROFILE = 'UCC_UNITY_BUILTIN_FORWARD_QUAD_NORMALS_V1'
ENGINE_VERSION = '6000.4.5f1'
MAX_REQUEST_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class UnityExportRequest:
    job_id: str
    project_id: str
    revision: int
    project_sha256: str
    unity_executable_sha256: str
    source_bindings: tuple[tuple[str, str], ...]
    permissions: tuple[EngineInputPermission, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.job_id) is not str or str(UUID(self.job_id)) != self.job_id:
                raise ValueError('Noncanonical job identity')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError('Unity export needs a canonical job UUID') from error
        if (type(self.project_id) is not str or not 1 <= len(self.project_id) <= 160
                or self.project_id.strip() != self.project_id or any(ord(c) < 32 for c in self.project_id)
                or type(self.revision) is not int or self.revision < 1
                or not is_sha256(self.project_sha256) or not is_sha256(self.unity_executable_sha256)):
            raise ValidationError('Unity export requires saved project and selected editor identities')
        if (type(self.source_bindings) is not tuple or not 3 <= len(self.source_bindings) <= 4
                or any(type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
                       or not is_sha256(row[1]) for row in self.source_bindings)):
            raise ValidationError('Unity export requires complete prepared-source identities')
        bound = dict(self.source_bindings)
        if (len(bound) != len(self.source_bindings)
                or not {'master', 'expression_library', 'body_material'} <= set(bound)
                or any(name not in {'master', 'expression_library', 'body_material'}
                       and not name.startswith('part:ucc-hand-v1-') for name in bound)
                or type(self.permissions) is not tuple or len(self.permissions) != len(bound)
                or any(type(p) is not EngineInputPermission for p in self.permissions)
                or {p.asset_id for p in self.permissions} != set(bound)):
            raise ValidationError('Every Unity source needs a distinct explicit per-use permission')
        for permission in self.permissions:
            if permission.source_sha256 != bound[permission.asset_id]:
                raise ValidationError('Unity permission names different source content')
            permission.require_engine('unity')
            if (not permission.policy.no_ai or permission.policy.ai_input_allowed
                    or permission.policy.redistribute_source_allowed):
                raise ValidationError('Private Unity export must retain NoAI and original-source privacy')
        object.__setattr__(self, 'source_bindings', tuple(sorted(self.source_bindings)))
        object.__setattr__(self, 'permissions', tuple(sorted(self.permissions, key=lambda p: p.asset_id)))
        if len(canonical_bytes(self.to_dict())) > MAX_REQUEST_BYTES:
            raise ValidationError('Unity request exceeds its bounded contract')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': POLICY, 'profile': PROFILE,
                'job_id': self.job_id, 'project_id': self.project_id, 'revision': self.revision,
                'project_sha256': self.project_sha256, 'unity_executable_sha256': self.unity_executable_sha256,
                'source_bindings': dict(self.source_bindings),
                'permissions': [permission.to_dict() for permission in self.permissions],
                'engine_version': ENGINE_VERSION, 'render_pipeline': 'BUILTIN_FORWARD',
                'graphics_api': 'DIRECT3D11', 'color_space': 'LINEAR',
                'animation_clips': False, 'engine_import_verified': False,
                'runtime_render_verified': False, 'visual_quality_approved': False,
                'distribution_license_review_complete': False, 'cloud_transmission_authorized': False}

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, raw: dict) -> 'UnityExportRequest':
        fields = {'schema_version', 'policy', 'profile', 'job_id', 'project_id', 'revision',
                  'project_sha256', 'unity_executable_sha256', 'source_bindings', 'permissions',
                  'engine_version', 'render_pipeline', 'graphics_api', 'color_space', 'animation_clips',
                  'engine_import_verified', 'runtime_render_verified', 'visual_quality_approved',
                  'distribution_license_review_complete', 'cloud_transmission_authorized'}
        if (type(raw) is not dict or set(raw) != fields
                or type(raw['source_bindings']) is not dict or type(raw['permissions']) is not list):
            raise ValidationError('Malformed closed Unity request')
        request = cls(raw['job_id'], raw['project_id'], raw['revision'], raw['project_sha256'],
                      raw['unity_executable_sha256'], tuple(raw['source_bindings'].items()),
                      tuple(EngineInputPermission.from_dict(p) for p in raw['permissions']))
        if canonical_bytes(raw) != canonical_bytes(request.to_dict()):
            raise ValidationError('Unity request changed capabilities or unapproved readiness flags')
        return request

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UnityExportRequest':
        import json
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        if type(data) is not bytes or not 1 <= len(data) <= MAX_REQUEST_BYTES:
            raise ValidationError('Unity request must be bounded UTF-8 JSON bytes')
        try:
            raw = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
            raise ValidationError('Malformed Unity request JSON') from error
        return cls.from_dict(raw)
