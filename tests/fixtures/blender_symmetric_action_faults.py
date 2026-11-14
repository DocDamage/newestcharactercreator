"""Actual rehashed saved-scene faults after fresh source/base reproduction.

One active pose plus complete Action/rest/weights schema is checked here.
This supplements, and does not replace, the separate full-sequence workers.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import sys

import bpy
from mathutils import Quaternion

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from blender_bridge.native_fit_scene import original_context, open_fitted, check_scene, input_hashes, unchanged
from blender_bridge.native_fit_policy import fitted_world_poses
from blender_bridge.native_review_reopen import scene_objects, bound_scene


def verify(job, output):
    options = json.loads((job/'result.json').read_text(encoding='utf-8'))['details']['bindings']
    # Accept either the final verification worker or the cache worker's inputs.
    if 'base_fit_policy_sha256' not in options or 'fit_report_sha256' not in options:
        raise ValueError('Fault contract needs a fully verified layered Action')
    output.mkdir(exist_ok=False); work = output/'inputs'; work.mkdir()
    before = {}
    for name, expected in input_hashes(options).items():
        source = job/name
        if source.is_symlink() or not source.is_file() or sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('Changed symmetric fault-test input')
        before[name] = expected
        with source.open('rb') as reader, (work/name).open('xb') as writer: shutil.copyfileobj(reader, writer)
    baseline, profile, plan, state, _ = original_context(bpy, work, options)
    original = work/'fitted_motion.blend'
    frame = max(range(1, baseline['source_frame_count']+1), key=lambda f: sum(
        sum(v*v for v in plan[s]['clavicle_rotations'][f-1]) for s in ('left', 'right')))
    expected = fitted_world_poses(plan, baseline['full_timeline_frames'][frame-1]['target_global_poses'], frame)
    def checked_pose(rig):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        for name, wanted in expected.items():
            actual = rig.matrix_world@rig.pose.bones[name].matrix
            if (actual.translation-wanted.translation).length > 1e-5 or max(abs(actual[i][j]-wanted[i][j]) for i in range(3) for j in range(3)) > 1e-4:
                raise ValueError('Symmetric saved pose differs from declared layer')
    human, rig = open_fitted(bpy, work, options, baseline, profile, state); checked_pose(rig)
    records = []
    for case, reason in (('left_clavicle_action', 'declared layer'), ('missing_clavicle_key', 'complete linear bake'),
                         ('left_rest_roll', 'rest/roll'), ('weight_ulp', 'exact weights')):
        bpy.ops.wm.open_mainfile(filepath=str(original), load_ui=False); human, rig = scene_objects(bpy)
        name = plan['left']['clavicle']; bone = rig.pose.bones[name]
        if case in ('left_clavicle_action', 'missing_clavicle_key'):
            action = rig.animation_data.action
            curves = sorted([c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves
                             if c.data_path == bone.path_from_id('rotation_quaternion')], key=lambda c: c.array_index)
            if len(curves) != 4: raise ValueError('Missing actual left clavicle Action channels')
            if case == 'missing_clavicle_key':
                for curve in curves: curve.keyframe_points.remove(curve.keyframe_points[frame-1], fast=True)
            else:
                rotation = Quaternion(tuple(c.keyframe_points[frame-1].co.y for c in curves))@Quaternion((1., 0., 0.), .02)
                for curve, value in zip(curves, rotation.normalized()): curve.keyframe_points[frame-1].co.y = value
        if case == 'left_rest_roll':
            bpy.context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
            rig.data.edit_bones[name].roll += .01; bpy.ops.object.mode_set(mode='OBJECT')
        if case == 'weight_ulp':
            vertex, membership = next((v, g) for v in human.data.vertices for g in v.groups if .05 < g.weight < .95)
            bits = struct.unpack('<I', struct.pack('<f', membership.weight))[0]
            human.vertex_groups[membership.group].add([vertex.index], struct.unpack('<f', struct.pack('<I', bits+1))[0], 'REPLACE')
        path = output/(case+'.blend')
        if path.exists() or 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=False, copy=True):
            raise ValueError('Could not author a separate real symmetric fault scene')
        digest = sha256(path.read_bytes()).hexdigest()
        if digest == options['fitted_sha256']: raise ValueError('Fault scene has unchanged bytes')
        bound_scene(path, digest); bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
        human, rig = scene_objects(bpy)
        try: check_scene(bpy, human, rig, baseline, profile, state); checked_pose(rig)
        except ValueError as error:
            if reason not in str(error): raise
            records.append({'case': case, 'new_scene_sha256': digest, 'rejected_by': str(error)})
        else: raise AssertionError('Actual rehashed symmetric fault was accepted: '+case)
    unchanged(work, options)
    if before != {name: sha256((job/name).read_bytes()).hexdigest() for name in before}:
        raise ValueError('Fault check changed an original scene/policy/report')
    return {'status': 'REAL_REHASHED_SYMMETRIC_ACTION_FAULTS_REJECTED', 'active_source_frame': frame,
            'scope': 'ONE_ACTIVE_POSE_AND_COMPLETE_ACTION_REST_WEIGHTS_SCHEMA_AFTER_FRESH_BASE_REPRODUCTION',
            'faults': records, 'positive_saved_pose_passed': True, 'original_inputs_unchanged': True,
            'full_sequence_replacement': False, 'animation_quality_approved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = verify(args.job, args.output)
    with (args.output/'summary.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    print(result['status'], len(result['faults']), flush=True)
