"""Independent worker intake for explicit, source-bound shoulder layers.

No application-core imports: both processes validate the complete contract.
The caller supplies an independently validated legacy base plan and hierarchy.
"""
import math

from blender_bridge.native_fit_policy import BASE_HASHES, POLICY as ARM_POLICY, BODY_POLICY, parse_fit
from blender_bridge.native_hand_fit import POLICY as HAND_POLICY
from blender_bridge.native_inputs import read_json

POLICY = 'BOUNDED_NATIVE_SYMMETRIC_CLAVICLE_LAYER_V4'
BASE_FIT_HASHES = {'base_fit_policy_sha256', 'base_fitted_sha256', 'base_fit_report_sha256'}
BINDINGS = BASE_HASHES | BASE_FIT_HASHES


def layer_fields(fields, options):
    return fields | (BASE_FIT_HASHES if type(options) is dict and BASE_FIT_HASHES & set(options) else set())


def _number(value):
    return type(value) in (int, float) and -1e6 <= value <= 1e6 and math.isfinite(value)


def _vector(value):
    if type(value) is not list or len(value) != 3 or any(not _number(v) for v in value):
        raise ValueError('Symmetric worker needs a finite three-component control')
    return tuple(float(v) for v in value)


def _trajectory(values, fps, maximum, angular):
    if any(math.hypot(*v) > maximum+1e-12 for v in values):
        raise ValueError('Symmetric worker exceeds fixed control magnitude')
    if any(values[0]) or any(values[-1]):
        raise ValueError('Symmetric worker needs unchanged clip endpoints')
    velocities = [(0., 0., 0.)] + [tuple((b[j]-a[j])*fps for j in range(3))
                                  for a, b in zip(values, values[1:])] + [(0., 0., 0.)]
    speed, acceleration = (90., 900.) if angular else (.3, 5.)
    if (any(math.hypot(*v) > speed+1e-9 for v in velocities) or
            any(math.dist(a, b)*fps > acceleration+1e-9 for a, b in zip(velocities, velocities[1:]))):
        raise ValueError('Symmetric worker exceeds fixed speed/acceleration')


def parse_symmetric(data, bindings, baseline, profile, parents, base):
    try:
        return _parse(data, bindings, baseline, profile, parents, base)
    except (KeyError, TypeError, IndexError, OverflowError, RecursionError) as error:
        raise ValueError('Malformed symmetric worker context or controls') from error


