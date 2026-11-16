"""Production staging from an authoritative MPFB master and selected target Action."""
from array import array
import math
from pathlib import Path
from typing import Any

from blender_bridge.expression_clip_action import create_action, linear_weight
from blender_bridge.expression_policy import keyname
from blender_bridge.face_geometry import evaluated
from blender_bridge.face_policy import digest
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh
from blender_bridge.godot_outputs import export_glb, write_json, write_floats
from blender_bridge.godot_policy import POLICY, OUTPUTS, checked_inputs
from blender_bridge.godot_source import master_context, observe_source, attach_source_action, pose_values


def sample_error(points: list, source: array, frame: int) -> float:
    if len(points) != 13380:
        raise ValueError('Godot candidate changed complete visible source topology')
    offset = (frame-1)*13380*3
    result = max(math.dist(point, source[offset+i*3:offset+i*3+3]) for i, point in enumerate(points))
    if not math.isfinite(result) or result > 1e-6:
        raise ValueError('Godot candidate differs from the complete independent original source surface')
    return result


def bone_error(bpy: Any, rig: Any, human: Any, names: list[str], reference: array, frame: int) -> float:
    values = pose_values(rig, human, names)
    offset = (frame-1)*len(names)*16
    if len(reference) != 25*len(names)*16:
        raise ValueError('Godot source bone-world reference is incomplete')
    result = max(abs(value-reference[offset+i]) for i, value in enumerate(values))
    if not math.isfinite(result) or result > 1e-6:
        raise ValueError('Transferred source Action changed a family bone world transform')
    return result


def stage_candidate(bpy: Any, root: Path, job: dict) -> dict:
    recipe, clip = checked_inputs(root, job); options = job['options']
    if any((root/name).exists() or (root/name).is_symlink() for name in OUTPUTS):
        raise ValueError('Godot stage refuses to overwrite earlier private outputs')
    context = master_context(bpy, root, clip)
    action, positions, bones = observe_source(bpy, root, context)
    human, rig = attach_source_action(bpy, root, context, action, clip)
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    candidate = build_godot_bind_mesh(bpy, human, rig)
    converted = candidate.object
    if len(converted.data.uv_layers) != 1:
        raise ValueError('Godot source needs one original UV set; diagnostic UVs are not exported')
    bind = array('f', (value for vertex in converted.data.vertices
                      for value in (vertex.co.x, vertex.co.z, -vertex.co.y)))
    write_floats(root/'bind_positions.bin', bind)
    create_action(bpy, converted, context['values'])
    rows = []; maximum = 0.; bone_maximum = 0.
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        for (role, family), peak in context['values'].items():
            human.data.shape_keys.key_blocks[keyname(role, family)].value = linear_weight(peak, frame)
        bpy.context.view_layer.update()
        original_error = sample_error(evaluated(bpy, human), positions, frame)
        converted_error = sample_error(evaluated(bpy, converted), positions, frame)
        observed_bones = bone_error(bpy, rig, human, context['bone_names'], bones, frame)
        maximum = max(maximum, converted_error); bone_maximum = max(bone_maximum, observed_bones)
        rows.append({'frame': frame, 'master_source_error_m': original_error,
                     'converted_max_error_m': converted_error, 'bone_world_error': observed_bones})
    for role, family in context['values']:
        human.data.shape_keys.key_blocks[keyname(role, family)].value = 0.
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    exported = export_glb(bpy, root, converted, rig)
    write_floats(root/'source_positions.bin', positions); write_floats(root/'source_bones.bin', bones)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'source_review.blend'), check_existing=False)
    action_report = {'schema_version': 1, 'policy': POLICY, 'master_sha256': options['master_sha256'],
        'source_motion_sha256': options['target_motion_sha256'], 'export_recipe_sha256': options['export_recipe_sha256'],
        'static_master_sha256': context['static_sha256'], 'action': action,
        'bone_names': context['bone_names'], 'frames': rows,
        'positions_sha256': digest(root/'source_positions.bin'), 'bones_sha256': digest(root/'source_bones.bin')}
    write_json(root/'source_action.json', action_report)
    report = {**candidate.observation, **exported,
        'status': 'REAL_MPFB_SOURCE_ACTION_CANDIDATE_STAGED_NOT_ENGINE_VERIFIED',
        'producer_policy': POLICY, 'master_sha256': options['master_sha256'],
        'source_motion_sha256': options['target_motion_sha256'],
        'export_recipe_sha256': options['export_recipe_sha256'], 'clip_sha256': options['clip_sha256'],
        'blender_version': bpy.app.version_string, 'fps': 24, 'frames': 25,
        'positions_dtype': 'float32le', 'positions_sha256': digest(root/'source_positions.bin'),
        'positions_bytes': (root/'source_positions.bin').stat().st_size,
        'bind_positions_sha256': digest(root/'bind_positions.bin'),
        'source_bones_sha256': digest(root/'source_bones.bin'),
        'review_scene_sha256': digest(root/'source_review.blend'),
        'source_action_sha256': digest(root/'source_action.json'),
        'diagnostic_source_ids_in_UV2': False, 'shipping_animation_created': False,
        'bone_names': context['bone_names'],
        'expression_peaks': {keyname(role, family): value for (role, family), value in context['values'].items()},
        'max_preexport_source_difference_m': maximum, 'max_source_bone_world_error': bone_maximum,
        'visual_quality_approved': False, 'engine_import_verified': False}
    write_json(root/'blender_stage.json', report)
    checked_inputs(root, job)
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': options['master_sha256'],
            'source_motion_sha256': options['target_motion_sha256'],
            'export_recipe_sha256': options['export_recipe_sha256'],
            **{field: digest(root/name) for name, field in OUTPUTS.items()},
            'frame_count': 25, 'engine_import_verified': False, 'visual_quality_approved': False}
