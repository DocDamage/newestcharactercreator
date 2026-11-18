"""Measure and solve the original walk's parent-relative MPFB pose channels."""

import math
from dataclasses import dataclass
from typing import Any

from blender_bridge.face_geometry import evaluated
from blender_bridge.idle_authoring_math import sign_continuous
from blender_bridge.idle_authoring_policy import require
from blender_bridge.idle_authoring_scene import matrix, solve_baseline
from blender_bridge import walk_authoring_phase as phase_model
from ucc.core.authored_idle import baseline_spec

COUNTER_SWING_DEGREES = 4.
MPFB_VERTICES = (19158, 13380)
POSE_EPSILON = 1e-6
Z = (0., 0., 1.)
Vector3 = tuple[float, float, float]
Quaternion4 = tuple[float, float, float, float]
PoseSample = tuple[Vector3, tuple[Quaternion4, ...]]
SIDES = ('L', 'R')


@dataclass(frozen=True)
class WalkPoseBake:
    """The in-memory motion, its neutral armature state and measured evidence."""

    neutral_world: Any
    neutral_location: Vector3
    samples: list[PoseSample]
    observations: list[dict[str, Any]]
    virtual_seam: dict[str, float]


class _RelaxedArmBaseline:
    """Use the idle arm fitting's neutral geometry recipe without an idle Action."""

    @staticmethod
    def to_dict():
        return {'baseline': baseline_spec()}


def dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b, strict=True))


def difference(a, b):
    return tuple(x-y for x, y in zip(a, b, strict=True))


def unit(value):
    size = math.hypot(*value)
    if not math.isfinite(size) or size == 0:
        raise ValueError('DEGENERATE_DIRECTION')
    return tuple(x/size for x in value)


def perpendicular(value, axis):
    along = dot(value, axis)
    return tuple(x-along*y for x, y in zip(value, axis, strict=True))


def knee_solution(hip, ankle, thigh, shin, neutral_pole):
    """Intersect the two measured joint spheres using the neutral bend branch."""
    line = difference(ankle, hip)
    reach = math.hypot(*line)
    margin = min(reach-abs(thigh-shin), thigh+shin-reach)
    if not math.isfinite(margin) or margin <= 0:
        return None, margin
    direction = unit(line)
    pole = unit(perpendicular(neutral_pole, direction))
    center = (thigh*thigh-shin*shin+reach*reach)/(2*reach)
    radius = math.sqrt(max(0, thigh*thigh-center*center))
    knee = tuple(h+center*d+radius*p for h, d, p in zip(hip, direction, pole, strict=True))
    return knee, margin


def leg_rest(frame: dict) -> dict:
    """Bind the measured bilateral leg chains, including the neutral helpers."""
    records = {row['name']: row for row in frame['anatomy']['bones']}
    rest = {}
    for side in SIDES:
        chain = tuple(name+'.'+side for name in ('pelvis', 'upperleg01', 'upperleg02',
                                                 'lowerleg01', 'lowerleg02', 'foot', 'toe3-1'))
        if tuple(records[name]['parent'] for name in chain[1:]) != chain[:-1]:
            raise ValueError('MEASURED_MPFB_HELPER_CHAIN_MISMATCH')
        _, thigh, _, shin, _, foot, _ = chain
        h, k, a = (tuple(records[name]['head_world']) for name in (thigh, shin, foot))
        pole = unit(perpendicular(difference(k, h), unit(difference(a, h))))
        rest[side] = dict(hip=h, knee=k, ankle=a, thigh=math.dist(h, k), shin=math.dist(k, a),
                          pole=pole, chain=chain, records=records)
    return rest


def world_pose(rig, name):
    return rig.matrix_world @ rig.pose.bones[name].matrix


