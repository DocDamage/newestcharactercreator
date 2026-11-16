"""Private actual MPFB pose references; no exported or shipping animation."""
from array import array
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blender_bridge.face_geometry import intake, evaluated


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def run(master: Path, out: Path) -> dict:
    if master.is_symlink() or not master.is_file() or out.exists():
        raise ValueError('Require a regular staged master and a new private directory')
    before = digest(master)
    out.mkdir()
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    human, rig, _, _ = intake(bpy)
    if human.animation_data or rig.animation_data:
        raise ValueError('Diagnostic poses require a staged master without an active Action')
    rig.data.pose_position = 'POSE'
    cases = [(), (("root", 'Y', .2),),
             (("upperarm01.L", 'Z', .25), ("spine03", 'X', .1)),
             (("wrist.R", 'X', .2), ("finger2-1.R", 'Z', .4))]
    references = array('f')
    records = []
    for case in cases:
        for bone in rig.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        for name, axis, angle in case:
            rig.pose.bones[name].matrix_basis = Matrix.Rotation(angle, 4, axis)
        bpy.context.view_layer.update()
        points = evaluated(bpy, human)
        if len(points) != 13380:
            raise ValueError('Actual posed MPFB visible topology changed')
        references.extend(value for point in points for value in point)
        deltas = {bone.name: rig.matrix_world @ bone.matrix
                  @ bone.bone.matrix_local.inverted() @ rig.matrix_world.inverted()
                  for bone in rig.pose.bones}
        records.append({'posed_controls': list(case),
                        'source_world_deltas': {name: [list(row) for row in matrix]
                                                for name, matrix in deltas.items()}})
    if sys.byteorder != 'little':
        raise ValueError('Reference writer requires little-endian float32')
    with (out/'pose_positions.bin').open('xb') as stream:
        references.tofile(stream)
    result = {'status': 'ACTUAL_MPFB_POSE_REFERENCES_NOT_ANIMATION_ACCEPTANCE',
              'master_sha256': before, 'blender_version': bpy.app.version_string,
              'source_vertices': 13380, 'cases': records,
              'positions_sha256': digest(out/'pose_positions.bin'),
              'positions_dtype': 'float32le', 'skeletal_animation_verified': False}
    if digest(master) != before:
        raise ValueError('Staged master changed')
    (out/'pose_reference.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n',
                                         encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = run(args.master, args.out)
    print(result['status'], len(result['cases']), flush=True)
