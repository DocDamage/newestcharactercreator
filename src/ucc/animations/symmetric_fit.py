"""SHA-bound, explicit bilateral correction layered over a verified base fit.

Controls are target-world corrections, not another interpretation of source FK.
The caller must independently validate the source timeline and base evidence.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Callable

from ucc.core.errors import ValidationError
from .contact_fit import ContactFit, HASHES, POLICY as ARM_POLICY, BODY_POLICY, MAX_FIT_BYTES
from .hand_fit import POLICY as HAND_POLICY
from .source_rest_frames import is_sha256

POLICY = 'BOUNDED_NATIVE_SYMMETRIC_CLAVICLE_LAYER_V4'
BASE_HASHES = {'base_fit_policy_sha256', 'base_fitted_sha256', 'base_fit_report_sha256'}
BINDINGS = HASHES | BASE_HASHES
FITTED_HASHES = HASHES | {'fit_sha256', 'fitted_sha256', 'fit_report_sha256'}
Vector3 = tuple[float, float, float]


def fitted_hash_fields(bindings: object) -> set[str]:
    """Both legacy and layered receipts stay closed; partial base hashes reject."""
    return FITTED_HASHES | (BASE_HASHES if type(bindings) is dict and BASE_HASHES & set(bindings) else set())


@dataclass(frozen=True, slots=True)
class ShoulderFit:
    arm: ContactFit
    clavicle: str
    branch: tuple[str, ...]
    rotations: tuple[Vector3, ...]


@dataclass(frozen=True, slots=True)
class SymmetricFit:
    bindings: tuple[tuple[str, str], ...]
    left: ShoulderFit
    right: ShoulderFit
    base: ContactFit
    active_frames: tuple[bool, ...]
    render_frames: tuple[int, ...] = ()
    policy: str = POLICY

    @property
    def targets(self) -> tuple[str, ...]: return self.right.arm.targets

    @property
    def fps(self) -> float: return self.right.arm.fps


def _number(value: object) -> bool:
    return type(value) in (int, float) and -1e6 <= value <= 1e6 and math.isfinite(value)


def _vector(value: object, label: str) -> Vector3:
    if type(value) is not list or len(value) != 3 or any(not _number(v) for v in value):
        raise ValidationError('Symmetric fitting needs finite three-component ' + label)
    return tuple(float(v) for v in value)


def _trajectory(values: list[Vector3], fps: float, maximum: float, angular: bool) -> None:
    label = 'angular' if angular else 'displacement'
    if any(math.hypot(*v) > maximum + 1e-12 for v in values):
        raise ValidationError('Symmetric fitting exceeds its fixed ' + label + ' bound')
    if any(values[0]) or any(values[-1]):
        raise ValidationError('Symmetric fitting requires unchanged clip endpoints')
    velocities = [(0., 0., 0.)] + [tuple((b[j]-a[j])*fps for j in range(3))
                                  for a, b in zip(values, values[1:])] + [(0., 0., 0.)]
    speed, acceleration = (90., 900.) if angular else (.3, 5.)
    if any(math.hypot(*v) > speed + 1e-9 for v in velocities):
        raise ValidationError('Symmetric fitting exceeds its fixed ' + label + ' speed')
    if any(math.dist(a, b)*fps > acceleration + 1e-9 for a, b in zip(velocities, velocities[1:])):
        raise ValidationError('Symmetric fitting exceeds its fixed ' + label + ' acceleration')


def read_symmetric_fit(path: Path, expected_sha: str, bindings: dict, baseline: dict,
                       profile: dict, parents: dict[str, str | None], base: ContactFit,
                       *, cancel_check: Callable[[], None] = lambda: None) -> SymmetricFit:
    """Reject changed, redirected, oversized, duplicate-key and nonfinite input."""
    cancel_check()
    if (not is_sha256(expected_sha) or path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= MAX_FIT_BYTES):
        raise ValidationError('Symmetric fitting needs a bounded SHA-bound regular policy file')
    chunks = []; size = 0
    with path.open('rb') as stream:
        while chunk := stream.read(min(16384, MAX_FIT_BYTES+1-size)):
            cancel_check(); chunks.append(chunk); size += len(chunk)
            if size > MAX_FIT_BYTES: raise ValidationError('Symmetric fitting policy grew beyond its size bound')
    payload = b''.join(chunks)
    if sha256(payload).hexdigest() != expected_sha:
        raise ValidationError('Symmetric fitting policy SHA-256 differs')
    def unique(rows):
        result = {}
        for key, value in rows:
            if key in result: raise ValueError('Duplicate symmetric fitting field')
            result[key] = value
        return result
    def nonfinite(_value): raise ValueError('Nonfinite symmetric fitting number')
    try: data = json.loads(payload, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Invalid symmetric fitting JSON') from error
    cancel_check()
    return read_symmetric_plan(data, bindings, baseline, profile, parents, base, cancel_check=cancel_check)


def read_symmetric_plan(data: dict, bindings: dict, baseline: dict, profile: dict,
                        parents: dict[str, str | None], base: ContactFit,
                        *, cancel_check: Callable[[], None] = lambda: None) -> SymmetricFit:
    """Validate both complete anatomical branches and preserve active base frames."""
    try: return _read(data, bindings, baseline, profile, parents, base, cancel_check)
    except (KeyError, TypeError, IndexError, OverflowError, RecursionError) as error:
        raise ValidationError('Malformed symmetric fitting context or control structure') from error


def _read(data, bindings, baseline, profile, parents, base, cancel_check):
    required = {'schema_version', 'policy', 'bindings', 'coordinate_space', 'chains', 'fps', 'frames'}
    if (type(data) is not dict or set(data)-{'render_frames'} != required or
            type(data['schema_version']) is not int or data['schema_version'] != 1 or data['policy'] != POLICY or
            data['coordinate_space'] != 'BLENDER_WORLD_METERS' or type(bindings) is not dict or
            set(bindings) != BINDINGS or any(not is_sha256(v) for v in bindings.values()) or data['bindings'] != bindings):
        raise ValidationError('Symmetric fitting needs exact source, master, map, timeline and base-fit identities')
    if (profile.get('skin_deformation_policy') != 'BOUND_CORRECTIVE_SMOOTH_V1' or
            profile.get('mesh_strain_reference') != 'TRUE_NEUTRAL_BIND_V2'):
        raise ValidationError('Symmetric fitting requires independently verified neutral-reference skin')
    if (not isinstance(base, ContactFit) or base.policy not in (ARM_POLICY, HAND_POLICY, BODY_POLICY) or
            dict(base.bindings) != {k: bindings[k] for k in HASHES}):
        raise ValidationError('Symmetric fitting needs a verified legacy base with matching source identities')
    targets = tuple(p['target'] for p in profile['pairs'])
    if (not 1 <= len(targets) <= 64 or len(targets) != len(set(targets)) or targets != base.targets or
            targets != tuple(p['target'] for p in baseline['mapped_pairs'])):
        raise ValidationError('Symmetric fitting target order differs from its source or base')
    known = set(targets) | set(baseline['neutral_target_helpers'])
    if (type(parents) is not dict or set(parents) != known or len(known) > 256 or
            any(type(n) is not str or (p is not None and (type(p) is not str or p not in known)) for n, p in parents.items()) or
            sum(p is None for p in parents.values()) != 1):
        raise ValidationError('Symmetric fitting needs the complete actual target hierarchy')
    paths = {}
    for name in known:
        cancel_check(); path = []; current = name
        while current is not None:
            if current in path: raise ValidationError('Cyclic symmetric fitting hierarchy')
            path.append(current); current = parents[current]
        paths[name] = path
    count, fps = baseline['source_frame_count'], data['fps']
    if (type(count) is not int or not 5 <= count <= 2000 or not _number(fps) or not 1 <= fps <= 240 or
            fps != baseline['fps'] or fps != base.fps or len(base.offsets) != count or
            (base.hand_rotations and len(base.hand_rotations) != count) or
            type(data['frames']) is not list or len(data['frames']) != count):
        raise ValidationError('Symmetric fitting requires the complete original timeline and FPS')
    landmarks = baseline['target_anatomical_landmarks']
    points = [_vector(landmarks[k], 'anatomical landmarks') for k in ('head', 'left_foot', 'right_foot')]
    span = math.dist(points[0], tuple((points[1][j]+points[2][j])/2 for j in range(3)))
    if not .1 < span < 10: raise ValidationError('Invalid symmetric fitting anatomical body span')
    maximum = min(.08, span*.05)
    chains = data['chains']
    if type(chains) is not dict or set(chains) != {'left', 'right'}:
        raise ValidationError('Symmetric fitting needs both explicit anatomical chains')
    columns = {s: {k: [] for k in ('offset', 'clavicle', 'hand')} for s in ('left', 'right')}
    fields = {'frame'} | {s+'_'+k for s in columns for k in
                        ('offset_world', 'clavicle_rotation_world_degrees', 'hand_rotation_local_degrees')}
    active = []
    for frame, row in enumerate(data['frames'], 1):
        cancel_check()
        if type(row) is not dict or set(row) != fields or type(row['frame']) is not int or row['frame'] != frame:
            raise ValidationError('Symmetric fitting frames must be complete and ordered')
        for side in columns:
            for key, suffix in (('offset', 'offset_world'), ('clavicle', 'clavicle_rotation_world_degrees'),
                                ('hand', 'hand_rotation_local_degrees')):
                columns[side][key].append(_vector(row[side+'_'+suffix], suffix))
        changed = any(any(columns[s][k][-1]) for s in columns for k in columns[s])
        if changed and (any(base.offsets[frame-1]) or (base.hand_rotations and any(base.hand_rotations[frame-1]))):
            raise ValidationError('SYMMETRIC_BASE_ACTIVITY_OVERLAP; verified base correction retained')
        active.append(changed)
    meaningful = False
    for side in columns:
        for key, values in columns[side].items():
            _trajectory(values, fps, maximum if key == 'offset' else 15., key != 'offset')
            meaningful |= any(math.hypot(*v) > (1e-7 if key == 'offset' else 1e-6) for v in values)
    if not meaningful: raise ValidationError('Symmetric fitting needs a measurable correction')
    sides = {}
    for side in columns:
        chain = chains[side]
        if (type(chain) is not dict or set(chain) != {'clavicle', 'upper_arm', 'forearm', 'hand'} or
                any(type(n) is not str or n not in targets for n in chain.values()) or len(set(chain.values())) != 4 or
                targets[0] in chain.values() or chain['hand'] != profile['landmarks'][side+'_hand']['target'] or
                [n for n in paths[chain['hand']][1:] if n in targets][:3] !=
                [chain['forearm'], chain['upper_arm'], chain['clavicle']]):
            raise ValidationError('Symmetric fitting chain crosses its declared mapped hand hierarchy')
        descendants = tuple(n for n in targets if chain['hand'] in paths[n])
        branch = tuple(n for n in targets if chain['clavicle'] in paths[n])
        if set(branch) != {chain['clavicle'], chain['upper_arm'], chain['forearm'], *descendants}:
            raise ValidationError('Symmetric fitting would change an undeclared mapped shoulder descendant')
        hand = tuple(columns[side]['hand']) if any(any(v) for v in columns[side]['hand']) else ()
        arm = ContactFit(tuple(sorted((k, bindings[k]) for k in HASHES)), targets,
                         (chain['upper_arm'], chain['forearm'], chain['hand']), descendants,
                         tuple(columns[side]['offset']), float(fps), maximum, (), POLICY, hand)
        sides[side] = ShoulderFit(arm, chain['clavicle'], branch, tuple(columns[side]['clavicle']))
    if set(sides['left'].branch) & set(sides['right'].branch):
        raise ValidationError('Symmetric fitting shoulder branches overlap')
    samples = data.get('render_frames', [])
    if 'render_frames' in data and (type(samples) is not list or len(samples) != 5 or
            any(type(f) is not int or not 1 <= f <= count for f in samples) or samples != sorted(set(samples)) or
            not any(active[f-1] for f in samples)):
        raise ValidationError('Symmetric fitting needs five ordered render frames including a correction')
    return SymmetricFit(tuple(sorted(bindings.items())), sides['left'], sides['right'], base, tuple(active), tuple(samples))
