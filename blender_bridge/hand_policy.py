"""Independent closed worker policy for source-bound MPFB hand assets.

This module deliberately does not import the application's core contracts.
"""
from hashlib import sha256
import json
import math
from pathlib import Path

from blender_bridge.face_policy import BASE_SHA, RIG_SHA, digest, read_json

POLICY = 'SOURCE_BOUND_MPFB_JOINED_HAND_ASSETS_V1'
OWN_KEY = 'UCC_HAND_ASSET_LEFT_V1'
SLOT = 'hand.L'
ROOT_BONE = 'wrist.L'
METADATA_SHA = '8cb1417bc55ae5ec8aa99f90734e81ed5fbb556511ff6a2c00e0534b70911444'
BORDER_SHA = '12c0267fc1336bf86c18812647072b2b186f48a2f2f1ca574ff7025c141cbcd6'
POLYGONS_SHA = '0c56e582decee01bf98509eb36b06a1b7ed80a6a9bcbc8605722b02304026a63'
TARGETS = (
    ('shorter', 'l-hand-fingers-length-decr.target.gz',
     '77e720f2da2d446262bb698f453177abbf94b3e7aec37594ddd518c893721acf'),
    ('longer', 'l-hand-fingers-length-incr.target.gz',
     '37620de4a7d2f3c8f1b233fc42ebf6c6c6b100ce1aecfe4ed4ada2f0e4006637'),
)


def is_sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def state_digest(value: object) -> str:
    try:
        return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError('Hand policy requires bounded finite JSON') from error


def _number(value: object, low: float, high: float) -> bool:
    # Check range before isfinite, so a malicious huge integer cannot overflow.
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def validate_recipe(raw: object) -> dict:
    fields = {'schema_version', 'policy', 'family', 'mpfb_version', 'slot', 'root_bone',
              'source', 'strength', 'bindings', 'variants'}
    if type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int:
        raise ValueError('Invalid hand recipe fields/version')
    source = raw['source']
    if type(source) is not dict or set(source) != {'project_id', 'body_parameters', 'facial_parameters', 'height_m'}:
        raise ValueError('Hand recipe lacks saved source intent')
    project_id = source['project_id']
    if (type(project_id) is not str or not project_id.strip() or len(project_id) > 160
            or any(ord(c) < 32 for c in project_id)):
        raise ValueError('Invalid bound hand project identity')
    body, face = source['body_parameters'], source['facial_parameters']
    if (type(body) is not dict or set(body) != {'height', 'muscle', 'weight'}
            or not all(_number(v, 0., 1.) for v in body.values())
            or type(face) is not dict or set(face)-{'nose_width'}
            or not all(_number(v, 0., 1.) for v in face.values())
            or not _number(source['height_m'], .2, 5.)):
        raise ValueError('Invalid hand source body/face/scale values')
    bindings = raw['bindings']
    if type(bindings) is not dict or not is_sha(bindings.get('master_sha256')):
        raise ValueError('Hand recipe lacks original master binding')
    expected = {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1',
                'mpfb_version': '2.0.18', 'slot': SLOT, 'root_bone': ROOT_BONE,
                'source': source, 'strength': .25,
                'bindings': {'master_sha256': bindings['master_sha256'], 'base_sha256': BASE_SHA,
                             'rig_sha256': RIG_SHA, 'metadata_sha256': METADATA_SHA,
                             'border_sha256': BORDER_SHA, 'polygons_sha256': POLYGONS_SHA},
                'variants': [{'variant': variant, 'target_file': filename, 'target_sha256': target_sha,
                              'asset_file': 'hand-'+variant+'.blend'} for variant, filename, target_sha in TARGETS]}
    if state_digest(raw) != state_digest(expected):
        raise ValueError('Hand recipe differs from independently pinned policy/assets')
    return expected


def validate_manifest(raw: object) -> dict:
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'recipe', 'assets', 'rights'}
            or type(raw['schema_version']) is not int):
        raise ValueError('Invalid closed hand manifest')
    recipe = validate_recipe(raw['recipe']);assets = raw['assets']
    if type(assets) is not dict or set(assets) != {'shorter', 'longer'}:
        raise ValueError('Hand manifest lacks both assets')
    for row in assets.values():
        if (type(row) is not dict or set(row) != {'sha256', 'observation_sha256'}
                or not all(is_sha(v) for v in row.values())):
            raise ValueError('Invalid hand asset/observation identity')
    expected = {'schema_version': 1, 'policy': POLICY, 'recipe': recipe, 'assets': assets,
                'rights': {'local_project_preview': True, 'source_rights_retained': True,
                           'no_ai': True, 'ai_input_allowed': False,
                           'engine_export_authorized': False, 'source_redistribution_authorized': False}}
    if state_digest(raw) != state_digest(expected):
        raise ValueError('Hand manifest changes pinned bindings or retained rights')
    return expected


