"""Explicit first-party opaque body color; no textures, assets or rights inference."""
from dataclasses import dataclass
import math
import json
from .errors import ValidationError
from .models import CharacterProject
from .expressions import is_sha256 as _hash
from hashlib import sha256

POLICY = 'UCC_MPFBBODY_PRINCIPLED_COLOR_V1'
RECIPE_POLICY = 'UCC_PREPARED_BODY_MATERIAL_CANDIDATE_V1'
OPERATIONS = frozenset({'stage_mpfb_skin_material','verify_mpfb_skin_material'})
APPEARANCE_KEY = 'ucc.body_material.v1'


def require_material_preservation(project: CharacterProject) -> None:
    if APPEARANCE_KEY in dict(project.appearance):
        raise ValidationError('This body/face operation has no verified material preservation path; saved material master remains unchanged')


def canonical_bytes(value: object) -> bytes:
    try:return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    except (ValueError,TypeError,OverflowError,RecursionError) as error:
        raise ValidationError('Material contract requires bounded finite JSON values') from error


@dataclass(frozen=True, slots=True)
class SkinMaterialSpec:
    base_color_srgb: tuple[float,float,float]
    roughness: float

    def __post_init__(self) -> None:
        if (type(self.base_color_srgb) is not tuple or len(self.base_color_srgb)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in (*self.base_color_srgb,self.roughness))):
            raise ValidationError('Body material needs explicit finite RGB and roughness values between zero and one')
        object.__setattr__(self,'base_color_srgb',tuple(float(v) for v in self.base_color_srgb))
        object.__setattr__(self,'roughness',float(self.roughness))

    @property
    def linear_rgba(self) -> tuple[float,float,float,float]:
        return (*tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in self.base_color_srgb),1.)

    def to_dict(self) -> dict:
        return {'schema_version':1,'policy':POLICY,'base_color_srgb':list(self.base_color_srgb),'roughness':self.roughness,
            'metallic':0.,'alpha':1.,'textures':False,'source':'FIRST_PARTY_EXPLICIT_PARAMETERS'}

    @property
    def sha256(self) -> str:return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls,raw: object) -> 'SkinMaterialSpec':
        if type(raw) is not dict or type(raw.get('base_color_srgb')) is not list:
            raise ValidationError('Body material spec must be a closed versioned object')
        try:spec=cls(tuple(raw['base_color_srgb']),raw['roughness'])
        except (KeyError,TypeError) as error:raise ValidationError('Malformed body material spec') from error
        if canonical_bytes(spec.to_dict())!=canonical_bytes(raw):raise ValidationError('Unsupported or altered body material policy')
        return spec


def material_recipe(project: CharacterProject,project_sha: str,sources: dict[str,str],spec: SkinMaterialSpec) -> dict:
    if (not isinstance(project,CharacterProject) or project.master_blend is None or project.expression is None
            or project.family!='humanoid.v1' or project.base_provider!='mpfb'
            or project.animations or not _hash(project_sha) or not isinstance(spec,SkinMaterialSpec)
            or type(sources) is not dict or set(sources)!={'master','expression_library'}|{'part:'+p.part_asset_id for p in project.parts}
            or any(not _hash(value) for value in sources.values())
            or project.master_blend!='master/versions/'+sources['master']+'.blend'
            or project.expression.library_sha256!=sources['expression_library']):
        raise ValidationError('Material preparation needs an exact saved prepared MPFB source closure')
    result={'schema_version':1,'policy':RECIPE_POLICY,'project_snapshot':project.to_dict(),'project_file_sha256':project_sha,
        'source_bindings':sources,'spec':spec.to_dict(),'spec_sha256':spec.sha256,'scope':'WHOLE_HUMAN_OPAQUE_COLOR_ONLY',
        'project_publication_authorized':False,'source_rights_changed':False,'cloud_transmission_authorized':False,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    if len(canonical_bytes(result))>256*1024:raise ValidationError('Material recipe exceeds its bounded source contract')
    return result


def validate_material_recipe(raw: object) -> dict:
    if type(raw) is not dict:raise ValidationError('Material recipe must be an object')
    try:
        expected=material_recipe(CharacterProject.from_dict(raw['project_snapshot']),raw['project_file_sha256'],
            raw['source_bindings'],SkinMaterialSpec.from_dict(raw['spec']))
    except (KeyError,TypeError,AttributeError) as error:raise ValidationError('Malformed material source recipe') from error
    if canonical_bytes(expected)!=canonical_bytes(raw):raise ValidationError('Material source recipe changed its closed bindings or authorization')
    return expected


def validate_material_job(operation: str,input_project: object,options: object) -> None:
    fields={'master_sha256','recipe_sha256'}
    if operation=='verify_mpfb_skin_material':fields|={'material_master_sha256','stage_report_sha256','glb_sha256'}
    if (operation not in OPERATIONS or input_project!='candidate.blend' or type(options) is not dict
            or set(options)!=fields or any(not _hash(value) for value in options.values())):
        raise ValidationError('Material worker requires fixed files and a complete closed set of hashes')
