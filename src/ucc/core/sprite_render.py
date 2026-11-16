"""Closed private neutral sprite render contract; pure data, no renderer imports."""
from dataclasses import dataclass
from hashlib import sha256
import json,math
from uuid import UUID
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec

POLICY='UCC_PRIVATE_NEUTRAL_SPRITES_V1'
STAGE='stage_mpfb_sprite_sample'
VERIFY='verify_mpfb_sprite_sample'


def canonical(value: object) -> bytes:
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


@dataclass(frozen=True,slots=True)
class SpriteSettings:
    resolution: int=256
    directions: int=4
    yaw_deg: float=0.
    pitch_deg: float=0.

    def __post_init__(self) -> None:
        if type(self.resolution) is not int or self.resolution not in (128,256) or type(self.directions) is not int or self.directions not in (4,8):
            raise ValidationError('Sprite sample needs 128/256 pixels and four/eight directions')
        for name,low,high in (('yaw_deg',-180,180),('pitch_deg',-30,30)):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
                raise ValidationError('Sprite camera angle is outside the bounded profile: '+name)

    def to_dict(self) -> dict:
        return {name:getattr(self,name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls,value: dict) -> 'SpriteSettings':
        if type(value) is not dict or set(value)!=set(cls.__dataclass_fields__):raise ValidationError('Malformed sprite settings')
        return cls(**value)

    def angles(self) -> tuple[float,...]:
        return tuple(round((self.yaw_deg+i*360/self.directions)%360,6) for i in range(self.directions))


@dataclass(frozen=True,slots=True)
class SpritePermission:
    asset_id: str
    source_sha256: str
    authorization: str
    reviewed: bool=False
    private_sprite_render_allowed: bool=False
    no_ai: bool=True
    ue_only: bool=False
    redistribute_source_allowed: bool=False

    def __post_init__(self) -> None:
        if (type(self.asset_id) is not str or not 1<=len(self.asset_id)<=160 or not is_sha256(self.source_sha256)
                or type(self.authorization) is not str or not 1<=len(self.authorization.strip())<=2048):
            raise ValidationError('Every sprite source needs its exact identity and reviewed authorization')
        if (self.reviewed is not True or self.private_sprite_render_allowed is not True or self.no_ai is not True
                or self.ue_only is not False or self.redistribute_source_allowed is not False):
            raise ValidationError('Explicit private sprite-render rights are required; retain NoAI and original-source restrictions')

    def to_dict(self) -> dict:return {name:getattr(self,name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls,value: dict) -> 'SpritePermission':
        if type(value) is not dict or set(value)!=set(cls.__dataclass_fields__):raise ValidationError('Malformed closed sprite permission')
        return cls(**value)


@dataclass(frozen=True,slots=True)
class SpriteRenderRequest:
    job_id: str
    project_id: str
    revision: int
    project_sha256: str
    source_bindings: tuple[tuple[str,str],...]
    permissions: tuple[SpritePermission,...]
    settings: SpriteSettings

    def __post_init__(self) -> None:
        try:UUID(self.job_id)
        except (ValueError,TypeError,AttributeError) as error:raise ValidationError('Sprite job needs a UUID') from error
        if (type(self.project_id) is not str or not 1<=len(self.project_id)<=160 or type(self.revision) is not int or self.revision<1
                or not is_sha256(self.project_sha256) or not isinstance(self.settings,SpriteSettings)
                or type(self.source_bindings) is not tuple or not 3<=len(self.source_bindings)<=4
                or any(type(r) is not tuple or len(r)!=2 or type(r[0]) is not str or not is_sha256(r[1]) for r in self.source_bindings)):
            raise ValidationError('Sprite rendering requires an exact saved prepared-character review')
        bound=dict(self.source_bindings)
        if (len(bound)!=len(self.source_bindings) or not {'master','expression_library','body_material'}<=set(bound)
                or any(k not in {'master','expression_library','body_material'} and not k.startswith('part:ucc-hand-v1-') for k in bound)
                or type(self.permissions) is not tuple or len(self.permissions)!=len(bound)
                or any(not isinstance(p,SpritePermission) for p in self.permissions)
                or {p.asset_id for p in self.permissions}!=set(bound)
                or any(p.source_sha256!=bound[p.asset_id] for p in self.permissions)):
            raise ValidationError('Review every exact sprite source separately for this use')

    def to_dict(self) -> dict:
        return {'schema_version':1,'policy':POLICY,**{k:getattr(self,k) for k in ('job_id','project_id','revision','project_sha256')},
                'source_bindings':dict(self.source_bindings),'permissions':[p.to_dict() for p in self.permissions],
                'settings':self.settings.to_dict(),'animation_clips':False,'visual_quality_approved':False,'distribution_license_review_complete':False}

    @property
    def sha256(self) -> str:return sha256(canonical(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls,value: dict) -> 'SpriteRenderRequest':
        fields={'schema_version','policy','job_id','project_id','revision','project_sha256','source_bindings','permissions','settings',
                'animation_clips','visual_quality_approved','distribution_license_review_complete'}
        if type(value) is not dict or set(value)!=fields or type(value['source_bindings']) is not dict or type(value['permissions']) is not list:
            raise ValidationError('Malformed closed sprite request')
        request=cls(value['job_id'],value['project_id'],value['revision'],value['project_sha256'],tuple(value['source_bindings'].items()),
                    tuple(SpritePermission.from_dict(p) for p in value['permissions']),SpriteSettings.from_dict(value['settings']))
        if canonical(request.to_dict())!=canonical(value):raise ValidationError('Sprite capability or approval flags changed')
        return request


def validate_recipe(value: dict) -> dict:
    if type(value) is not dict or set(value)!={'schema_version','policy','request','material_spec'} or type(value['schema_version']) is not int or value['schema_version']!=1 or value['policy']!=POLICY:
        raise ValidationError('Malformed sprite recipe')
    SpriteRenderRequest.from_dict(value['request']);SkinMaterialSpec.from_dict(value['material_spec'])
    return value


def validate_job(operation: str,input_project: str,options: dict) -> None:
    fields={'master_sha256','recipe_sha256'}|({'scene_sha256','stage_sha256'} if operation==VERIFY else set())
    if operation not in (STAGE,VERIFY) or input_project!='candidate.blend' or type(options) is not dict or set(options)!=fields or not all(is_sha256(h) for h in options.values()):
        raise ValidationError('Sprite worker requires a closed source/recipe/saved-scene hash binding')