def check_inputs(root: Path, options: dict, *, verify_assets: bool = False) -> dict:
    """Fixed filenames only; no executable code or alternate asset paths accepted."""
    fields = {'master_sha256', 'recipe_sha256', 'metadata_sha256',
              'shorter_target_sha256', 'longer_target_sha256'}
    if verify_assets:
        fields |= {'shorter_asset_sha256', 'longer_asset_sha256', 'assets_report_sha256'}
    if type(options) is not dict or set(options) != fields or not all(is_sha(v) for v in options.values()):
        raise ValueError('Hand asset worker requires complete fixed input identities')
    names = {'candidate.blend': 'master_sha256', 'hand_recipe.json': 'recipe_sha256',
             'basemesh_vertex_groups.json': 'metadata_sha256',
             **{filename: variant+'_target_sha256' for variant, filename, _ in TARGETS}}
    if verify_assets:
        names.update({**{'hand-'+variant+'.blend': variant+'_asset_sha256' for variant, _, _ in TARGETS},
                      'hand_assets_report.json': 'assets_report_sha256'})
    for filename, role in names.items():
        path = root/filename
        if path.is_symlink() or not path.is_file() or digest(path) != options[role]:
            raise ValueError('Missing, redirected or changed hand input: '+filename)
    recipe = validate_recipe(read_json(root/'hand_recipe.json', options['recipe_sha256'], 64*1024))
    if options['master_sha256'] != recipe['bindings']['master_sha256'] or digest(root/'candidate.blend') != options['master_sha256']:
        raise ValueError('Original hand source does not match immutable recipe')
    if options['metadata_sha256'] != METADATA_SHA or digest(root/'basemesh_vertex_groups.json') != METADATA_SHA:
        raise ValueError('Hand topology metadata differs from pinned data')
    for variant, filename, expected in TARGETS:
        if options[variant+'_target_sha256'] != expected or digest(root/filename) != expected:
            raise ValueError('Hand target differs from pinned installed data')
        if verify_assets and digest(root/('hand-'+variant+'.blend')) != options[variant+'_asset_sha256']:
            raise ValueError('Saved hand asset does not match staged identity')
    if verify_assets and digest(root/'hand_assets_report.json') != options['assets_report_sha256']:
        raise ValueError('Hand asset report changed')
    return recipe


def check_revision_inputs(root: Path, options: dict, *, verify: bool = False) -> dict:
    fields = {'master_sha256','original_master_sha256','manifest_sha256','metadata_sha256',
              'shorter_target_sha256','longer_target_sha256','shorter_asset_sha256','longer_asset_sha256',
              'current_selection','selection'}
    if type(options) is not dict:
        raise ValueError('Hand revision requires explicit bound options')
    for name in ('current_selection','selection'):
        if type(options.get(name)) is not str or options[name] not in {'neutral','shorter','longer'}:
            raise ValueError('Hand revision has an unsupported selection')
    if options['current_selection'] != 'neutral':
        fields.add('current_observation_sha256')
    if verify:
        fields |= {'revised_sha256','revision_report_sha256'}
    if set(options) != fields or any(not is_sha(v) for k,v in options.items() if k not in {'selection','current_selection'}):
        raise ValueError('Hand revision lacks complete immutable bindings')
    names = {'candidate.blend':'master_sha256','original.blend':'original_master_sha256',
             'hand_manifest.json':'manifest_sha256','basemesh_vertex_groups.json':'metadata_sha256',
             **{filename:variant+'_target_sha256' for variant,filename,_ in TARGETS},
             **{'hand-'+variant+'.blend':variant+'_asset_sha256' for variant,_,_ in TARGETS}}
    if verify:
        names.update({'revised_human.blend':'revised_sha256','hand_revision_report.json':'revision_report_sha256'})
    for filename,role in names.items():
        path=root/filename
        if path.is_symlink() or not path.is_file() or digest(path) != options[role]:
            raise ValueError('Missing, redirected or changed hand revision input: '+filename)
    manifest=validate_manifest(read_json(root/'hand_manifest.json',options['manifest_sha256'],64*1024))
    if state_digest(manifest) != options['manifest_sha256']:
        raise ValueError('Hand manifest is not in its canonical immutable form')
    if (options['original_master_sha256'] != manifest['recipe']['bindings']['master_sha256']
            or options['metadata_sha256'] != METADATA_SHA):
        raise ValueError('Hand revision original/topology identity differs from its library')
    for variant,_,expected in TARGETS:
        if (options[variant+'_target_sha256'] != expected
                or options[variant+'_asset_sha256'] != manifest['assets'][variant]['sha256']):
            raise ValueError('Hand revision selects an undeclared asset or target')
    if options['current_selection'] == 'neutral' and options['master_sha256'] != options['original_master_sha256']:
        raise ValueError('Neutral hand metadata does not select the original immutable master')
    return manifest
