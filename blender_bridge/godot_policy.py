"""Independent Blender admission; fixed files, source roles and engine policies."""
from pathlib import Path

from blender_bridge.expression_clip_policy import recipe as expression_recipe
from blender_bridge.expression_policy import TARGETS, filename
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest, read_json

POLICY = 'MPFB_GODOT_CANDIDATE_SOURCE_V1'
OPERATIONS = {'stage_mpfb_godot_candidate', 'verify_mpfb_godot_candidate'}
OUTPUTS = {'character.glb': 'candidate_sha256', 'source_review.blend': 'review_scene_sha256',
           'blender_stage.json': 'stage_report_sha256', 'source_positions.bin': 'positions_sha256',
           'bind_positions.bin': 'bind_positions_sha256', 'source_bones.bin': 'bones_sha256',
           'source_action.json': 'action_report_sha256'}


def is_hash(value) -> bool:
    return type(value) is str and len(value) == 64 and all(char in '0123456789abcdef' for char in value)


def text(value, maximum=160) -> bool:
    return type(value) is str and 0 < len(value) <= maximum and value.strip() == value and all(ord(c) >= 32 for c in value)


def checked_recipe(raw: object, clip: dict, options: dict) -> dict:
    fields = {'schema_version', 'policy', 'project', 'source_bindings', 'motion_asset_id',
              'permissions', 'expression_clip_sha256', 'timeline', 'source_role',
              'engine_import_verified', 'visual_quality_approved',
              'source_redistribution_authorized', 'cloud_transmission_authorized'}
    if (type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int
            or raw['schema_version'] != 1 or raw['policy'] != POLICY):
        raise ValueError('Unsupported closed Godot Blender source recipe')
    project = raw['project']; sources = raw['source_bindings']; motion = raw['motion_asset_id']
    if (type(project) is not dict or set(project) != {'project_id', 'revision', 'project_file_sha256', 'project_snapshot_sha256'}
            or project['project_id'] != clip['source']['project_id'] or type(project['revision']) is not int
            or project['revision'] != clip['source']['revision'] or not is_hash(project['project_file_sha256'])
            or project['project_snapshot_sha256'] != clip['source']['project_snapshot_sha256']
            or type(sources) is not dict or not 3 <= len(sources) <= 128
            or any(not text(key) or not is_hash(value) for key, value in sources.items())
            or not text(motion) or not motion.startswith('motion:') or motion not in sources
            or sources.get('master') != options['master_sha256']
            or sources.get('expression_library') != clip['source']['library_sha256']
            or sources[motion] != options['target_motion_sha256']
            or any(key not in {'master', 'expression_library', motion} and not key.startswith('part:') for key in sources)
            or raw['expression_clip_sha256'] != options['clip_sha256']):
        raise ValueError('Godot Blender source/project/clip identities differ')
    policy_fields = {'provider', 'license_name', 'source_uri', 'reviewed', 'no_ai', 'ue_only',
                     'can_use_non_unreal', 'can_use_unreal', 'ai_input_allowed',
                     'redistribute_source_allowed', 'local_preview_allowed'}
    rows = raw['permissions']; names = set()
    if type(rows) is not list or len(rows) != len(sources):
        raise ValueError('Godot Blender source lacks complete per-input engine permissions')
    for row in rows:
        if (type(row) is not dict or set(row) != {'asset_id', 'source_sha256', 'source_only', 'policy'}
                or not text(row['asset_id']) or row['asset_id'] in names or row['asset_id'] not in sources
                or row['source_sha256'] != sources[row['asset_id']] or row['source_only'] is not False):
            raise ValueError('Source-only, duplicate or mismatched Godot Blender input permission')
        names.add(row['asset_id']); policy = row['policy']
        if (type(policy) is not dict or set(policy) != policy_fields
                or any(not text(policy[key], 2048) for key in ('provider', 'license_name', 'source_uri'))
                or any(type(policy[key]) is not bool for key in policy_fields-{'provider', 'license_name', 'source_uri'})
                or not policy['reviewed'] or policy['ue_only'] or not policy['can_use_non_unreal']):
            raise ValueError('Godot Blender input lacks reviewed cross-engine use permission')
        if row['asset_id'] not in {'master', motion} and (not policy['no_ai'] or policy['ai_input_allowed']):
            raise ValueError('Godot Blender input cannot remove retained library NoAI restrictions')
    expected = {**raw, 'schema_version': 1, 'policy': POLICY,
        'timeline': {'fps': 24, 'first_frame': 1, 'last_frame': 25},
        'source_role': 'TARGET_ACTION_ONLY_AUTHORITATIVE_MASTER_GEOMETRY_V1',
        'engine_import_verified': False, 'visual_quality_approved': False,
        'source_redistribution_authorized': False, 'cloud_transmission_authorized': False}
    if state_digest(expected) != state_digest(raw):
        raise ValueError('Godot Blender recipe changed timeline, source role or unapproved rights/readiness')
    return raw


def checked_inputs(root: Path, job: dict) -> tuple[dict, dict]:
    options = job['options']; operation = job['operation']
    names = {'candidate.blend': 'master_sha256', 'target_motion.blend': 'target_motion_sha256',
             'export_recipe.json': 'export_recipe_sha256', 'expression_clip.json': 'clip_sha256',
             **{filename(role, family): role+'_'+family+'_sha256' for role, family, _ in TARGETS}}
    if operation == 'verify_mpfb_godot_candidate':
        names.update(OUTPUTS)
    if (operation not in OPERATIONS or job['input_project'] != 'candidate.blend'
            or type(options) is not dict or set(options) != set(names.values())
            or any(not is_hash(value) for value in options.values())
            or any(options[role+'_'+family+'_sha256'] != value for role, family, value in TARGETS)):
        raise ValueError('Godot Blender job lacks its fixed complete input/output bindings')
    for name, field in names.items():
        path = root/name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root or path.stat().st_size > 512*1024*1024 or digest(path) != options[field]:
            raise ValueError('Godot Blender input is missing, redirected or changed: '+name)
    clip = expression_recipe(read_json(root/'expression_clip.json', options['clip_sha256'], 256*1024), options['master_sha256'])
    raw = checked_recipe(read_json(root/'export_recipe.json', options['export_recipe_sha256'], 256*1024), clip, options)
    return raw, clip
