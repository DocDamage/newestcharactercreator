"""Fresh-process saved candidate verification; never rebuilds or repairs it."""
from array import array
from pathlib import Path
from typing import Any

from blender_bridge.expression_clip_action import ACTION_NAME, all_curves, linear_weight
from blender_bridge.expression_policy import keyname
from blender_bridge.face_geometry import evaluated
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest, read_json
from blender_bridge.godot_outputs import write_json
from blender_bridge.godot_policy import POLICY, OUTPUTS, checked_inputs
from blender_bridge.godot_source import master_context, observe_source, action_state, static_state, timeline
from blender_bridge.godot_workers import sample_error, bone_error


def check_face(candidate: Any, values: dict) -> None:
    keys = candidate.data.shape_keys
    animation = keys.animation_data if keys else None
    action = animation.action if animation else None
    if (action is None or action.name != ACTION_NAME or action.library
            or len(animation.drivers) or len(animation.nla_tracks)
            or animation.action_blend_type != 'REPLACE' or animation.action_influence != 1.
            or len(action.slots) != 1 or animation.action_slot != action.slots[0]
            or list(action.frame_range) != [1., 25.]):
        raise ValueError('Saved candidate lost its exact independent facial Action binding')
    expected = {keys.key_blocks[keyname(r, f)].path_from_id('value'): v for (r, f), v in values.items()}
    curves = all_curves(action)
    if (len(curves) != 12 or {curve.data_path for curve in curves} != set(expected)
            or any(c.array_index != 0 or c.mute or len(c.modifiers) or c.extrapolation != 'CONSTANT' for c in curves)):
        raise ValueError('Saved candidate facial channels differ')
    for curve in curves:
        if len(curve.keyframe_points) != 3 or any(
                point.interpolation != 'LINEAR' or list(point.co) != [float(frame), value]
                for point, frame, value in zip(curve.keyframe_points, (1, 13, 25), (0., expected[curve.data_path], 0.))):
            raise ValueError('Saved candidate facial keyframes differ')


def verify_candidate(bpy: Any, root: Path, job: dict) -> dict:
    _, clip = checked_inputs(root, job)
    destination = root/'blender_verification.json'
    if destination.exists() or destination.is_symlink():
        raise ValueError('Refuse to overwrite earlier saved-candidate verification')
    context = master_context(bpy, root, clip)
    action, positions, bones = observe_source(bpy, root, context)
    if (positions.tobytes() != (root/'source_positions.bin').read_bytes()
            or bones.tobytes() != (root/'source_bones.bin').read_bytes()):
        raise ValueError('Independent original source differs from staged surface/bone reference bytes')
    source_report = read_json(root/'source_action.json', job['options']['action_report_sha256'], 8*1024*1024)
    if (source_report.get('action') != action or source_report.get('static_master_sha256') != context['static_sha256']
            or source_report.get('source_motion_sha256') != job['options']['target_motion_sha256']):
        raise ValueError('Staged Action observation differs from independently reopened source')
    bpy.ops.wm.open_mainfile(filepath=str(root/'source_review.blend'), load_ui=False)
    timeline(bpy)
    human = bpy.data.objects.get(context['human_name']); rig = bpy.data.objects.get(context['rig_name'])
    candidate = bpy.data.objects.get('UCC_Godot_Private_Character')
    if (human is None or rig is None or candidate is None or candidate.type != 'MESH'
            or candidate.parent != rig or len(candidate.data.vertices) != 13380
            or len(candidate.data.uv_layers) != 1 or len(bpy.data.actions) != 2
            or bpy.context.scene.frame_current != 1 or bpy.context.scene.frame_subframe != 0.
            or state_digest(static_state(bpy, human, rig, context['targets'])) != context['static_sha256']
            or action_state(rig) != action):
        raise ValueError('Saved candidate changed the authoritative character, Action or neutral timeline')
    check_face(candidate, context['values'])
    bind = array('f', (v for vertex in candidate.data.vertices for v in (vertex.co.x, vertex.co.z, -vertex.co.y)))
    if bind.tobytes() != (root/'bind_positions.bin').read_bytes():
        raise ValueError('Reopened candidate bind mesh differs from staged reference bytes')
    rows = []; reopened = array('f'); maximum = 0.; bone_maximum = 0.
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        for (role, family), peak in context['values'].items():
            human.data.shape_keys.key_blocks[keyname(role, family)].value = linear_weight(peak, frame)
        bpy.context.view_layer.update()
        source = evaluated(bpy, human)
        original_error = sample_error(source, positions, frame)
        error = sample_error(evaluated(bpy, candidate), positions, frame)
        bone = bone_error(bpy, rig, human, context['bone_names'], bones, frame)
        reopened.extend(value for point in source for value in point)
        maximum = max(maximum, error); bone_maximum = max(bone_maximum, bone)
        rows.append({'frame': frame, 'master_source_error_m': original_error,
                     'converted_max_error_m': error, 'bone_world_error': bone})
    if reopened.tobytes() != positions.tobytes():
        raise ValueError('Fresh saved original source evaluation changed exact reference bytes')
    checked_inputs(root, job)
    result = {'status': 'FRESH_SAVED_COMBINED_ACTION_AND_FULL_SURFACE_VERIFIED',
        'producer_policy': POLICY, 'blender_version': bpy.app.version_string,
        'master_sha256': job['options']['master_sha256'],
        'source_motion_sha256': job['options']['target_motion_sha256'],
        'export_recipe_sha256': job['options']['export_recipe_sha256'],
        'bound_files': {name: digest(root/name) for name in OUTPUTS},
        'frames': rows, 'source_vertices': 13380, 'max_conversion_error_m': maximum,
        'max_source_bone_world_error': bone_maximum, 'independent_source_bytes_exact': True,
        'shipping_animation_created': False, 'engine_import_verified': False}
    write_json(destination, result)
    return {**result, 'verification_sha256': digest(destination)}