def _parse(data, bindings, baseline, profile, parents, base):
    required = {'schema_version', 'policy', 'bindings', 'coordinate_space', 'chains', 'fps', 'frames'}
    if (type(data) is not dict or set(data)-{'render_frames'} != required or
            type(data['schema_version']) is not int or data['schema_version'] != 1 or data['policy'] != POLICY or
            data['coordinate_space'] != 'BLENDER_WORLD_METERS' or type(bindings) is not dict or
            set(bindings) != BINDINGS or any(type(v) is not str or len(v) != 64 or
                any(c not in '0123456789abcdef' for c in v) for v in bindings.values()) or data['bindings'] != bindings or
            profile.get('skin_deformation_policy') != 'BOUND_CORRECTIVE_SMOOTH_V1' or
            profile.get('mesh_strain_reference') != 'TRUE_NEUTRAL_BIND_V2'):
        raise ValueError('Symmetric worker needs exact source/base identities and neutral-reference skin')
    if (type(base) is not dict or base.get('policy') not in (ARM_POLICY, HAND_POLICY, BODY_POLICY) or
            base.get('bindings') != {k: bindings[k] for k in BASE_HASHES}):
        raise ValueError('Symmetric worker requires an independently validated legacy base')
    targets = [p['target'] for p in profile['pairs']]
    if (not 1 <= len(targets) <= 64 or len(set(targets)) != len(targets) or targets != base['targets'] or
            targets != [p['target'] for p in baseline['mapped_pairs']]):
        raise ValueError('Symmetric worker target order differs')
    known = set(targets) | set(baseline['neutral_target_helpers'])
    if (type(parents) is not dict or set(parents) != known or len(known) > 256 or
            any(type(n) is not str or (p is not None and (type(p) is not str or p not in known)) for n, p in parents.items()) or
            sum(p is None for p in parents.values()) != 1):
        raise ValueError('Symmetric worker needs the complete actual target hierarchy')
    paths = {}
    for name in parents:
        path = []; current = name
        while current is not None:
            if current in path: raise ValueError('Cyclic symmetric worker hierarchy')
            path.append(current); current = parents[current]
        paths[name] = path
    count, fps = baseline['source_frame_count'], data['fps']
    if (type(count) is not int or not 5 <= count <= 2000 or not _number(fps) or not 1 <= fps <= 240 or
            fps != baseline['fps'] or fps != base['fps'] or len(base['offsets']) != count or
            (base.get('hand_rotations') and len(base['hand_rotations']) != count) or
            type(data['frames']) is not list or len(data['frames']) != count):
        raise ValueError('Symmetric worker requires complete source and base timelines')
    landmarks = baseline['target_anatomical_landmarks']
    head, left, right = (_vector(landmarks[k]) for k in ('head', 'left_foot', 'right_foot'))
    span = math.dist(head, tuple((left[j]+right[j])/2 for j in range(3)))
    if not .1 < span < 10: raise ValueError('Invalid symmetric worker anatomical span')
    maximum = min(.08, span*.05)
    chains = data['chains']
    if type(chains) is not dict or set(chains) != {'left', 'right'}:
        raise ValueError('Symmetric worker needs both explicit shoulder chains')
    columns = {s: {k: [] for k in ('offset', 'clavicle', 'hand')} for s in ('left', 'right')}
    fields = {'frame'} | {s+'_'+k for s in columns for k in
                         ('offset_world', 'clavicle_rotation_world_degrees', 'hand_rotation_local_degrees')}
    active = []
    for frame, row in enumerate(data['frames'], 1):
        if type(row) is not dict or set(row) != fields or type(row['frame']) is not int or row['frame'] != frame:
            raise ValueError('Symmetric worker needs complete ordered frame controls')
        for side in columns:
            for key, suffix in (('offset', 'offset_world'), ('clavicle', 'clavicle_rotation_world_degrees'),
                                ('hand', 'hand_rotation_local_degrees')):
                columns[side][key].append(_vector(row[side+'_'+suffix]))
        changed = any(any(columns[s][k][-1]) for s in columns for k in columns[s])
        if changed and (any(base['offsets'][frame-1]) or
                        (base.get('hand_rotations') and any(base['hand_rotations'][frame-1]))):
            raise ValueError('SYMMETRIC_BASE_ACTIVITY_OVERLAP; base correction retained')
        active.append(changed)
    meaningful = False
    for side in columns:
        for key, values in columns[side].items():
            _trajectory(values, fps, maximum if key == 'offset' else 15., key != 'offset')
            meaningful |= any(math.hypot(*v) > (1e-7 if key == 'offset' else 1e-6) for v in values)
    if not meaningful: raise ValueError('Symmetric worker requires a measurable correction')
    sides = {}
    for side, values in columns.items():
        chain = chains[side]
        if (type(chain) is not dict or set(chain) != {'clavicle', 'upper_arm', 'forearm', 'hand'} or
                any(type(n) is not str or n not in targets for n in chain.values()) or len(set(chain.values())) != 4 or
                targets[0] in chain.values() or chain['hand'] != profile['landmarks'][side+'_hand']['target'] or
                [n for n in paths[chain['hand']][1:] if n in targets][:3] !=
                [chain['forearm'], chain['upper_arm'], chain['clavicle']]):
            raise ValueError('Symmetric worker chain crosses its actual mapped hand hierarchy')
        descendants = [n for n in targets if chain['hand'] in paths[n]]
        branch = [n for n in targets if chain['clavicle'] in paths[n]]
        if set(branch) != {chain['clavicle'], chain['upper_arm'], chain['forearm'], *descendants}:
            raise ValueError('Symmetric worker would change an undeclared shoulder descendant')
        sides[side] = {'targets': targets, 'clavicle': chain['clavicle'], 'branch': branch,
                       'chain': tuple(chain[k] for k in ('upper_arm', 'forearm', 'hand')),
                       'descendants': descendants, 'offsets': values['offset'], 'maximum': maximum,
                       'clavicle_rotations': values['clavicle'], 'fps': float(fps),
                       'hand_rotations': values['hand'] if any(any(v) for v in values['hand']) else ()}
    if set(sides['left']['branch']) & set(sides['right']['branch']):
        raise ValueError('Symmetric worker shoulder branches overlap')
    samples = data.get('render_frames', [])
    if 'render_frames' in data and (type(samples) is not list or len(samples) != 5 or
            any(type(f) is not int or not 1 <= f <= count for f in samples) or samples != sorted(set(samples)) or
            not any(active[f-1] for f in samples)):
        raise ValueError('Symmetric worker needs five ordered samples including an active correction')
    return {'targets': targets, 'left': sides['left'], 'right': sides['right'], 'base': base,
            'active_frames': active, 'fps': float(fps), 'render_frames': samples, 'policy': POLICY}


def load_symmetric(root, options, baseline, profile, parents):
    source_bindings = {k: options[k] for k in BASE_HASHES}
    base_data = read_json(root/'base_contact_fit.json', options['base_fit_policy_sha256'], 512*1024)
    base = parse_fit(base_data, source_bindings, baseline, profile, parents)
    base['bindings'] = source_bindings
    data = read_json(root/'contact_fit.json', options['fit_sha256'], 512*1024)
    return parse_symmetric(data, {k: options[k] for k in BINDINGS}, baseline, profile, parents, base)