def rotation_for(pose_bone, rig, rotation):
    """Place a measured world rotation while preserving its actual parent-relative pivot."""
    from mathutils import Matrix

    bone = pose_bone.bone
    parent = pose_bone.parent
    parent_args = dict(parent_matrix=parent.matrix,
                       parent_matrix_local=parent.bone.matrix_local) if parent else {}
    natural = rig.matrix_world @ bone.convert_local_to_pose(Matrix.Identity(4), bone.matrix_local, **parent_args)
    target = rotation(natural).to_matrix().to_4x4()
    target.translation = natural.translation
    local = bone.convert_local_to_pose(rig.matrix_world.inverted() @ target,
                                      bone.matrix_local, invert=True, **parent_args)
    if local.to_translation().length >= 1e-5 or max(abs(value-1) for value in local.to_scale()) >= 1e-4:
        raise ValueError('LEG_SOLVE_REQUIRES_UNDECLARED_LOCAL_TRANSLATION_OR_SCALE')
    pose_bone.rotation_quaternion = local.to_quaternion().normalized()


def aim(rig, record, rest_start, rest_end, goal):
    from mathutils import Vector

    rest_rotation = matrix(record['rest_world']).to_quaternion()
    rest_direction = rest_rotation.inverted() @ Vector(unit(difference(rest_end, rest_start)))

    def desired(world):
        natural_rotation = world.to_quaternion()
        target_direction = (Vector(goal)-world.translation).normalized()
        return (natural_rotation @ rest_direction).rotation_difference(target_direction) @ natural_rotation

    rotation_for(rig.pose.bones[record['name']], rig, desired)


def pose_leg(bpy, rig, data, knee, ankle):
    names = data['chain']
    thigh, shin, foot = (data['records'][names[i]] for i in (1, 3, 5))
    aim(rig, thigh, data['hip'], data['knee'], knee)
    bpy.context.view_layer.update()
    aim(rig, shin, data['knee'], data['ankle'], ankle)
    bpy.context.view_layer.update()
    neutral_rotation = matrix(foot['rest_world']).to_quaternion()
    rotation_for(rig.pose.bones[foot['name']], rig, lambda _world: neutral_rotation)
    bpy.context.view_layer.update()
    actual = [world_pose(rig, row['name']) for row in (thigh, shin, foot)]
    v1 = unit(difference(actual[0].translation, actual[1].translation))
    v2 = unit(difference(actual[2].translation, actual[1].translation))
    flexion = 180-math.degrees(math.acos(max(-1, min(1, dot(v1, v2)))))
    rotation_agreement = abs(dot(actual[2].to_quaternion(), neutral_rotation))
    return {'knee_target_residual_m': math.dist(actual[1].translation, knee),
            'ankle_target_residual_m': math.dist(actual[2].translation, ankle),
            'knee_flexion_degrees': flexion,
            'flat_foot_rotation_residual_degrees': 2*math.degrees(math.acos(min(1, rotation_agreement)))}


def foot_regions(human, frame: dict, forward: Vector3) -> dict:
    """Combine exact neutral sole markers and the measured weighted foot envelope."""
    names = {group.index: group.name for group in human.vertex_groups}
    regions = {}
    for side in SIDES:
        patch = frame['sole_patches'][side]
        markers = tuple(patch['indices'])
        rest = tuple(tuple(point) for point in patch['neutral_world'])
        envelope = tuple(v.index for v in human.data.vertices if any(
            g.weight > .05 and names[g.group].endswith('.'+side)
            and names[g.group].startswith(('foot', 'toe')) for g in v.groups))
        if (len(markers) != len(rest) or len(markers) != len(set(markers)) or len(markers) < 3
                or not set(markers) <= set(envelope)):
            raise ValueError('EXACT_NEUTRAL_SOLE_TOPOLOGY_MISMATCH')
        along = [dot(point, forward) for point in rest]
        lo, hi = min(along), max(along)
        if hi <= lo:
            raise ValueError('NEUTRAL_SOLE_HAS_NO_FORWARD_SPAN')
        regions[side] = {
            'markers': markers, 'neutral': rest, 'envelope': envelope,
            'thirds': {name: tuple(i for i, value in enumerate(along) if classifier((value-lo)/(hi-lo)))
                       for name, classifier in (('rear', lambda u: u < .25),
                                                  ('mid', lambda u: .25 <= u < .75),
                                                  ('fore', lambda u: u >= .75))},
        }
        if any(not members for members in regions[side]['thirds'].values()):
            raise ValueError('REAR_MID_FORE_SOLE_COVERAGE_REQUIRED')
    return regions


