"""Closed animated-sprite contract over existing saved source rights and clip."""
from dataclasses import dataclass
from hashlib import sha256
import json
from .errors import ValidationError
from .sprite_render import SpriteRenderRequest,canonical,POLICY as NEUTRAL_POLICY
from .expression_clip import validate_expression_clip
from .expressions import TARGETS,is_sha256
from .skin_material import SkinMaterialSpec

POLICY='UCC_PRIVATE_FACIAL_SPRITES_V1'
STAGE='stage_mpfb_facial_sprites'
VERIFY='verify_mpfb_facial_sprites'
TARGET_BINDINGS={t.role+'_'+t.family+'_sha256':t.sha256 for t in TARGETS}


@dataclass(frozen=True,slots=True)
class FacialSpriteRequest:
    review: SpriteRenderRequest
    clip_json: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.review,SpriteRenderRequest) or type(self.clip_json) is not bytes:
            raise ValidationError('Facial sprites need an exact source review and immutable expression clip')
        try:clip=validate_expression_clip(json.loads(self.clip_json))
        except (ValueError,TypeError) as error:raise ValidationError('Malformed facial sprite clip') from error
        if canonical(clip)!=self.clip_json:raise ValidationError('Facial sprite clip must use canonical closed JSON')
        source=clip['source'];r=self.review;bindings=dict(r.source_bindings)
        if (source['project_id']!=r.project_id or source['revision']!=r.revision
                or source['master_sha256']!=bindings['master'] or source['library_sha256']!=bindings['expression_library']):
            raise ValidationError('Facial sprite clip differs from the reviewed saved character')
        if not any(v>0 for v in clip['parameters'].values()):
            raise ValidationError('Save at least one nonzero expression strength before rendering animation')

    @property
    def clip(self) -> dict:return json.loads(self.clip_json)

    @property
    def sha256(self) -> str:return sha256(canonical(self.to_dict())).hexdigest()

    def to_dict(self) -> dict:
        fields=self.review.to_dict()
        fields.update(policy=POLICY,animation_clips=True,expression_clip=self.clip)
        return fields

    @classmethod
    def from_dict(cls,raw: dict) -> 'FacialSpriteRequest':
        if type(raw) is not dict or raw.get('policy')!=POLICY or raw.get('animation_clips') is not True or 'expression_clip' not in raw:
            raise ValidationError('Malformed animated sprite request')
        neutral={k:v for k,v in raw.items() if k!='expression_clip'}
        neutral.update(policy=NEUTRAL_POLICY,animation_clips=False)
        result=cls(SpriteRenderRequest.from_dict(neutral),canonical(validate_expression_clip(raw['expression_clip'])))
        if canonical(result.to_dict())!=canonical(raw):raise ValidationError('Animated sprite contract or capability flags changed')
        return result


def validate_recipe(raw: dict) -> dict:
    if type(raw) is not dict or set(raw)!={'schema_version','policy','request','material_spec'} or type(raw['schema_version']) is not int or raw['schema_version']!=1 or raw['policy']!=POLICY:
        raise ValidationError('Malformed facial sprite recipe')
    FacialSpriteRequest.from_dict(raw['request']);SkinMaterialSpec.from_dict(raw['material_spec'])
    return raw


def validate_job(operation: str,input_project: str,options: dict) -> None:
    fields={'master_sha256','recipe_sha256','clip_sha256',*TARGET_BINDINGS}
    if operation==VERIFY:fields|={'scene_sha256','stage_sha256'}
    if (operation not in (STAGE,VERIFY) or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or not all(is_sha256(v) for v in options.values())
            or any(options[k]!=v for k,v in TARGET_BINDINGS.items())):
        raise ValidationError('Facial sprite worker needs all pinned source, clip, target and render identities')
