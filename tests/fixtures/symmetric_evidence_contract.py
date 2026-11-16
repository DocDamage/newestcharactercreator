"""Invented report boundary metadata; never a skin or Blender acceptance proof."""
from copy import deepcopy
from hashlib import sha256
import json

from ucc.animations.symmetric_fit import read_symmetric_plan
from ucc.animations.symmetric_math import fit_symmetric_frame, verify_symmetric_sequence
from .symmetric_fit_contract import fixture
from .contact_fit_contract import fitted_contract, matrix, reopen_report


def write_evidence(folder):
    data, bindings, baseline, profile, parents, base, sources, bases = fixture()
    _, _, template_base, _, _, template = fitted_contract()
    count = len(sources)
    baseline.update({k: deepcopy(template_base[k]) for k in ('source_first_frame', 'target_armature_world',
                     'model_baseline_diagonal_local', 'mesh_strain_reference', 'bind_edge_strain', 'master_bind_edge_strain')})
    baseline['full_timeline_frames'] = [{'frame': i, 'target_global_poses': poses, 'root_world_head': [0., 0., 0.]}
                                       for i, poses in enumerate(sources, 1)]
    rest = {n: {'parent': p, 'matrix': matrix((0., 0., 0.))} for n, p in parents.items()}
    policy = {'schema_version': 1, 'policy': base.policy, 'bindings': dict(base.bindings),
              'coordinate_space': 'BLENDER_WORLD_METERS', 'fps': base.fps,
              'chain': {'side': 'right', **dict(zip(('upper_arm', 'forearm', 'hand'), base.chain))},
              'frames': [{'frame': i, 'offset_world': list(v)} for i, v in enumerate(base.offsets, 1)]}
    def write(name, document):
        payload = json.dumps(document, allow_nan=False).encode(); path = folder/name; path.write_bytes(payload)
        return path, sha256(payload).hexdigest()
    _, bindings['base_fit_policy_sha256'] = write('base_contact_fit.json', policy)
    base_options = {**dict(base.bindings), 'fit_sha256': bindings['base_fit_policy_sha256'],
                    'fitted_sha256': bindings['base_fitted_sha256']}
    def report(poses, identities, policy_name):
        result = deepcopy(template)
        result.update(policy=policy_name, bindings=dict(identities), frame_count=count, fps=baseline['fps'],
                      target_rest_frames=deepcopy(rest))
        result['original_review_verification'] = reopen_report(dict(base.bindings))
        for k in ('frames_verified', 'uncorrected_skin_frames_verified', 'master_strain_frames_verified', 'first_pose_observation_frames_verified'):
            result['original_review_verification'][k] = count
        result['frames'] = []
        for frame, row in enumerate(poses, 1):
            measure = deepcopy(template['frames'][0 if frame == 1 else 1])
            measure.update(frame=frame, source_frame=frame, target_global_poses=row,
                           skin_sha256=f'{frame:064x}', raw_skin_sha256=f'{frame+30:064x}', triangle_sha256='f'*64)
            result['frames'].append(measure)
        joint = deepcopy(template['joint_motion_metrics'][0]); joint['frames_measured'] = count
        result['joint_motion_metrics'] = [{**joint, 'bone': p['target']} for p in profile['pairs'][1:]]
        surface = result['surface_review']; surface.update(bindings=dict(identities), frame_count=count,
            hands={'left': 'handL', 'right': 'handR'}, frames=[{'frame': r['frame'], 'skin_sha256': r['skin_sha256'],
                'triangle_sha256': r['triangle_sha256'], 'left': None, 'right': None} for r in result['frames']])
        return result
    base_data = report(bases, base_options, base.policy)
    _, bindings['base_fit_report_sha256'] = write('base_fitted_timeline.json', base_data)
    data['bindings'] = deepcopy(bindings)
    plan = read_symmetric_plan(data, bindings, baseline, profile, parents, base)
    actual = [fit_symmetric_frame(plan, s, b, f) for f, (s, b) in enumerate(zip(sources, bases), 1)]
    path, layer_sha = write('contact_fit.json', data)
    options = {**bindings, 'fit_sha256': layer_sha, 'fitted_sha256': 'd'*64}
    measured = report(actual, options, data['policy']); audit = verify_symmetric_sequence(plan, sources, bases, actual)
    measured['angular_correction_metrics'] = {'max_speed_degrees_s': audit['max_speed_degrees_s'],
                                              'max_acceleration_degrees_s2': audit['max_acceleration_degrees_s2']}
    return path, options, baseline, profile, rest, measured, data, base_data
