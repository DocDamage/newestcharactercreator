"""Bounded, explicit target fitting of an already verified native FK preview.

This policy changes the declared target arm; it is not source FK or contact
approval. Blender and the application must verify that distinction separately.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path

from ucc.core.errors import ValidationError
from .source_rest_frames import is_sha256
from . import native_math as nm
from .hand_fit import POLICY as HAND_POLICY,read_rotations,orient_hand

POLICY = "BOUNDED_NATIVE_ARM_IK_V1"
BODY_POLICY = "BOUNDED_NATIVE_BODY_SHAPE_IK_V3"
BODY_MAX_OFFSET_METERS = .08
BODY_MAX_SPAN_RATIO = .05
HASHES = {"source_sha256", "snapshot_sha256", "mapping_sha256", "master_sha256",
          "review_sha256", "timeline_sha256"}
MAX_OFFSET_METERS = .03
MAX_BODY_SPAN_RATIO = .02
MAX_SPEED_METERS_S = .3
MAX_ACCELERATION_METERS_S2 = 5.
MAX_ROTATION_DEGREES = 15.
MAX_ANGULAR_SPEED_DEGREES_S = 90.
MAX_ANGULAR_ACCELERATION_DEGREES_S2 = 900.
MAX_FIT_BYTES = 512*1024


def _number(v):
    return type(v) in (int, float) and -1e6 <= v <= 1e6 and math.isfinite(v)


def _vector(v):
    if type(v) is not list or len(v) != 3 or any(not _number(x) for x in v):
        raise ValidationError("Contact fitting needs finite three-component world offsets")
    return tuple(float(x) for x in v)


def _sub(a, b): return tuple(x-y for x, y in zip(a, b))
def _add(a, b): return tuple(x+y for x, y in zip(a, b))
def _mul(a, s): return tuple(x*s for x in a)
def _dot(a, b): return sum(x*y for x, y in zip(a, b))
def _length(a): return math.sqrt(_dot(a, a))


def _unit(a):
    size = _length(a)
    if not 1e-8 < size < 1e6:
        raise ValidationError("Degenerate contact-fitting limb direction")
    return _mul(a, 1/size)


def _checked_pose(matrix):
    if type(matrix) is not list or len(matrix) != 16 or any(not _number(v) for v in matrix):
        raise ValidationError("Invalid contact-fitting target matrix")
    nm.rotation(matrix, target_noise=True)


@dataclass(frozen=True, slots=True)
class ContactFit:
    bindings: tuple[tuple[str, str], ...]
    targets: tuple[str, ...]
    chain: tuple[str, str, str]
    hand_descendants: tuple[str, ...]
    offsets: tuple[tuple[float, float, float], ...]
    fps: float
    maximum_offset: float
    render_frames: tuple[int, ...] = ()
    policy: str = POLICY
    hand_rotations: tuple[tuple[float,float,float], ...] = ()


def read_contact_fit(path: Path, expected_sha: str, bindings: dict, baseline: dict, profile: dict,
                     parents: dict[str, str | None], *, cancel_check=lambda: None) -> ContactFit:
    """Read a bounded regular policy file; never trust an unhashed offset edit."""
    cancel_check()
    if (not is_sha256(expected_sha) or path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= MAX_FIT_BYTES):
        raise ValidationError("Contact fitting requires a bounded SHA-bound regular policy file")
    chunks = []; size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(min(16384, MAX_FIT_BYTES+1-size)):
            cancel_check(); chunks.append(chunk); size += len(chunk)
            if size > MAX_FIT_BYTES: raise ValidationError("Contact-fitting policy grew beyond its size bound")
    payload = b"".join(chunks)
    if sha256(payload).hexdigest() != expected_sha:
        raise ValidationError("Contact-fitting policy SHA-256 differs")
    def unique(rows):
        result = {}
        for key, value in rows:
            if key in result: raise ValueError("Duplicate contact-fitting field")
            result[key] = value
        return result
    def nonfinite(_value): raise ValueError("Nonfinite contact-fitting value")
    try: data = json.loads(payload, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("Invalid contact-fitting JSON") from error
    cancel_check()
    return read_fit_plan(data, bindings, baseline, profile, parents)


def read_fit_plan(data: dict, bindings: dict, baseline: dict, profile: dict,
                  parents: dict[str, str | None]) -> ContactFit:
    """Validate complete SHA-bound trajectories against the actual target tree.

    Callers must already have validated the baseline/profile and independently
    measured the supplied parent tree from the original and saved character.
    """
    fields = {"schema_version", "policy", "bindings", "coordinate_space", "chain", "fps", "frames"}
    if (type(data) is not dict or set(data)-{"render_frames"} != fields or type(data["schema_version"]) is not int or
            data["schema_version"] != 1 or type(data['policy']) is not str or data["policy"] not in (POLICY,HAND_POLICY,BODY_POLICY) or
            data["coordinate_space"] != "BLENDER_WORLD_METERS" or
            type(bindings) is not dict or set(bindings) != HASHES or
            any(not is_sha256(v) for v in bindings.values()) or data["bindings"] != bindings):
        raise ValidationError("Contact fitting needs the exact source/master/map/review/timeline identities")
    if (profile.get("skin_deformation_policy") != "BOUND_CORRECTIVE_SMOOTH_V1" or
            profile.get("mesh_strain_reference") != "TRUE_NEUTRAL_BIND_V2"):
        raise ValidationError("Contact fitting requires the independently reopened neutral-reference skin policy")
    targets = tuple(p["target"] for p in profile["pairs"])
    helpers = baseline["neutral_target_helpers"]
    known = set(targets) | set(helpers)
    if (type(parents) is not dict or set(parents) != known or len(known) > 256 or
            any(type(n) is not str or (p is not None and (type(p) is not str or p not in known)) for n, p in parents.items()) or
            sum(p is None for p in parents.values()) != 1):
        raise ValidationError("Contact fitting needs the complete actual target parent tree")
    paths = {}
    for name in known:
        path = []; current = name
        while current is not None:
            if current in path: raise ValidationError("Cyclic contact-fitting parent tree")
            path.append(current); current = parents[current]
        paths[name] = path
    chain = data["chain"]
    if (type(chain) is not dict or set(chain) != {"side", "upper_arm", "forearm", "hand"} or
            type(chain["side"]) is not str or chain["side"] not in {"left", "right"} or
            any(type(chain[k]) is not str or chain[k] not in targets for k in ("upper_arm", "forearm", "hand"))):
        raise ValidationError("Contact fitting needs one explicit mapped arm and anatomical hand")
    upper, lower, hand = (chain[k] for k in ("upper_arm", "forearm", "hand"))
    if (len({upper, lower, hand}) != 3 or targets[0] in {upper, lower, hand} or
            hand != profile["landmarks"][chain["side"]+"_hand"]["target"] or
            [n for n in paths[hand][1:] if n in targets][:2] != [lower, upper]):
        raise ValidationError("Contact-fitting arm must follow the declared hand's mapped anatomical hierarchy")
    fps = data["fps"]; count = baseline["source_frame_count"]
    if (not _number(fps) or not 1 <= fps <= 240 or fps != baseline["fps"] or
            type(count) is not int or not 3 <= count <= 2000 or type(data["frames"]) is not list or len(data["frames"]) != count):
        raise ValidationError("Contact fitting requires the complete source timeline and original frame rate")
    if data['policy'] in (HAND_POLICY,BODY_POLICY) and count<5:
        raise ValidationError('Hand fitting requires at least five complete source frames')
    points = baseline["target_anatomical_landmarks"]
    # Hip-to-head height is the orientation reference, not standing body span.
    # Bound fitting by the measured head/foot landmarks as well as meters.
    feet = tuple((points["left_foot"][i]+points["right_foot"][i])/2 for i in range(3))
    span = math.dist(points["head"], feet)
    if not .1 < span < 10: raise ValidationError("Invalid contact-fitting anatomical body span")
    maximum = (min(BODY_MAX_OFFSET_METERS,span*BODY_MAX_SPAN_RATIO) if data['policy']==BODY_POLICY else
               min(MAX_OFFSET_METERS,span*MAX_BODY_SPAN_RATIO))
    hand_policy=data['policy'] in (HAND_POLICY,BODY_POLICY)
    offsets = []
    for frame, row in enumerate(data["frames"], 1):
        if type(row) is not dict or set(row) != ({"frame", "offset_world"}|({'hand_rotation_local_degrees'} if hand_policy else set())) or type(row["frame"]) is not int or row["frame"] != frame:
            raise ValidationError("Contact-fitting frames must be complete and sequential")
        offset = _vector(row["offset_world"])
        if _length(offset) > maximum+1e-12:
            raise ValidationError("Contact fitting exceeds its fixed displacement bound")
        offsets.append(offset)
    if offsets[0] != (0., 0., 0.) or offsets[-1] != (0., 0., 0.) or not any(_length(v) > 1e-7 for v in offsets):
        raise ValidationError("Contact fitting needs a nonzero trajectory with unchanged clip endpoints")
    velocities = [(0., 0., 0.)] + [_mul(_sub(b, a), fps) for a, b in zip(offsets, offsets[1:])] + [(0., 0., 0.)]
    if any(_length(v) > MAX_SPEED_METERS_S+1e-9 for v in velocities):
        raise ValidationError("Contact fitting exceeds its fixed correction-speed bound")
    if any(_length(_sub(b, a))*fps > MAX_ACCELERATION_METERS_S2+1e-9 for a, b in zip(velocities, velocities[1:])):
        raise ValidationError("Contact fitting exceeds its fixed correction-acceleration bound")
    descendants = tuple(n for n in targets if hand in paths[n])
    samples = data.get("render_frames", [])
    if "render_frames" in data and (type(samples) is not list or len(samples) != 5 or
            any(type(f) is not int or not 1 <= f <= count for f in samples) or samples != sorted(set(samples))):
        raise ValidationError("Contact fitting needs five explicit ordered render frames")
    if samples and not any(_length(offsets[f-1])>1e-7 for f in samples):
        raise ValidationError("Fitting render samples must include an actual target correction")
    return ContactFit(tuple(sorted(bindings.items())), targets, (upper, lower, hand), descendants,
                      tuple(offsets), float(fps), maximum, tuple(samples),data['policy'],
                      read_rotations(data['frames'],fps) if hand_policy else ())


def _between(a, b):
    a, b = _unit(a), _unit(b)
    cosine = max(-1., min(1., _dot(a, b)))
    if cosine < -1+1e-8: raise ValidationError("Ambiguous contact-fitting half turn")
    v = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    x, y, z = v
    cross = [[0., -z, y], [z, 0., -x], [-y, x, 0.]]
    squared = nm.product(cross, cross)
    rotation = [[float(i == j)+cross[i][j]+squared[i][j]/(1+cosine) for j in range(3)] for i in range(3)]
    if math.degrees(math.acos(cosine)) > MAX_ROTATION_DEGREES+1e-9:
        raise ValidationError("Contact fitting exceeds its fixed angular correction bound")
    return rotation


def _fit_arm_frame(plan: ContactFit, poses: list[list[float]], frame: int) -> list[list[float]]:
    """Independent analytic two-bone solve; retain hand orientation and elbow pole."""
    if type(frame) is not int or not 1 <= frame <= len(plan.offsets) or type(poses) is not list or len(poses) != len(plan.targets):
        raise ValidationError("Contact-fitting pose coverage differs")
    for matrix in poses: _checked_pose(matrix)
    result = [list(m) for m in poses]
    offset = plan.offsets[frame-1]
    if offset == (0., 0., 0.): return result
    indices = {n: i for i, n in enumerate(plan.targets)}
    u, l, h = (indices[n] for n in plan.chain)
    shoulder, elbow, wrist = (tuple(poses[i][j*4+3] for j in range(3)) for i in (u, l, h))
    first, second = _sub(elbow, shoulder), _sub(wrist, elbow)
    a, b = _length(first), _length(second)
    target = _add(wrist, offset); direction = _sub(target, shoulder); distance = _length(direction)
    if min(a, b) < 1e-5 or not abs(a-b)+1e-7 < distance < a+b-1e-7:
        raise ValidationError("Contact-fitting endpoint is unreachable; no length scaling or clamping")
    axis = _unit(direction)
    pole = _sub(first, _mul(axis, _dot(first, axis)))
    if _length(pole) < min(a, b)*1e-4:
        raise ValidationError("Contact fitting cannot infer the elbow pole from a straight arm")
    along = (a*a+distance*distance-b*b)/(2*distance)
    height = math.sqrt(max(0., a*a-along*along))
    new_elbow = _add(shoulder, _add(_mul(axis, along), _mul(_unit(pole), height)))
    if _length(_sub(new_elbow, elbow)) > plan.maximum_offset+1e-9:
        raise ValidationError("Contact-fitting elbow exceeds the displacement bound")
    for i, old_direction, new_direction, head in ((u, first, _sub(new_elbow, shoulder), shoulder),
                                                 (l, second, _sub(target, new_elbow), new_elbow)):
        rotate = _between(old_direction, new_direction)
        old = [[poses[i][r*4+c] for c in range(3)] for r in range(3)]
        rotation = nm.product(rotate, old)
        for r in range(3):
            result[i][r*4:r*4+3] = rotation[r]
            result[i][r*4+3] = head[r]
    for name in plan.hand_descendants:
        i = indices[name]
        for r in range(3): result[i][r*4+3] += offset[r]
    return result


def fit_frame(plan: ContactFit, poses: list[list[float]], frame: int) -> list[list[float]]:
    """Apply explicit arm fitting and optional V2 hand-frame orientation."""
    result=_fit_arm_frame(plan,poses,frame)
    return orient_hand(plan,result,frame) if plan.hand_rotations else result


def verify_fitted_frame(plan: ContactFit, original: list, actual: list, frame: int) -> None:
    expected = fit_frame(plan, original, frame)
    if type(actual) is not list or len(actual) != len(expected):
        raise ValidationError("Incomplete fitted target pose evidence")
    for wanted, measured in zip(expected, actual):
        _checked_pose(measured)
        if any(abs(a-b) > (1e-5 if i % 4 == 3 else 1e-4) for i, (a, b) in enumerate(zip(wanted, measured))):
            raise ValidationError("Actual fitted target does not implement its explicit bounded IK trajectory")


def _rotation_vector(rotation):
    angle = math.acos(max(-1., min(1., (sum(rotation[i][i] for i in range(3))-1)/2)))
    antisymmetric = (rotation[2][1]-rotation[1][2], rotation[0][2]-rotation[2][0], rotation[1][0]-rotation[0][1])
    factor = .5 if angle < 1e-7 else angle/(2*math.sin(angle))
    return _mul(antisymmetric, factor*180/math.pi)


def verify_fitted_sequence(plan: ContactFit, originals: list, actuals: list) -> dict:
    """Reject pole-induced correction jumps even when target offsets are smooth.

    Measure the additional target rotation, separating it from the original
    source-driven rotation. Existing complete joint/skin checks remain required.
    """
    count = len(plan.offsets)
    if type(originals) is not list or type(actuals) is not list or len(originals) != count or len(actuals) != count:
        raise ValidationError("Contact-fitting angular audit needs the complete original and fitted sequences")
    indices = [plan.targets.index(n) for n in (plan.chain if plan.hand_rotations else plan.chain[:2])]
    previous = {}; previous_velocity = {i:(0., 0., 0.) for i in indices}
    maximum_speed = maximum_acceleration = 0.
    for frame, (original, actual) in enumerate(zip(originals, actuals), 1):
        verify_fitted_frame(plan, original, actual, frame)
        expected = fit_frame(plan, original, frame)
        for i in indices:
            old, _ = nm.rotation(original[i], target_noise=True)
            new, _ = nm.rotation(expected[i], target_noise=True)
            correction = nm.product(new, nm.transposed(old))
            velocity = ((0., 0., 0.) if frame == 1 else
                        _mul(_rotation_vector(nm.product(correction, nm.transposed(previous[i]))), plan.fps))
            speed = _length(velocity)
            acceleration = _length(_sub(velocity, previous_velocity[i]))*plan.fps
            if speed > MAX_ANGULAR_SPEED_DEGREES_S+1e-6 or acceleration > MAX_ANGULAR_ACCELERATION_DEGREES_S2+1e-6:
                raise ValidationError("Contact-fitting correction has a discontinuous angular velocity or acceleration")
            maximum_speed = max(maximum_speed, speed)
            maximum_acceleration = max(maximum_acceleration, acceleration)
            previous[i], previous_velocity[i] = correction, velocity
    # The clip's declared unchanged endpoint also returns correction velocity to zero.
    end_acceleration = max(_length(v)*plan.fps for v in previous_velocity.values())
    if end_acceleration > MAX_ANGULAR_ACCELERATION_DEGREES_S2+1e-6:
        raise ValidationError("Contact-fitting correction ends with discontinuous angular velocity")
    return {"frames":count, "max_correction_angular_speed_degrees_s":maximum_speed,
            "max_correction_angular_acceleration_degrees_s2":max(maximum_acceleration, end_acceleration)}
