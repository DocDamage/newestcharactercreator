"""Measure actual Blender weight semantics on a staged real MPFB master."""
import argparse
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blender_bridge.face_geometry import intake
from blender_bridge.godot_bind_mesh import SOURCE_ID, _visible_sample


def run(master: Path) -> dict:
    with master.open('rb') as stream:
        before = file_digest(stream, 'sha256').hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    human, rig, _, _ = intake(bpy)
    if human.data.attributes.get(SOURCE_ID):
        raise ValueError('Reserved probe attribute exists')
    attribute = human.data.attributes.new(SOURCE_ID, 'INT', 'POINT')
    attribute.data.foreach_set('value', list(range(len(human.data.vertices))))
    rig.data.pose_position = 'REST'
    ids, local = _visible_sample(bpy, human)
    baseline = [human.matrix_world @ Vector(point) for point in local]
    names = {group.index: group.name for group in human.vertex_groups}
    weights = [[(names[group.group], float(group.weight))
                for group in human.data.vertices[index].groups
                if group.weight > 0 and names[group.group] in rig.data.bones]
               for index in ids]
    totals = [sum(weight for _, weight in row) for row in weights]
    if any(total <= 0 for total in totals):
        raise ValueError('Visible source has an unweighted vertex')
    cases = [(("root", 'Y', .2),),
             (("upperarm01.L", 'Z', .25), ("spine03", 'X', .1)),
             (("wrist.R", 'X', .2), ("finger2-1.R", 'Z', .4))]
    result = []
    rig.data.pose_position = 'POSE'
    for case in cases:
        for bone in rig.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        for name, axis, angle in case:
            rig.pose.bones[name].matrix_basis = Matrix.Rotation(angle, 4, axis)
        posed_ids, coordinates = _visible_sample(bpy, human)
        if posed_ids != ids:
            raise ValueError('Skinning changed static-mask vertex identity')
        actual = [human.matrix_world @ Vector(point) for point in coordinates]
        transforms = {bone.name: rig.matrix_world @ bone.matrix
            @ bone.bone.matrix_local.inverted() @ rig.matrix_world.inverted() for bone in rig.pose.bones}
        normalized = raw = rest_blend = 0.
        for point, row, total, observed in zip(baseline, weights, totals, actual):
            weighted = Vector((0., 0., 0.))
            for name, weight in row:
                weighted += (transforms[name] @ point)*weight
            normalized = max(normalized, (weighted/total-observed).length)
            raw = max(raw, (weighted-observed).length)
            rest_blend = max(rest_blend, (weighted+point*(1-total)-observed).length)
        if not all(math.isfinite(value) for value in (normalized, raw, rest_blend)):
            raise ValueError('Invalid independent weight measurements')
        result.append({'posed_bones': [name for name, _, _ in case],
            'normalized_LBS_max_error_m': normalized, 'raw_sum_max_error_m': raw,
            'rest_blended_max_error_m': rest_blend})
    with master.open('rb') as stream:
        if file_digest(stream, 'sha256').hexdigest() != before:
            raise ValueError('Probe changed staged master bytes')
    return {'status': 'ACTUAL_MPFB_WEIGHT_SEMANTICS_MEASURED_NOT_ENGINE_VERIFIED',
        'blender_version': bpy.app.version_string, 'master_sha256': before,
        'visible_vertices': len(ids), 'min_positive_weight_sum': min(totals),
        'max_positive_weight_sum': max(totals),
        'vertices_with_sum_error_over_1e_5': sum(abs(total-1) > 1e-5 for total in totals),
        'cases': result, 'master_unchanged': True, 'engine_import_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = run(args.master)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(result['status'], flush=True)