def horizontal_distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def contact(points, region: dict, phase: phase_model.FootSample, forward: Vector3,
            travel: float, floor: float, previous: dict, side: str) -> dict:
    """Observe anatomy-relative support with an unwrapped virtual travel anchor."""
    probes = [points[i] for i in region['markers']]
    envelope = [points[i][2]-floor for i in region['envelope']]
    result = {'stance': phase.is_stance, 'phase_index': phase.phase_index,
        'target_ankle_forward_m': phase.forward_m, 'target_ankle_lift_m': phase.lift_m,
        'sampled_sole_markers': len(probes), 'sampled_weighted_foot_vertices': len(envelope),
        'weighted_foot_minimum_height_m': min(envelope),
        'weighted_foot_penetration_m': max(0., -min(envelope)),
        'sole_lowest_height_m': min(p[2]-floor for p in probes),
        'sole_highest_height_m': max(p[2]-floor for p in probes),
        'anchor_max_horizontal_residual_m': None,
        'same_stance_sampled_drift_m': None, 'stance_height_max_neutral_residual_m': None,
        'rear_mid_fore_vertical_ranges_m': {}}
    for name, members in region['thirds'].items():
        bounds = [probes[i][2]-floor for i in members]
        result['rear_mid_fore_vertical_ranges_m'][name] = [min(bounds), max(bounds)]
    if phase.is_stance:
        world = [tuple(p[k]+travel*forward[k] for k in range(3)) for p in probes]
        expected = [tuple(p[k]+phase.stance_anchor_m*forward[k] for k in range(3)) for p in region['neutral']]
        result['anchor_max_horizontal_residual_m'] = max(horizontal_distance(a, b) for a, b in zip(world, expected))
        result['stance_height_max_neutral_residual_m'] = max(abs(a[2]-b[2]) for a, b in zip(world, expected))
        own_key = (side, phase.stance_anchor_m)
        if own_key in previous:
            result['same_stance_sampled_drift_m'] = max(horizontal_distance(a, b)
                                                       for a, b in zip(world, previous[own_key]))
        else:
            previous[own_key] = world
    return result


def solve_lower_pose(bpy, rig, helpers, rest: dict, forward: Vector3, bind_world,
                     authored: phase_model.WalkFrame) -> dict:
    """Reset to neutral and fit thigh, shin and flat foot at each measured pivot."""
    from mathutils import Vector

    require(authored.armature_world_z_m == phase_model.ARMATURE_WORLD_Z_M,
            'Walk requires the fixed world Z offset')
    world = bind_world.copy()
    world.translation += Vector((0., 0., authored.armature_world_z_m))
    rig.matrix_world = world
    for bone in rig.pose.bones:
        bone.rotation_mode = 'QUATERNION'
        bone.rotation_quaternion = (1., 0., 0., 0.)
        bone.location = (0., 0., 0.)
        bone.scale = (1., 1., 1.)
    bpy.context.view_layer.update()

    steps = {'L': authored.left, 'R': authored.right}
    feet = {}
    for side, foot in steps.items():
        data = rest[side]
        hip = tuple(world_pose(rig, data['chain'][1]).translation)
        ankle = tuple(p+foot.forward_m*d+foot.lift_m*u for p, d, u in zip(data['ankle'], forward, Z, strict=True))
        knee, margin = knee_solution(hip, ankle, data['thigh'], data['shin'], data['pole'])
        require(knee is not None, 'A walk ankle target exceeds the measured leg reach')
        feet[side] = (margin, knee, ankle)

    row = {'index': authored.index, 'time_s': authored.time_s,
           'virtual_ground_travel_m': authored.time_s*phase_model.GROUND_SPEED_M_S, 'feet': {}}
    for side, (margin, knee, ankle) in feet.items():
        row['feet'][side] = {'reachable': True, 'triangle_inequality_margin_m': margin,
                             **pose_leg(bpy, rig, rest[side], knee, ankle)}
    actual = rig.matrix_world
    row['maximum_armature_world_matrix_residual'] = max(abs(actual[i][j]-world[i][j])
                                                         for i in range(4) for j in range(4))
    row['measured_armature_world_z_offset_m'] = actual.translation.z-bind_world.translation.z
    row['maximum_local_translation_m'] = max(b.location.length for b in rig.pose.bones)
    row['maximum_local_scale_delta'] = max(abs(v-1) for b in rig.pose.bones for v in b.scale)
    row['maximum_neutral_helper_quaternion_delta'] = max(abs(1-abs(b.rotation_quaternion.w))
                                                          for b in helpers)
    return row


