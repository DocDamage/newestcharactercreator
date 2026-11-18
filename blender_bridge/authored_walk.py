"""Author the fixed original MPFB walk in an owned Blender worker directory."""

import math
from pathlib import Path
from typing import Any

from blender_bridge.face_geometry import rest_state
from blender_bridge.face_operations import state_digest
from blender_bridge.idle_authoring_measure import check_frame, measure, values
from blender_bridge.idle_authoring_policy import (
    canonical_path, document, output_record, payload, require, unchanged, write_document,
)
from blender_bridge.idle_authoring_scene import action_curves
from blender_bridge.walk_authoring_phase import ARMATURE_WORLD_Z_M, FPS, GROUND_SPEED_M_S, STORED_FRAMES
from blender_bridge.walk_authoring_pose import COUNTER_SWING_DEGREES, POSE_EPSILON, capture_analytic, matrix_residual
from ucc.core.authored_idle import AuthoredIdleInspectionRequest
from ucc.core.authored_walk_job import AUTHOR, INPUT_BINDINGS, INTENT, read_walk_intent, validate_job
from ucc.core.target_action_format import MAX_BYTES, checked_uuid

ACTION_NAME = 'UCC_ORIGINAL_STANDING_WALK'
POLICY = 'UCC_PRIVATE_ORIGINAL_WALK_BAKE_V1'
REVIEW = 'original_walk.blend'
FBX = 'original_walk.fbx'
REPORT = 'walk_author_report.json'
ANATOMY = 'idle_anatomical_frame.json'
PROJECT = 'project.ucc.json'
REQUEST = 'idle_inspection_request.json'
CANDIDATE = 'candidate.blend'
BONE_COUNT = 163
FBX_OPTIONS = {
    'check_existing': False, 'use_selection': True, 'object_types': {'ARMATURE'}, 'global_scale': 1.,
    'apply_unit_scale': True, 'apply_scale_options': 'FBX_SCALE_NONE', 'use_space_transform': True,
    'bake_space_transform': False, 'use_custom_props': False, 'add_leaf_bones': False,
    'primary_bone_axis': 'Y', 'secondary_bone_axis': 'X', 'use_armature_deform_only': False,
    'armature_nodetype': 'NULL', 'bake_anim': True, 'bake_anim_use_all_bones': True,
    'bake_anim_use_nla_strips': False, 'bake_anim_use_all_actions': False,
    'bake_anim_force_startend_keying': True, 'bake_anim_step': 1., 'bake_anim_simplify_factor': 0.,
    'path_mode': 'STRIP', 'embed_textures': False, 'batch_mode': 'OFF', 'axis_forward': '-Z', 'axis_up': 'Y',
}


def validate_action(bpy, rig, action, lowered_location):
    require(len(bpy.data.actions) == 1 and rig.animation_data.action == action and action.name == ACTION_NAME
         and len(action.slots) == 1 and rig.animation_data.action_slot == action.slots[0]
         and tuple(action.frame_range) == (1., float(STORED_FRAMES)), 'ONE_CLOSED_WALK_ACTION_AND_CLOCK_REQUIRED')
    curves = action_curves(action)
    expected = {(b.path_from_id('rotation_quaternion'), i) for b in rig.pose.bones for i in range(4)}
    expected |= {('location', index) for index in range(3)}
    require(len(curves) == len(expected) and {(c.data_path, c.array_index) for c in curves} == expected,
         'WALK_ACTION_HAS_UNDECLARED_OR_MISSING_CURVES')
    for curve in curves:
        keys = curve.keyframe_points
        require(len(keys) == STORED_FRAMES and all(k.co.x == i and math.isfinite(k.co.y)
             and k.interpolation == 'LINEAR' for i, k in enumerate(keys, start=1)),
             'WALK_ACTION_MUST_HAVE_DENSE_LINEAR_300_FRAME_CURVES')
        if curve.data_path == 'location':
            require(all(k.co.y == lowered_location[curve.array_index] for k in keys),
                 'WALK_ARMATURE_LOCATION_FCURVES_NOT_CONSTANT')


