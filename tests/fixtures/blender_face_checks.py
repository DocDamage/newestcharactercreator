"""Disposable original-MPFB pose/fault checks; never accepts purchased inputs.

This is an integration test helper, not a product geometry operation.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Quaternion

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blender_bridge.face_geometry import intake, evaluated, points_digest, invariant_state, rest_state
from blender_bridge.face_operations import state_digest

FAULTS = ('value', 'one-ulp-value', 'key-coordinate', 'weight', 'rest', 'uv', 'material')


def mutate(root: Path, fault: str):
    bpy.ops.wm.open_mainfile(filepath=str(root/'faced_human.blend'), load_ui=False)
    human, rig, _, _ = intake(bpy)
    key = human.data.shape_keys.key_blocks['nose-scale-horiz-incr']
    if fault == 'value':
        key.value = .4
    elif fault == 'one-ulp-value':
        bits = struct.unpack('<I', struct.pack('<f', key.value))[0]
        key.value = struct.unpack('<f', struct.pack('<I', bits-1))[0]
    elif fault == 'key-coordinate':
        key.data[0].co.x += .001
    elif fault == 'weight':
        group = human.vertex_groups['head']
        vertex = next(v for v in human.data.vertices if any(g.group == group.index for g in v.groups))
        group.add([vertex.index], .125, 'REPLACE')
    elif fault == 'rest':
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones['head'].tail.x += .001
        bpy.ops.object.mode_set(mode='OBJECT')
    elif fault == 'uv':
        human.data.uv_layers[0].data[0].uv.x += .01
    elif fault == 'material':
        if not bpy.data.materials:
            raise RuntimeError('Original MPFB character has no material to test')
        bpy.data.materials[0].diffuse_color[0] = .12345
    else:
        raise ValueError('Unknown integration fault')
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'faced_human.blend'), compress=False)


def poses(source: Path) -> dict:
    source_sha = sha256(source.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    human, rig, _, targets = intake(bpy)
    invariant = state_digest(invariant_state(bpy, human, rig, targets))
    rest = state_digest(rest_state(rig))
    neutral = evaluated(bpy, human, full=True)
    neutral_sha = points_digest(neutral)
    visible_sha = points_digest(evaluated(bpy, human))
    span = max(p[2] for p in neutral)-min(p[2] for p in neutral)
    probes = []
    for name, axes, angle in [('head', (0, 1, 2), 20), ('neck03', (0, 2), 20), ('jaw', (0,), 10),
                              ('eye.L', (2,), 10), ('eye.R', (2,), 10),
                              ('upperarm01.L', (0,), 20), ('upperarm01.R', (0,), 20)]:
        for axis in axes:
            for direction in (-1, 1):
                probes.append((name, axis, direction*angle))
    if len(probes) != 20:
        raise RuntimeError('Pose coverage changed')
    observations = []
    for name, axis, degrees in probes:
        bone = rig.pose.bones[name]
        mode = bone.rotation_mode
        quaternion = bone.rotation_quaternion.copy()
        euler = bone.rotation_euler.copy()
        axis_angle = tuple(bone.rotation_axis_angle)
        try:
            bone.rotation_mode = 'QUATERNION'
            vector = [0., 0., 0.]; vector[axis] = 1.
            bone.rotation_quaternion = Quaternion(vector, math.radians(degrees))
            posed = evaluated(bpy, human, full=True)
            if len(posed) != len(neutral) or len(posed) != 19158:
                raise RuntimeError('Pose changed full mesh indexing')
            movement = [math.dist(a, b) for a, b in zip(neutral, posed)]
            moved = sum(d > 1e-6 for d in movement)
            if moved < 16 or not 1e-6 < max(movement) < span*.5 or points_digest(posed) == neutral_sha:
                raise RuntimeError('Pose did not produce bounded substantial skin movement: '+name)
            if not evaluated(bpy, human):
                raise RuntimeError('Pose has no visible skin')
            observations.append({'bone': name, 'axis': axis, 'degrees': degrees,
                                 'moved_vertices_over_1um': moved, 'maximum_displacement': max(movement)})
        finally:
            bone.rotation_quaternion = quaternion; bone.rotation_euler = euler
            bone.rotation_axis_angle = axis_angle; bone.rotation_mode = mode
            bpy.context.view_layer.update()
        if (points_digest(evaluated(bpy, human, full=True)) != neutral_sha
                or points_digest(evaluated(bpy, human)) != visible_sha
                or state_digest(invariant_state(bpy, human, rig, targets)) != invariant
                or state_digest(rest_state(rig)) != rest):
            raise RuntimeError('Pose did not restore exact geometry/rig/skin state')
    if sha256(source.read_bytes()).hexdigest() != source_sha:
        raise RuntimeError('Pose check changed its original input')
    return {'source_master_sha256': source_sha, 'pose_count': 20, 'observations': observations,
            'exact_restores': True, 'source_unchanged': True,
            'visual_quality_approved': False, 'engine_import_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--fault', choices=FAULTS)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.fault:
        if args.root is None or args.source is not None or args.output is not None:
            parser.error('A fault requires only a disposable root')
        mutate(args.root, args.fault)
    else:
        if args.source is None or args.output is None or args.root is not None:
            parser.error('Pose checks require source and a new output')
        result = poses(args.source)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
