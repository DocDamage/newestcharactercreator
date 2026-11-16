"""Read-only character/Action matching and complete target-source observations."""
from array import array
import math
from pathlib import Path
import re
from typing import Any

from blender_bridge.expression_clip_action import all_curves, linear_weight, peaks, source_intake
from blender_bridge.expression_existing import canonical_keys
from blender_bridge.expression_geometry import invariant_state
from blender_bridge.face_geometry import evaluated, key_state, mesh_coordinates, rest_state
from blender_bridge.face_operations import state_digest


def static_state(bpy: Any, human: Any, rig: Any, targets: Any) -> dict:
    state = invariant_state(bpy, human, rig, targets)
    keep = {'topology', 'weights', 'bone_controls', 'stack', 'macro', 'key_order', 'relative_keys',
            'uv_sha256', 'active_uv_index', 'polygon_material_smooth_sha256', 'materials'}
    return {'invariants': {key: state[key] for key in keep},
            'all_keys': {key.name: key_state(key) for key in human.data.shape_keys.key_blocks},
            'rest': rest_state(rig), 'mesh_coordinates': mesh_coordinates(human),
            'parent_inverse': [float(x) for row in human.matrix_parent_inverse for x in row],
            'human_local': [float(x) for row in human.matrix_basis for x in row],
            'rig_scale': list(rig.scale)}


def timeline(bpy: Any) -> None:
    scene = bpy.context.scene
    if (scene.render.fps != 24 or scene.render.fps_base != 1.
            or scene.frame_start != 1 or scene.frame_end != 25
            or scene.render.frame_map_old != 100 or scene.render.frame_map_new != 100
            or not math.isfinite(scene.unit_settings.scale_length)
            or scene.unit_settings.scale_length != 1.):
        raise ValueError('Godot source needs the exact supported 25-frame/24fps timeline and metre units')


def pose_values(rig: Any, human: Any, names: list[str]) -> list[float]:
    for obj in (human, rig):
        if any(not math.isfinite(float(value)) or value <= 0 for value in obj.scale):
            raise ValueError('Godot motion contains negative, zero or nonfinite object scale')
        matrix = obj.matrix_world.to_3x3()
        lengths = [column.length for column in matrix.col]
        if matrix.determinant() <= 0 or min(lengths) <= 0 or max(lengths)/min(lengths) > 1.0001:
            raise ValueError('Godot motion contains reflected or nonuniform world transforms')
        if any(abs(matrix.col[i].dot(matrix.col[j])) > 1e-4*lengths[i]*lengths[j]
               for i in range(3) for j in range(i)):
            raise ValueError('Godot motion contains sheared world transforms')
    values = []
    for name in names:
        bone = rig.pose.bones[name]
        if len(bone.constraints) or any(not math.isfinite(float(value)) or abs(value-1.) > 1e-6 for value in bone.scale):
            raise ValueError('Godot motion cannot reinterpret bone constraints or animated bone scale')
        values.extend(float(value) for row in (rig.matrix_world @ bone.matrix) for value in row)
    if any(not math.isfinite(value) for value in values):
        raise ValueError('Godot source has nonfinite bone world transforms')
    return values


def action_state(rig: Any) -> dict:
    animation = rig.animation_data
    action = animation.action if animation else None
    if (action is None or action.library is not None or len(animation.drivers) or len(animation.nla_tracks)
            or animation.action_blend_type != 'REPLACE' or animation.action_influence != 1.
            or len(action.slots) != 1 or animation.action_slot != action.slots[0]
            or list(action.frame_range) != [1., 25.]):
        raise ValueError('Godot source needs one complete bound target Action without blending, drivers or NLA')
    curves = all_curves(action)
    if not 1 <= len(curves) <= 2000:
        raise ValueError('Godot source Action has an unsupported channel count')
    rows = []; identities = set(); total_keys = 0
    components = {'location': 3, 'scale': 3, 'rotation_euler': 3,
                  'rotation_quaternion': 4, 'rotation_axis_angle': 4}
    modes = {'rotation_euler': {'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'},
             'rotation_quaternion': {'QUATERNION'}, 'rotation_axis_angle': {'AXIS_ANGLE'}}
    for curve in curves:
        path = curve.data_path; owner = rig; channel = path
        match = re.fullmatch(r'pose\.bones\["([^"\\]+)"\]\.(location|scale|rotation_euler|rotation_quaternion|rotation_axis_angle)', path)
        if match:
            if match[1] not in rig.pose.bones:
                raise ValueError('Godot Action references an unknown family bone')
            owner, channel = rig.pose.bones[match[1]], match[2]
        if (channel not in components or not 0 <= curve.array_index < components[channel]
                or (channel in modes and owner.rotation_mode not in modes[channel])
                or (path, curve.array_index) in identities or curve.mute or len(curve.modifiers)
                or curve.extrapolation not in {'CONSTANT', 'LINEAR'}):
            raise ValueError('Godot Action contains duplicate, incompatible or unsupported control channels')
        identities.add((path, curve.array_index))
        keys = []
        for key in curve.keyframe_points:
            values = [*key.co, *key.handle_left, *key.handle_right]
            if any(not math.isfinite(float(value)) for value in values) or not 1 <= key.co.x <= 25:
                raise ValueError('Godot Action has nonfinite or out-of-range keyframes')
            keys.append({'co': list(key.co), 'left': list(key.handle_left), 'right': list(key.handle_right),
                         'interpolation': key.interpolation, 'left_type': key.handle_left_type,
                         'right_type': key.handle_right_type, 'easing': key.easing,
                         'amplitude': key.amplitude, 'back': key.back, 'period': key.period})
        total_keys += len(keys)
        if not keys or total_keys > 1_000_000:
            raise ValueError('Godot Action keyframe data is empty or oversized')
        rows.append({'path': path, 'index': curve.array_index, 'extrapolation': curve.extrapolation,
                     'auto_smoothing': curve.auto_smoothing, 'keys': keys})
    return {'name': action.name, 'curves_sha256': state_digest(rows), 'channels': len(rows),
            'keyframes': total_keys, 'object_rotation_mode': rig.rotation_mode,
            'bone_rotation_modes': {bone.name: bone.rotation_mode for bone in rig.pose.bones}}


