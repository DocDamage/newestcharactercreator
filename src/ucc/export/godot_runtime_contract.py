"""Private native-runtime input contract; retention never certifies execution.

Runtime implementation files are caller-selected, content-bound private inputs.
This module neither distributes those files nor approves their code/license.
"""
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

from ucc.core.errors import ValidationError
from .godot_candidate_contract import EngineInputPermission, canonical_bytes, _hash, _text, _closed

POLICY = 'UCC_PRIVATE_NATIVE_RUNTIME_INPUTS_V1'
PROFILE = 'MPFB_BOUND_CS_SMOOTH_IDENTITY_V1'
CAPABILITY = 'GODOT_4_7_MOBILE_VULKAN_COMPUTE'
CODE_FILES = frozenset({'runtime_kernel.gd', 'ucc_skin_adapter.gd', 'smooth.glsl',
                       'corners.glsl', 'combine.glsl', 'normal_faces.glsl', 'normal_vertices.glsl'})
DATA_FILES = frozenset({'neighbor_ranges.u32', 'neighbors.u32', 'corners.u32',
    'offsets_vec4.f32', 'corner_ranges.u32', 'corner_indices.u32', 'face_ranges.u32',
    'face_vertices.u32', 'face_ids.u32'})
FILES = CODE_FILES | DATA_FILES | {'character.glb', 'skin_plan.json', 'bind_positions.bin',
                                  'bind_source_indices.json', 'source_profile.json'}
MAX_BYTES = 256*1024
EVIDENCE = frozenset({'native_review', 'native_timeline'})


def pairs(rows: object, label: str) -> dict[str, str]:
    if (type(rows) is not tuple or not 1 <= len(rows) <= 128
            or any(type(row) is not tuple or len(row) != 2 or not _text(row[0]) or not _hash(row[1]) for row in rows)
            or len(dict(rows)) != len(rows)):
        raise ValidationError('Invalid or duplicate runtime '+label)
    return dict(rows)


@dataclass(frozen=True, slots=True)
class NativeRuntimeRequest:
    job_id: str
    project_id: str
    revision: int
    project_file_sha256: str
    master_sha256: str
    files: tuple[tuple[str, str], ...]
    source_bindings: tuple[tuple[str, str], ...]
    evidence_bindings: tuple[tuple[str, str], ...]
    permissions: tuple[EngineInputPermission, ...]
    requested_capability: str

    def __post_init__(self) -> None:
        try:
            if type(self.job_id) is not str or str(UUID(self.job_id)) != self.job_id:
                raise ValueError('Noncanonical identity')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError('Runtime request needs a canonical UUID') from error
        if (not _text(self.project_id) or type(self.revision) is not int or self.revision < 0
                or not _hash(self.project_file_sha256) or not _hash(self.master_sha256)
                or self.requested_capability != CAPABILITY):
            raise ValidationError('Unsupported runtime identity or explicitly selected renderer capability')
        files = pairs(self.files, 'files'); bound = pairs(self.source_bindings, 'source bindings')
        evidence = pairs(self.evidence_bindings, 'evidence bindings')
        if set(files) != FILES or set(evidence) != EVIDENCE:
            raise ValidationError('Runtime request requires its exact complete file/evidence set')
        if (bound.get('master') != self.master_sha256
                or len([name for name in bound if name.startswith('motion:')]) != 1):
            raise ValidationError('Runtime request requires the saved master and one explicit source motion')
        if (type(self.permissions) is not tuple or len(self.permissions) != len(bound)
                or any(not isinstance(item, EngineInputPermission) for item in self.permissions)
                or {item.asset_id for item in self.permissions} != set(bound)):
            raise ValidationError('Every original runtime source needs a distinct explicit engine permission')
        for item in self.permissions:
            if item.source_sha256 != bound[item.asset_id]:
                raise ValidationError('Runtime permission names different source content')
            item.require_godot()
        if len(canonical_bytes(self.to_dict())) > MAX_BYTES:
            raise ValidationError('Runtime request exceeds its bounded contract')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': POLICY, 'profile': PROFILE,
            'job_id': self.job_id, 'project_id': self.project_id, 'revision': self.revision,
            'project_file_sha256': self.project_file_sha256, 'master_sha256': self.master_sha256,
            'files': dict(self.files), 'source_bindings': dict(self.source_bindings),
            'evidence_bindings': dict(self.evidence_bindings),
            'permissions': [item.to_dict() for item in self.permissions],
            'requested_capability': self.requested_capability,
            'implementation_sha256': hashlib.sha256(canonical_bytes({name: dict(self.files)[name] for name in sorted(CODE_FILES)})).hexdigest(),
            'import_profile': {'fps': 30, 'frames': 300, 'optimizer_enabled': False, 'compression_enabled': False},
            'runtime_execution_verified': False, 'native_lineage_verified': False,
            'engine_import_verified': False, 'visual_quality_approved': False,
            'distribution_license_review_complete': False,
            'source_redistribution_authorized': False, 'cloud_transmission_authorized': False}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'NativeRuntimeRequest':
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        if type(data) is not bytes or not 2 <= len(data) <= MAX_BYTES:
            raise ValidationError('Missing or oversized native runtime request')
        try:
            raw = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValidationError('Malformed native runtime JSON') from error
        keys = {'schema_version', 'policy', 'profile', 'job_id', 'project_id', 'revision',
            'project_file_sha256', 'master_sha256', 'files', 'source_bindings', 'evidence_bindings',
            'permissions', 'requested_capability', 'implementation_sha256', 'import_profile',
            'runtime_execution_verified', 'native_lineage_verified', 'engine_import_verified',
            'visual_quality_approved', 'distribution_license_review_complete',
            'source_redistribution_authorized', 'cloud_transmission_authorized'}
        raw = _closed(raw, keys)
        if any(type(raw[name]) is not dict for name in ('files', 'source_bindings', 'evidence_bindings')) or type(raw['permissions']) is not list:
            raise ValidationError('Malformed runtime source/file/permission collections')
        request = cls(raw['job_id'], raw['project_id'], raw['revision'], raw['project_file_sha256'],
            raw['master_sha256'], tuple(raw['files'].items()), tuple(raw['source_bindings'].items()),
            tuple(raw['evidence_bindings'].items()), tuple(EngineInputPermission.from_dict(item) for item in raw['permissions']),
            raw['requested_capability'])
        if canonical_bytes(raw) != canonical_bytes(request.to_dict()):
            raise ValidationError('Runtime contract changed its profile, implementation hash or unapproved flags')
        return request
