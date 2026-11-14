"""Closed, source-bound contracts for actual compatible MPFB hand assets.

These contracts do not attest to geometry by themselves. Registration and
revision APIs must require independent Blender reconstruction of the assets.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING

from .errors import CompatibilityError, ValidationError
from .facial import FACE_BASE_SHA256, FACE_RIG_SHA256, validate_face_parameters

if TYPE_CHECKING:
    from .models import CharacterProject

POLICY = 'SOURCE_BOUND_MPFB_JOINED_HAND_ASSETS_V1'
SLOT = 'hand.L'
ROOT_BONE = 'wrist.L'
STRENGTH = .25
METADATA_SHA256 = '8cb1417bc55ae5ec8aa99f90734e81ed5fbb556511ff6a2c00e0534b70911444'
BORDER_SHA256 = '12c0267fc1336bf86c18812647072b2b186f48a2f2f1ca574ff7025c141cbcd6'
POLYGONS_SHA256 = '0c56e582decee01bf98509eb36b06a1b7ed80a6a9bcbc8605722b02304026a63'


@dataclass(frozen=True, slots=True)
class HandTarget:
    variant: str
    filename: str
    sha256: str


TARGETS = (
    HandTarget('shorter', 'l-hand-fingers-length-decr.target.gz',
               '77e720f2da2d446262bb698f453177abbf94b3e7aec37594ddd518c893721acf'),
    HandTarget('longer', 'l-hand-fingers-length-incr.target.gz',
               '37620de4a7d2f3c8f1b233fc42ebf6c6c6b100ce1aecfe4ed4ada2f0e4006637'),
)


def is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise ValidationError('Hand contract must be finite JSON') from error
    return sha256(encoded.encode('utf-8')).hexdigest()


def source_intent(project: 'CharacterProject') -> dict:
    """Bind saved body/face intent without importing Blender or inferring rights."""
    if project.family != 'humanoid.v1' or project.base_provider != 'mpfb' or project.animations:
        raise CompatibilityError('Hand assets require an unanimated MPFB humanoid')
    parameters = dict(project.parameters)
    if set(parameters) != {'height', 'muscle', 'weight'}:
        raise ValidationError('Hand assets require explicit saved body parameters')
    return {'project_id': project.project_id, 'body_parameters': parameters,
            'facial_parameters': validate_face_parameters(dict(project.facial_parameters)),
            'height_m': project.height_m}


def _recipe(source: dict, master_sha256: str) -> dict:
    return {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1',
            'mpfb_version': '2.0.18', 'slot': SLOT, 'root_bone': ROOT_BONE,
            'source': source, 'strength': STRENGTH,
            'bindings': {'master_sha256': master_sha256, 'base_sha256': FACE_BASE_SHA256,
                         'rig_sha256': FACE_RIG_SHA256, 'metadata_sha256': METADATA_SHA256,
                         'border_sha256': BORDER_SHA256, 'polygons_sha256': POLYGONS_SHA256},
            'variants': [{'variant': t.variant, 'target_file': t.filename,
                          'target_sha256': t.sha256, 'asset_file': 'hand-'+t.variant+'.blend'}
                         for t in TARGETS]}


def build_hand_library_recipe(project: 'CharacterProject', master_sha256: str) -> dict:
    if not is_sha256(master_sha256):
        raise ValidationError('Hand library needs the immutable original master SHA-256')
    if project.parts or project.master_blend is None:
        raise CompatibilityError('Build hand assets from an existing master without attached parts')
    return _recipe(source_intent(project), master_sha256)


def validate_hand_library_recipe(raw: object) -> dict:
    fields = {'schema_version', 'policy', 'family', 'mpfb_version', 'slot', 'root_bone',
              'source', 'strength', 'bindings', 'variants'}
    if type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int:
        raise ValidationError('Invalid closed hand-library recipe')
    source = raw['source']
    if type(source) is not dict or set(source) != {'project_id', 'body_parameters', 'facial_parameters', 'height_m'}:
        raise ValidationError('Hand library lacks complete saved source intent')
    from .models import CharacterProject
    try:
        project = CharacterProject.new('Hand recipe validation')
        from dataclasses import replace
        if type(source['body_parameters']) is not dict or type(source['facial_parameters']) is not dict:
            raise ValidationError('Hand source parameters must be objects')
        project = replace(project, project_id=source['project_id'], schema_version=2,
                          parameters=tuple(source['body_parameters'].items()),
                          facial_parameters=tuple(source['facial_parameters'].items()), height_m=source['height_m'])
        normalized = source_intent(project)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError('Invalid hand source intent') from error
    bindings = raw['bindings']
    if type(bindings) is not dict or not is_sha256(bindings.get('master_sha256')):
        raise ValidationError('Missing original hand-source identity')
    expected = _recipe(normalized, bindings['master_sha256'])
    if canonical_digest(raw) != canonical_digest(expected):
        raise ValidationError('Hand recipe differs from the pinned source, assets or policy')
    return expected


def ensure_source_intent(project: 'CharacterProject', recipe: object) -> dict:
    checked = validate_hand_library_recipe(recipe)
    if canonical_digest(source_intent(project)) != canonical_digest(checked['source']):
        raise CompatibilityError('Body, face or project changed; build compatible hand assets again')
    return checked


def build_hand_manifest(recipe: object, assets: object) -> dict:
    checked = validate_hand_library_recipe(recipe)
    if type(assets) is not dict or set(assets) != {t.variant for t in TARGETS}:
        raise ValidationError('Hand manifest requires both independently verified actual assets')
    for value in assets.values():
        if (type(value) is not dict or set(value) != {'sha256', 'observation_sha256'}
                or not all(is_sha256(v) for v in value.values())):
            raise ValidationError('Hand manifest lacks immutable asset/observation identities')
    return {'schema_version': 1, 'policy': POLICY, 'recipe': checked, 'assets': assets,
            'rights': {'local_project_preview': True, 'source_rights_retained': True,
                       'no_ai': True, 'ai_input_allowed': False,
                       'engine_export_authorized': False, 'source_redistribution_authorized': False}}


def validate_hand_manifest(raw: object) -> dict:
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'recipe', 'assets', 'rights'}
            or type(raw['schema_version']) is not int):
        raise ValidationError('Invalid closed hand manifest')
    expected = build_hand_manifest(raw['recipe'], raw['assets'])
    if canonical_digest(raw) != canonical_digest(expected):
        raise ValidationError('Hand manifest differs from verified bindings or retained rights')
    return expected


def hand_asset_id(manifest_sha256: str, variant: str) -> str:
    if not is_sha256(manifest_sha256) or type(variant) is not str or variant not in {t.variant for t in TARGETS}:
        raise ValidationError('Invalid immutable hand asset selection')
    return 'ucc-hand-v1-'+manifest_sha256+'-'+variant


def hand_selection(project: 'CharacterProject', manifest_sha256: str) -> str:
    """Read saved intent, never infer whether geometry has actually been applied."""
    if not is_sha256(manifest_sha256):
        raise ValidationError('Hand selection requires an immutable manifest identity')
    if not project.parts:
        return 'neutral'
    if len(project.parts) != 1 or project.parts[0].slot != SLOT or not project.parts[0].visible:
        raise CompatibilityError('Only one visible compatible left-hand part is supported')
    for target in TARGETS:
        if project.parts[0].part_asset_id == hand_asset_id(manifest_sha256, target.variant):
            return target.variant
    raise CompatibilityError('Saved part does not belong to this verified hand library')


def build_hand_receipt(manifest_sha256: str, master_sha256: str, original_master_sha256: str,
                       selection: str, observation_sha256: str) -> dict:
    if (not all(is_sha256(v) for v in (manifest_sha256, master_sha256, original_master_sha256, observation_sha256))
            or type(selection) is not str or selection not in {t.variant for t in TARGETS}):
        raise ValidationError('Invalid hand revision receipt bindings')
    return {'schema_version':1, 'policy':POLICY, 'manifest_sha256':manifest_sha256,
            'master_sha256':master_sha256, 'original_master_sha256':original_master_sha256,
            'selection':selection, 'observation_sha256':observation_sha256}


def validate_hand_receipt(raw: object) -> dict:
    fields = {'schema_version','policy','manifest_sha256','master_sha256',
              'original_master_sha256','selection','observation_sha256'}
    if type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int:
        raise ValidationError('Invalid closed hand revision receipt')
    expected = build_hand_receipt(raw['manifest_sha256'],raw['master_sha256'],
                                  raw['original_master_sha256'],raw['selection'],raw['observation_sha256'])
    if canonical_digest(raw) != canonical_digest(expected):
        raise ValidationError('Hand revision receipt differs from its immutable bindings')
    return expected