def master_context(bpy: Any, root: Path, clip: dict) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig, _, targets = source_intake(bpy)
    _, _, race, _ = canonical_keys(root, human, targets)
    if human.hide_render or human.hide_viewport:
        raise ValueError('Godot profile cannot silently change hidden master geometry')
    if bpy.context.scene.unit_settings.scale_length != 1.:
        raise ValueError('Godot authoritative master must use metre scene units')
    return {'human_name': human.name, 'rig_name': rig.name, 'targets': targets,
            'static_sha256': state_digest(static_state(bpy, human, rig, targets)),
            'bone_names': [bone.name for bone in rig.data.bones],
            'values': peaks(clip['parameters'], race)}


def observe_source(bpy: Any, root: Path, context: dict) -> tuple[dict, array, array]:
    bpy.ops.wm.open_mainfile(filepath=str(root/'target_motion.blend'), load_ui=False)
    timeline(bpy); bpy.context.scene.frame_set(1)
    human = bpy.data.objects.get(context['human_name']); rig = bpy.data.objects.get(context['rig_name'])
    if (human is None or rig is None or human.type != 'MESH' or rig.type != 'ARMATURE'
            or human.parent != rig or rig.parent is not None or human.data.users != 1 or rig.data.users != 1):
        raise ValueError('Target Action source does not have the authoritative character and family rig')
    for obj in (human, rig):
        if obj.library or obj.override_library or len(obj.constraints):
            raise ValueError('Godot Action source cannot contain linked, overridden or constrained character data')
    for data in (human, human.data, rig.data, human.data.shape_keys):
        if data.animation_data and (data.animation_data.action or data.animation_data.drivers or data.animation_data.nla_tracks):
            raise ValueError('Target source may supply the selected rig Action only; other animation needs separate admission')
    if rig.data.pose_position != 'POSE' or state_digest(static_state(bpy, human, rig, context['targets'])) != context['static_sha256']:
        raise ValueError('Target Action source changed authoritative geometry, bind pose, weights, shape states or static masks')
    action = action_state(rig)
    positions = array('f'); bones = array('f')
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        for (role, family), peak in context['values'].items():
            human.data.shape_keys.key_blocks['UCC_EXPR_V1_'+role+'_'+family].value = linear_weight(peak, frame)
        bpy.context.view_layer.update()
        points = evaluated(bpy, human)
        if len(points) != 13380:
            raise ValueError('Target Action changed the visible source topology')
        positions.extend(value for point in points for value in point)
        bones.extend(pose_values(rig, human, context['bone_names']))
    return action, positions, bones


def attach_source_action(bpy: Any, root: Path, context: dict, action: dict, clip: dict) -> tuple:
    fresh = master_context(bpy, root, clip)
    if fresh['static_sha256'] != context['static_sha256']:
        raise ValueError('Authoritative master changed while preparing Action transfer')
    rig = bpy.data.objects[context['rig_name']]; human = bpy.data.objects[context['human_name']]
    with bpy.data.libraries.load(str(root/'target_motion.blend'), link=False) as (source, destination):
        if action['name'] not in source.actions:
            raise ValueError('Selected actual source Action is missing')
        destination.actions = [action['name']]
    if len(destination.actions) != 1 or destination.actions[0] is None:
        raise ValueError('Selected actual source Action could not be appended')
    rig.rotation_mode = action['object_rotation_mode']
    for name, mode in action['bone_rotation_modes'].items(): rig.pose.bones[name].rotation_mode = mode
    rig.animation_data_create(); rig.animation_data.action = destination.actions[0]
    rig.animation_data.action_slot = destination.actions[0].slots[0]
    if action_state(rig) != action:
        raise ValueError('Appended Action differs from the independently observed source channels')
    return human, rig