def bake_action(bpy, rig, samples):
    from mathutils import Quaternion

    require(len(samples) == STORED_FRAMES, 'Walk bake requires the exact 300 stored samples')
    require(not bpy.data.actions and not (rig.animation_data and rig.animation_data.action),
         'WALK_AUTHOR_REFUSES_INHERITED_ACTION')
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, STORED_FRAMES
    scene.render.fps, scene.render.fps_base = FPS, 1.
    for index, (location, rotations) in enumerate(samples, 1):
        scene.frame_set(index)
        rig.location = location
        require(rig.keyframe_insert('location', frame=index), 'WALK_FAILED_TO_KEY_ARMATURE_LOCATION')
        for bone, rotation in zip(rig.pose.bones, rotations, strict=True):
            bone.rotation_mode = 'QUATERNION'
            bone.rotation_quaternion = Quaternion(rotation)
            require(bone.keyframe_insert('rotation_quaternion', frame=index), 'WALK_FAILED_TO_KEY_BONE_QUATERNION')
    require(rig.animation_data and rig.animation_data.action, 'Blender did not create the walk Action')
    action = rig.animation_data.action
    action.name = ACTION_NAME
    for curve in action_curves(action):
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    validate_action(bpy, rig, action, samples[0][0])
    scene.frame_set(1)
    bpy.context.view_layer.update()
    return action


def export_neutral_fbx(bpy, rig, destination, action, original_world, original_location, lowered_location):
    scene, view = bpy.context.scene, bpy.context.view_layer
    selected = list(bpy.context.selected_objects)
    active, hidden, frame = view.objects.active, rig.hide_get(), scene.frame_current
    inserted, inserted_location = [], False
    try:
        for item in view.objects:
            item.select_set(False)
        rig.hide_set(False)
        rig.select_set(True)
        view.objects.active = rig
        rig.location = original_location
        inserted_location = rig.keyframe_insert('location', frame=0)
        require(inserted_location, 'WALK_TEMPORARY_NEUTRAL_OBJECT_KEY_FAILED')
        for bone in rig.pose.bones:
            bone.rotation_quaternion = (1., 0., 0., 0.)
            require(bone.keyframe_insert('rotation_quaternion', frame=0), 'WALK_TEMPORARY_NEUTRAL_BONE_KEY_FAILED')
            inserted.append(bone)
        scene.frame_set(0)
        view.update()
        a, b = (values(matrix) for matrix in (rig.matrix_world, original_world))
        require(scene.frame_current == 0 and matrix_residual(a, b) <= POSE_EPSILON
             and (scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base) == (1, STORED_FRAMES, FPS, 1.)
             and all(matrix_residual(values(obj.matrix), values(obj.bone.matrix_local)) <= POSE_EPSILON
                     for obj in rig.pose.bones),
             'WALK_FBX_STATIC_MODEL_DEFAULTS_NOT_NEUTRAL')
        require(bpy.ops.export_scene.fbx(filepath=str(destination), **FBX_OPTIONS) == {'FINISHED'}
             and destination.is_file(), 'WALK_ARMATURE_ONLY_FBX_EXPORT_FAILED')
    finally:
        try:
            removed = [bone.keyframe_delete('rotation_quaternion', frame=0) for bone in inserted]
            if inserted_location:
                removed.append(rig.keyframe_delete('location', frame=0))
            require(all(removed), 'WALK_TEMPORARY_FBX_NEUTRAL_KEYS_NOT_REMOVED')
        finally:
            scene.frame_set(frame)
            rig.select_set(False)
            rig.hide_set(hidden)
            for item in selected:
                item.select_set(True)
            view.objects.active = active
            view.update()
    validate_action(bpy, rig, action, lowered_location)


def _inputs(root: Path, job: dict):
    checked_uuid(job.get('job_id'))
    options = job.get('options')
    require(job.get('operation') == AUTHOR, 'Wrong walk authoring handler')
    validate_job(AUTHOR, job.get('input_project'), options)
    pins = {name: options[option] for name, option in INPUT_BINDINGS.items()}
    unchanged(root, pins)
    request = AuthoredIdleInspectionRequest.from_bytes(payload(root, REQUEST, pins[REQUEST], MAX_BYTES))
    read_walk_intent(payload(root, INTENT, pins[INTENT], MAX_BYTES), options, request)
    raw_project = payload(root, PROJECT, pins[PROJECT], MAX_BYTES)
    require(raw_project == request.project_snapshot_json
            and dict(request.to_dict()['consumed_sources'])['master_and_derived_rig'] == pins[CANDIDATE],
            'Walk input project or master differs from its admitted neutral measurement request')
    return request.project, pins


