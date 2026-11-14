"""Independent facial clip contract and fixed staged file admission."""
import math
from pathlib import Path

from blender_bridge.expression_policy import TARGETS, filename, keyname
from blender_bridge.face_policy import BASE_SHA, RIG_SHA, digest, read_json

POLICY = 'BOUNDED_MPFB_EXPRESSION_CLIP_V1'
ROLES = {'eye_left_closure', 'eye_right_closure', 'mouth_corners', 'mouth_open'}


def recipe(raw: object, master_sha: str) -> dict:
    if type(raw) is not dict or type(raw.get('schema_version')) is not int:
        raise ValueError('Invalid expression clip recipe')
    source, parameters = raw.get('source'), raw.get('parameters')
    if (type(source) is not dict or set(source) != {'project_id', 'revision', 'project_snapshot_sha256',
            'master_sha256', 'library_sha256'} or type(source['project_id']) is not str
            or not source['project_id'].strip() or len(source['project_id']) > 160
            or any(ord(c) < 32 for c in source['project_id']) or type(source['revision']) is not int
            or source['revision'] < 1 or any(type(source[k]) is not str or len(source[k]) != 64
                or any(c not in '0123456789abcdef' for c in source[k])
                for k in ('project_snapshot_sha256', 'master_sha256', 'library_sha256'))
            or source['master_sha256'] != master_sha):
        raise ValueError('Expression clip lacks exact project/master/library identities')
    if (type(parameters) is not dict or set(parameters) != ROLES
            or any(type(v) not in (int, float) or not 0 <= v <= .5 or not math.isfinite(v) for v in parameters.values())):
        raise ValueError('Expression clip strengths are outside the supported finite bounds')
    expected = {'schema_version': 1, 'policy': POLICY, 'mpfb_version': '2.0.18', 'source': source,
        'parameters': {k: float(v) for k, v in parameters.items()},
        'timeline': {'fps': 24, 'first_frame': 1, 'last_frame': 25, 'keyframes': [1, 13, 25], 'interpolation': 'LINEAR'},
        'base_sha256': BASE_SHA, 'rig_sha256': RIG_SHA,
        'targets': [{'role': r, 'family': f, 'file': filename(r, f), 'key': keyname(r, f), 'sha256': sha}
                    for r, f, sha in TARGETS]}
    from blender_bridge.face_operations import state_digest
    if state_digest(raw) != state_digest(expected):
        raise ValueError('Expression clip differs from the independent pinned 25-frame policy')
    return expected


def check_inputs(root: Path, options: dict, *, verify: bool = False) -> dict:
    names = {'candidate.blend': 'master_sha256', 'expression_clip.json': 'clip_sha256',
             **{filename(r, f): r+'_'+f+'_sha256' for r, f, _ in TARGETS}}
    if verify:
        names.update({'expression_motion.blend': 'motion_sha256', 'expression_motion.json': 'motion_report_sha256',
                      'expression_skin.bin': 'cache_sha256', 'expression_skin.json': 'cache_manifest_sha256'})
    if (type(options) is not dict or set(options) != set(names.values()) or any(type(v) is not str
            or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())
            or any(options[r+'_'+f+'_sha256'] != sha for r, f, sha in TARGETS)):
        raise ValueError('Expression clip worker requires all pinned input identities')
    for name, field in names.items():
        path = root/name
        if path.is_symlink() or not path.is_file() or digest(path) != options[field]:
            raise ValueError('Missing or changed expression clip input: '+name)
    return recipe(read_json(root/'expression_clip.json', options['clip_sha256']), options['master_sha256'])
