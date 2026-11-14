"""Closed expression-template provenance, separate from current body approval."""
from dataclasses import replace
from hashlib import sha256
import json

from .errors import ValidationError
from .expression_recipe import validate_expression_recipe
from .expressions import POLICY, is_sha256


def canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValidationError('Expression provenance requires bounded finite JSON values') from error
    return sha256(encoded).hexdigest()


def source_intent(project) -> dict:
    from .hand_parts import source_intent as humanoid_source_intent
    return humanoid_source_intent(project)


def build_expression_manifest(source: dict, recipe: object, prepared_sha256: str,
                              report_sha256: str, observation_sha256: str) -> dict:
    from .models import CharacterProject
    if (type(source) is not dict or set(source) != {'project_id', 'body_parameters', 'facial_parameters', 'height_m'}
            or type(source['body_parameters']) is not dict or type(source['facial_parameters']) is not dict):
        raise ValidationError('Expression library requires its complete initial humanoid source intent')
    try:
        project = replace(CharacterProject.new('Expression provenance validation'), schema_version=2,
                          project_id=source['project_id'], parameters=tuple(source['body_parameters'].items()),
                          facial_parameters=tuple(source['facial_parameters'].items()), height_m=source['height_m'])
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError('Expression library source contains invalid humanoid intent') from error
    normalized = source_intent(project)
    checked = validate_expression_recipe(recipe)
    if not all(is_sha256(v) for v in (prepared_sha256, report_sha256, observation_sha256)):
        raise ValidationError('Expression library requires verified immutable scene/report/observation identities')
    if prepared_sha256 == checked['bindings']['master_sha256']:
        raise ValidationError('Neutral expression preparation must produce a different master identity')
    return {'schema_version': 1, 'policy': POLICY, 'source': normalized, 'recipe': checked,
            'prepared_master_sha256': prepared_sha256, 'report_sha256': report_sha256,
            'observation_sha256': observation_sha256,
            'rights': {'local_project_preview': True, 'source_rights_retained': True, 'no_ai': True,
                       'ai_input_allowed': False, 'engine_export_authorized': False,
                       'source_redistribution_authorized': False}}


def validate_expression_manifest(raw: object) -> dict:
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'source', 'recipe',
            'prepared_master_sha256', 'report_sha256', 'observation_sha256', 'rights'}
            or type(raw['schema_version']) is not int):
        raise ValidationError('Invalid closed expression-library manifest')
    expected = build_expression_manifest(raw['source'], raw['recipe'], raw['prepared_master_sha256'],
                                         raw['report_sha256'], raw['observation_sha256'])
    if canonical_digest(raw) != canonical_digest(expected):
        raise ValidationError('Expression provenance differs from pinned preparation or retained rights')
    return expected