def world_matrix(rig, name):
    return tuple(v for row in (rig.matrix_world @ rig.pose.bones[name].matrix) for v in row)


def matrix_residual(a, b) -> float:
    return max(abs(x-y) for x, y in zip(a, b, strict=True))


def periodic_counter_swing(index, stride_frames):
    return COUNTER_SWING_DEGREES*math.cos(math.tau*(index % stride_frames)/stride_frames)


def apply_arms(bpy, rig, neutral_upper_bases, right, swing):
    from mathutils import Quaternion

    for name, value in neutral_upper_bases.items():
        rig.pose.bones[name].rotation_quaternion = value
    bpy.context.view_layer.update()
    observed = {}
    for side, angle in (('L', -swing), ('R', swing)):
        name = 'upperarm01.'+side
        original = world_pose(rig, name).to_quaternion().normalized()
        target = Quaternion(right, math.radians(angle)) @ original
        rotation_for(rig.pose.bones[name], rig, lambda _world: target)
        bpy.context.view_layer.update()
        actual = world_pose(rig, name).to_quaternion().normalized()
        delta = (actual @ original.inverted()).normalized()
        if delta.w < 0:
            delta.negate()
        axis_projection = dot((delta.x, delta.y, delta.z), right)
        measured = math.degrees(2*math.atan2(axis_projection, delta.w))
        observed[side] = {'target_degrees': angle, 'measured_degrees': measured,
                          'difference_degrees': abs(measured-angle)}
    return observed


def joint_scope(rig, lower):
    names = {'root'}
    for leg in lower.values():
        bone = rig.pose.bones[leg['chain'][0]]
        while bone is not None:
            names.add(bone.name)
            bone = bone.parent
        names.update(leg['chain'])
    return tuple(sorted(names))


def observe_pose(bpy, human, record, full_points, regions, forward, floor, phase, post_holders):
    complete = evaluated(bpy, human, full=True)
    visible = evaluated(bpy, human)
    require((len(complete), len(visible)) == MPFB_VERTICES, 'WALK_EVALUATED_FULL_AND_VISIBLE_TOPOLOGY_COUNT')
    record['evaluated_full_vertices'] = len(complete)
    record['evaluated_visible_vertices'] = len(visible)
    record['whole_evaluated_skin_lowest_height_m'] = min(p[2]-floor for p in complete)
    record['visible_evaluated_skin_lowest_height_m'] = min(p[2]-floor for p in visible)
    for side, foot in (('L', phase.left), ('R', phase.right)):
        region = regions[side]
        movement = max(math.dist(full_points[i], complete[i]) for i in region['envelope'])
        record['feet'][side].update(contact(complete, region, foot, forward,
            record['virtual_ground_travel_m'], floor, post_holders, side))
        record['feet'][side]['upper_body_change_to_weighted_foot_m'] = movement
    return complete, visible


