"""Closed per-use private export; no catalog or source-rights promotion."""
from dataclasses import dataclass
from uuid import UUID
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from .godot_candidate_contract import EngineInputPermission,canonical_bytes
from hashlib import sha256

POLICY='UCC_PRIVATE_STATIC_GODOT_EXPORT_V1'


@dataclass(frozen=True,slots=True)
class StaticGodotRequest:
    job_id: str
    project_id: str
    revision: int
    project_sha256: str
    source_bindings: tuple[tuple[str,str],...]
    permissions: tuple[EngineInputPermission,...]

    def __post_init__(self) -> None:
        try:UUID(self.job_id)
        except (ValueError,TypeError,AttributeError) as error:raise ValidationError('Export job needs a UUID') from error
        if (type(self.project_id) is not str or not 1<=len(self.project_id)<=160 or type(self.revision) is not int or self.revision<1
                or not is_sha256(self.project_sha256) or type(self.source_bindings) is not tuple or not 3<=len(self.source_bindings)<=4
                or any(type(row) is not tuple or len(row)!=2 or type(row[0]) is not str or not is_sha256(row[1]) for row in self.source_bindings)):
            raise ValidationError('Static Godot export requires exact prepared project/source identities')
        bound=dict(self.source_bindings)
        if (len(bound)!=len(self.source_bindings) or not {'master','expression_library','body_material'}<=set(bound)
                or any(k not in {'master','expression_library','body_material'} and not k.startswith('part:ucc-hand-v1-') for k in bound)
                or type(self.permissions) is not tuple or len(self.permissions)!=len(bound)
                or any(not isinstance(p,EngineInputPermission) for p in self.permissions)
                or {p.asset_id for p in self.permissions}!=set(bound)):
            raise ValidationError('Every export source needs a separate explicit per-use permission')
        for permission in self.permissions:
            if permission.source_sha256!=bound[permission.asset_id]:raise ValidationError('Export permission names different source content')
            permission.require_godot()
            if (not permission.policy.no_ai or permission.policy.ai_input_allowed or permission.policy.redistribute_source_allowed):
                raise ValidationError('Private static export must retain NoAI and forbid original-source redistribution')

    def to_dict(self) -> dict:
        return {'schema_version':1,'policy':POLICY,'job_id':self.job_id,'project_id':self.project_id,'revision':self.revision,
            'project_sha256':self.project_sha256,'source_bindings':dict(self.source_bindings),
            'permissions':[p.to_dict() for p in self.permissions],'engine_major':4,'engine_minor':7,
            'animation_clips':False,'distribution_license_review_complete':False,'visual_quality_approved':False}

    @property
    def sha256(self) -> str:return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls,raw: dict) -> 'StaticGodotRequest':
        fields={'schema_version','policy','job_id','project_id','revision','project_sha256','source_bindings','permissions',
            'engine_major','engine_minor','animation_clips','distribution_license_review_complete','visual_quality_approved'}
        if (type(raw) is not dict or set(raw)!=fields or type(raw['source_bindings']) is not dict or type(raw['permissions']) is not list):
            raise ValidationError('Malformed closed static export request')
        request=cls(raw['job_id'],raw['project_id'],raw['revision'],raw['project_sha256'],tuple(raw['source_bindings'].items()),
            tuple(EngineInputPermission.from_dict(p) for p in raw['permissions']))
        if canonical_bytes(raw)!=canonical_bytes(request.to_dict()):raise ValidationError('Static export capability or approval flags changed')
        return request