def _file(root: Path, name: str) -> dict:
    row = output_record(root, name)
    return {key: row[key] for key in ('bytes', 'sha256')}


def author_source(bpy: Any, root: Path, job: dict) -> dict:
    """Bake a private candidate whose saved files still require an independent reopen."""
    project, inputs = _inputs(root, job)
    review_path, fbx_path, report_path = (canonical_path(root, name) for name in (REVIEW, FBX, REPORT))
    require(not any(path.exists() for path in (review_path, fbx_path, report_path)),
            'Walk author refuses to replace an existing output')
    try:
        declared = document(root, ANATOMY, inputs[ANATOMY])
        measured, human, rig, _ = measure(bpy, root, project, inputs[CANDIDATE])
        check_frame(measured, declared)
        require(len(rig.pose.bones) == BONE_COUNT and not bpy.data.actions,
                'Walk author requires the supported no-Action MPFB neutral rig')
        posed = capture_analytic(bpy, human, rig, measured)
        action = bake_action(bpy, rig, posed.samples)
        require(state_digest(rest_state(rig)) == measured['target']['rest_sha256'],
                'Walk bake changed the neutral rig rest state')
        export_neutral_fbx(bpy, rig, fbx_path, action, posed.neutral_world,
                           posed.neutral_location, posed.samples[0][0])
        require(bpy.ops.wm.save_as_mainfile(filepath=str(review_path), compress=False, copy=True) == {'FINISHED'}
                and review_path.is_file(), 'Blender did not save the original walk review')
        unchanged(root, inputs)
        files = {name: _file(root, name) for name in (REVIEW, FBX)}
        report = {
            'schema_version': 1,
            'policy': POLICY,
            'status': 'ORIGINAL_WALK_BAKED_PENDING_INDEPENDENT_REOPEN',
            'input_pins': {name: _file(root, name) for name in inputs},
            'neutral_rest_sha256': measured['target']['rest_sha256'],
            'files': files.copy(),
            'action_name': ACTION_NAME,
            'body_bones': BONE_COUNT,
            'actual_review_frames': [1, STORED_FRAMES],
            'intended_source_frames_after_fbx_import': [2, STORED_FRAMES+1],
            'fps': FPS,
            'stored_action_samples': len(posed.samples),
            'analytic_samples': len(posed.observations),
            'virtual_index': STORED_FRAMES,
            'virtual_index_stored_as_key': False,
            'position_channel': 'ARMATURE_OBJECT_LOCATION_ONLY',
            'constant_world_z_offset_m': ARMATURE_WORLD_Z_M,
            'ground_compensation_speed_m_s': GROUND_SPEED_M_S,
            'upper_body': {
                'counter_swing_degrees': COUNTER_SWING_DEGREES,
                'phase_basis': 'COSINE_PER_30_FRAME_STRIDE',
                'upper_arm_axis': 'MEASURED_ANATOMICAL_RIGHT',
                'torso_swivel': False,
                'old_animation_loaded': False,
                'hand_clearance_verified': False,
            },
            'virtual_seam': posed.virtual_seam,
            'samples': posed.observations,
            'armature_only_fbx': True,
            'neutral_static_bind_checked_before_export': True,
            'independent_blend_reopen_verified': False,
            'independent_fbx_import_verified': False,
            'usable_action_approved': False,
            'contact_quality_approved': False,
            'visual_quality_approved': False,
            'engine_import_verified': False,
        }
        report_row = write_document(root, REPORT, report)
        files[REPORT] = {key: report_row[key] for key in ('bytes', 'sha256')}
        return {'status': 'ORIGINAL_WALK_BAKED', 'outputs': files}
    finally:
        unchanged(root, inputs)