def capture_analytic(bpy, human, rig, frame) -> WalkPoseBake:
    from mathutils import Quaternion, Vector

    neutral_world = rig.matrix_world.copy()
    neutral_location = rig.location.copy()
    lower = leg_rest(frame)
    lower_names = joint_scope(rig, lower)
    forward = unit(perpendicular(tuple(frame['anatomy']['axes']['forward']), Z))
    require(dot(forward, (0., -1., 0.)) > .999999 and rig.parent is None,
         'WALK_MEASURED_NEGATIVE_Y_UNPARENTED_NEUTRAL_REQUIRED')
    right = Vector(frame['anatomy']['axes']['right']).normalized()
    regions = foot_regions(human, frame, forward)
    floor = min(point[2] for region in regions.values() for point in region['neutral'])
    lower_driven = {entry['chain'][index] for entry in lower.values() for index in (1, 3, 5)}
    helpers = [bone for bone in rig.pose.bones if bone.name not in lower_driven]
    # Use the existing measured neutral arm fitting, without evaluating any prior motion.
    baseline = solve_baseline(rig, frame, _RelaxedArmBaseline())['baseline_quaternions']
    upper = {name: Quaternion(value) for name, value in baseline.items() if any(value[1:])}
    require(bool(upper) and set(upper).isdisjoint(lower_names), 'RELAXED_BASELINE_DRIVES_ONLY_UPPER_BODY')
    stored, rows, first, last, previous = [], [], None, None, None
    post_holders = {}
    minimum_quaternion_dot = 1.
    for index in range(phase_model.STORED_FRAMES+1):
        phase = phase_model.sample_walk(index)
        row = solve_lower_pose(bpy, rig, helpers, lower, forward, neutral_world, phase)
        before_points = evaluated(bpy, human, full=True)
        require(len(before_points) == MPFB_VERTICES[0], 'Unsupported evaluated full walk topology')
        lower_before = {name: world_matrix(rig, name) for name in lower_names}
        swing = periodic_counter_swing(index, phase_model.STRIDE_FRAMES)
        row['upper_arm_counter_swing'] = apply_arms(bpy, rig, upper, right, swing)
        row['lower_chain_change_after_upper_body_max_matrix_component'] = max(
            matrix_residual(world_matrix(rig, name), prior) for name, prior in lower_before.items())
        require(row['lower_chain_change_after_upper_body_max_matrix_component'] <= POSE_EPSILON
             and all(bone.location.length == 0. and all(v == 1. for v in bone.scale) for bone in rig.pose.bones),
             'UPPER_WALK_SWING_CHANGED_LOWER_CHAIN_OR_POSE_CHANNEL_SCOPE')
        complete, visible = observe_pose(bpy, human, row, before_points, regions, forward, floor,
                                         phase, post_holders)
        location = tuple(rig.location)
        require(math.dist(location, (neutral_location.x, neutral_location.y, neutral_location.z+phase_model.ARMATURE_WORLD_Z_M)) <= POSE_EPSILON,
             'WALK_ARMATURE_TRANSLATION_IS_NOT_CONSTANT_WORLD_Z')
        poses = tuple(sign_continuous(bone.rotation_quaternion, None if previous is None else previous[i])
                      for i, bone in enumerate(rig.pose.bones))
        if previous is not None:
            minimum_quaternion_dot = min(minimum_quaternion_dot,
                min(dot(a, b) for a, b in zip(previous, poses, strict=True)))
        previous = poses
        if index < phase_model.STORED_FRAMES:
            stored.append((location, poses))
        if index == 0 or index == phase_model.STORED_FRAMES:
            witness = (complete, visible, tuple(world_matrix(rig, b.name) for b in rig.pose.bones))
            if index == 0:
                first = witness
            else:
                last = witness
        rows.append(row)
    require(first is not None and last is not None and len(stored) == phase_model.STORED_FRAMES,
            'Walk analytic virtual seam and stored samples must be complete')
    closure = {
        'maximum_full_skin_distance_m': max(math.dist(a, b) for a, b in zip(first[0], last[0], strict=True)),
        'maximum_visible_skin_distance_m': max(math.dist(a, b) for a, b in zip(first[1], last[1], strict=True)),
        'maximum_bone_world_matrix_component': max(matrix_residual(a, b) for a, b in zip(first[2], last[2], strict=True)),
        'minimum_adjacent_local_quaternion_dot': minimum_quaternion_dot,
    }
    require(all(closure[key] == 0. for key in ('maximum_full_skin_distance_m', 'maximum_visible_skin_distance_m',
                                           'maximum_bone_world_matrix_component')),
         'WALK_VIRTUAL_ENDPOINT_DOES_NOT_CLOSE_EXACTLY')
    return WalkPoseBake(neutral_world, tuple(neutral_location), stored, rows, closure)
