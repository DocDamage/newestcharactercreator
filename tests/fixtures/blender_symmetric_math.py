"""Actual mathutils parity/negative checks using invented numeric unit poses.

This is not a skinned character, retargeting-quality or asset compatibility test.
"""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from fixtures.symmetric_fit_contract import fixture
from test_symmetric_worker import worker_base
from blender_bridge.native_symmetric_policy import parse_symmetric
from blender_bridge.native_symmetric_math import symmetric_world_poses, audit_symmetric
from ucc.animations.symmetric_fit import read_symmetric_plan
from ucc.animations.symmetric_math import fit_symmetric_frame


def flat(matrices, targets):
    return [[float(v) for row in matrices[n] for v in row] for n in targets]


def verify():
    data, bindings, baseline, profile, parents, base, sources, bases = fixture()
    worker = parse_symmetric(data, bindings, baseline, profile, parents, worker_base(base))
    core = read_symmetric_plan(data, bindings, baseline, profile, parents, base)
    actual = []; maximum = 0.
    for frame, (source, retained) in enumerate(zip(sources, bases), 1):
        wanted = fit_symmetric_frame(core, source, retained, frame)
        measured = flat(symmetric_world_poses(worker, source, retained, frame), worker['targets'])
        error = max(abs(a-b) for x, y in zip(wanted, measured) for a, b in zip(x, y))
        assert error < 2e-6, (frame, error)
        maximum = max(maximum, error); actual.append(measured)
    audit = audit_symmetric(worker, sources, bases, actual)
    rejected = []
    for frame, name in ((14, 'clavL'), (14, 'handR'), (14, 'root'), (3, 'handR')):
        bad = deepcopy(actual); bad[frame-1][worker['targets'].index(name)][3] += .001
        try: audit_symmetric(worker, sources, bases, bad)
        except ValueError: rejected.append('observed_'+name+'_'+str(frame))
        else: raise AssertionError('Worker accepted observed pose corruption')
    bad = deepcopy(worker); bad['right']['offsets'][13] = (0., -.07, 0.)
    bad['right']['clavicle_rotations'] = [(0., 0., 0.)]*21; bad['right']['hand_rotations'] = ()
    try: symmetric_world_poses(bad, sources[13], bases[13], 14)
    except ValueError as error:
        assert '15-degree source-world' in str(error), str(error); rejected.append('final_world_rotation')
    else: raise AssertionError('Relative bound relaxed the final source-world rotation bound')
    bad = deepcopy(worker); bad['left']['clavicle_rotations'][13] = (2., 0., worker['left']['clavicle_rotations'][13][2])
    pulse = [flat(symmetric_world_poses(bad, s, b, f), bad['targets']) for f, (s, b) in enumerate(zip(sources, bases), 1)]
    try: audit_symmetric(bad, sources, bases, pulse)
    except ValueError as error:
        assert 'discontinuous' in str(error); rejected.append('actual_clavicle_pulse')
    else: raise AssertionError('Worker accepted actual clavicle discontinuity')
    for case in ('reflection', 'scale', 'nan', 'bool_frame', 'missing_pose', 'short_sequence', 'unreachable', 'straight_pole'):
        bad_source = deepcopy(sources[13]); bad_plan = deepcopy(worker); frame = 14
        if case == 'reflection': bad_source[0][0] = -1.
        if case == 'scale': bad_source[0][0] = 1.1
        if case == 'nan': bad_source[0][3] = float('nan')
        if case == 'bool_frame': frame = True
        if case == 'missing_pose': bad_source.pop()
        if case == 'unreachable': bad_plan['right']['offsets'][13] = (100., 0., 0.)
        if case == 'straight_pole':
            for name, x in (('upperR', -.25), ('lowerR', -.45), ('handR', -.65)):
                i = worker['targets'].index(name)
                for j, value in enumerate((x, 0., 1.5)): bad_source[i][j*4+3] = value
            bad_plan['right']['clavicle_rotations'] = [(0., 0., 0.)]*21
            bad_plan['right']['offsets'][13] = (.001, 0., 0.)
        try:
            if case == 'short_sequence': audit_symmetric(worker, sources[:-1], bases, actual)
            else: symmetric_world_poses(bad_plan, bad_source, bases[13], frame)
        except ValueError: rejected.append(case)
        else: raise AssertionError('Worker accepted '+case)
    # Rotate/translate the whole reference frame while local hand controls stay local.
    from mathutils import Matrix, Vector
    change = Matrix.Translation((3., 4., 1.))@Matrix.Rotation(math.pi/2, 4, 'Z')
    vector_rotation = change.to_3x3(); rotated = deepcopy(worker)
    for name in ('left', 'right'):
        for key in ('offsets', 'clavicle_rotations'):
            rotated[name][key] = [tuple(vector_rotation@Vector(v)) for v in worker[name][key]]
    change_rows = lambda rows: [[float(v) for row in change@Matrix([m[j:j+4] for j in range(0, 16, 4)]) for v in row] for m in rows]
    measured = flat(symmetric_world_poses(rotated, change_rows(sources[13]), change_rows(bases[13]), 14), worker['targets'])
    expected = change_rows(actual[13])
    covariance = max(abs(a-b) for x, y in zip(measured, expected) for a, b in zip(x, y))
    assert covariance < 3e-6, covariance
    return {'status': 'REAL_BLENDER_SYMMETRIC_NUMERIC_CONTRACT_PASSED', 'blender_version': bpy.app.version_string,
            'scope': 'INVENTED_NUMERIC_UNIT_POSES_ONLY_NO_SKIN_OR_ASSET_COMPATIBILITY',
            'frames': 21, 'mapped_joints': len(worker['targets']), 'max_core_worker_matrix_error': maximum,
            'world_frame_covariance_error': covariance, 'angular_audit': audit, 'negative_cases_rejected': rejected,
            'skinned_deformation_verified': False, 'animation_visual_quality_verified': False, 'engine_import_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:]); result = verify()
    with args.output.open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result), flush=True)
