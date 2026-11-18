"""Original anatomical idle math; no imported animation or bone-local Euler guesses."""
import math

from blender_bridge.idle_authoring_policy import finite_vector, require


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(value):
    value = finite_vector(value)
    length = math.sqrt(dot(value, value))
    require(length > 1e-8, 'Degenerate idle anatomical direction')
    return mul(value, 1 / length)


def body_axes(pelvis, neck, left_shoulder, right_shoulder):
    up = unit(sub(neck, pelvis))
    across = sub(right_shoulder, left_shoulder)
    right = unit(sub(across, mul(up, dot(across, up))))
    forward = unit(cross(up, right))
    require(abs(dot(right, up)) < 1e-8 and dot(cross(right, forward), up) > .999999,
            'Idle anatomical frame is ambiguous/reflected')
    return {'right': right, 'up': up, 'forward': forward}


def relaxed_directions(axes, side, baseline):
    require(side in ('L', 'R'), 'Unsupported anatomical side')
    outward = mul(axes['right'], -1 if side == 'L' else 1)
    drop = math.radians(baseline['upper_arm_drop_from_lateral_deg'])
    tilt = math.radians(baseline['upper_arm_forward_tilt_deg'])
    lateral_drop = sub(mul(outward, math.cos(drop)), mul(axes['up'], math.sin(drop)))
    upper = unit(add(mul(lateral_drop, math.cos(tilt)), mul(axes['forward'], math.sin(tilt))))
    flex = math.radians(baseline['elbow_forward_flex_deg'])
    bend_forward = unit(sub(axes['forward'], mul(upper, dot(axes['forward'], upper))))
    lower = unit(add(mul(upper, math.cos(flex)), mul(bend_forward, math.sin(flex))))
    medial = mul(outward, -1)
    hand = unit(sub(lower, mul(medial, dot(lower, medial))))
    return {'upper': upper, 'lower': lower, 'hand': hand, 'palm': medial}


def hand_anatomy(side, wrist, middle, index, little):
    require(side in ('L', 'R'), 'Unsupported hand side')
    direction = unit(sub(middle, wrist))
    across = unit(sub(index, little))
    require(sum(x*x for x in cross(across,direction)) > .25,
            'Ambiguous/near-parallel measured hand anatomy')
    # Public default-rig digit chirality; this is not skin-surface volar proof.
    normal = unit(mul(cross(direction, across), 1 if side == 'L' else -1))
    require(all(abs(dot(unit(sub(point,wrist)),normal)) < .4 for point in (index,little)),
            'Unsupported nonplanar measured hand anatomy')
    return {'direction': direction, 'normal': normal, 'flex_axis': unit(cross(direction, normal))}


def periodic_amplitudes(frame, periodic):
    require(type(frame) is int and 1 <= frame <= 301, 'Idle sample outside stored/virtual range')
    phase = 2 * math.pi * (frame - 1) / 300
    amplitude = math.sin(phase)
    return {'torso': math.radians(periodic['torso_forward_pitch_amplitude_deg']) * amplitude,
            'head': math.radians(periodic['head_counter_pitch_amplitude_deg']) * amplitude,
            'elbow': math.radians(periodic['bilateral_elbow_flex_amplitude_deg']) * amplitude}


def periodic_derivatives(frame, periodic):
    """Original analytic angular rates, per second; not a zero-velocity seam."""
    require(type(frame) is int and 1 <= frame <= 301, 'Idle derivative outside stored/virtual range')
    rate = 2 * math.pi / 10 * math.cos(2 * math.pi * (frame-1) / 300)
    return {'torso': math.radians(periodic['torso_forward_pitch_amplitude_deg'])*rate,
            'head': math.radians(periodic['head_counter_pitch_amplitude_deg'])*rate,
            'elbow': math.radians(periodic['bilateral_elbow_flex_amplitude_deg'])*rate}


def sign_continuous(quaternion, previous=None):
    values = tuple(float(x) for x in quaternion)
    require(len(values) == 4 and all(math.isfinite(x) for x in values), 'Nonfinite idle quaternion')
    length = math.sqrt(sum(x*x for x in values))
    require(length > 1e-8, 'Degenerate idle quaternion')
    values = tuple(x / length for x in values)
    return tuple(-x for x in values) if previous is not None and sum(a*b for a,b in zip(values,previous)) < 0 else values
