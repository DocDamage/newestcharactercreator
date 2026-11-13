"""Original-source real MPFB layer gate; no purchased input enters CI."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ucc.animations.contact_fit import read_fit_plan
from ucc.animations.symmetric_fit import POLICY, read_symmetric_plan
from ucc.animations.symmetric_math import fit_symmetric_frame
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.native_fit import fit_native_preview
from ucc.jobs.fitted_playback import prepare_fitted_playback


def layer_document(preview, base):
    baseline = preview.evidence; source = baseline['full_timeline_frames']; count = len(source)
    profile = json.loads(Path(preview.mapping_profile_used).read_text(encoding='utf-8'))
    rest = base.evidence['target_rest_frames']; parents = {n: r['parent'] for n, r in rest.items()}
    targets = [p['target'] for p in profile['pairs']]; chains = {}
    for side in ('left', 'right'):
        hand = profile['landmarks'][side+'_hand']['target']; ancestors = []; current = parents[hand]
        while current is not None:
            if current in targets: ancestors.append(current)
            current = parents[current]
        if len(ancestors) < 3: raise RuntimeError('Original CI source lacks a mapped shoulder chain')
        chains[side] = dict(zip(('clavicle', 'upper_arm', 'forearm', 'hand'), (*reversed(ancestors[:3]), hand)))
    old = json.loads(Path(base.fit_policy_used).read_text(encoding='utf-8'))
    base_plan = read_fit_plan(old, old['bindings'], baseline, profile, parents)
    def heads(frame, side):
        poses = source[frame-1]['target_global_poses']
        return [tuple(poses[targets.index(chains[side][k])][j*4+3] for j in range(3)) for k in ('upper_arm', 'forearm', 'hand')]
    def bend(frame, side):
        s, e, w = heads(frame, side); a = [e[j]-s[j] for j in range(3)]; b = [w[j]-e[j] for j in range(3)]
        return math.acos(max(-1., min(1., sum(x*y for x, y in zip(a, b))/(math.hypot(*a)*math.hypot(*b)))))
    half = 15
    choices = [c for c in range(half+5, count-half-4) if not any(any(base_plan.offsets[f-1]) or
                (base_plan.hand_rotations and any(base_plan.hand_rotations[f-1])) for f in range(c-half, c+half+1))]
    if not choices: raise RuntimeError('Original CI source has no disjoint shoulder-layer window')
    center = max(choices, key=lambda c: min(bend(f, s) for f in range(c-half, c+half+1) for s in chains))
    if min(bend(f, s) for f in range(center-half, center+half+1) for s in chains) < math.radians(2.):
        raise RuntimeError('Original CI source lacks two continuously bent arms')
    frames = []
    for frame in range(1, count+1):
        bump = math.cos(math.pi*(frame-center)/(2*half))**2 if abs(frame-center) < half else 0.
        row = {'frame': frame}
        for side, sign in (('left', 1.), ('right', -1.)):
            s, _, w = heads(frame, side); distance = math.dist(s, w)
            row[side+'_offset_world'] = [(s[j]-w[j])*.0001*bump/distance for j in range(3)]
            row[side+'_clavicle_rotation_world_degrees'] = [0., 0., sign*.05*bump]
            row[side+'_hand_rotation_local_degrees'] = [sign*.03*bump, 0., 0.]
        frames.append(row)
    identities = base.verification['bindings']
    bindings = {**old['bindings'], 'base_fit_policy_sha256': identities['fit_sha256'],
                'base_fitted_sha256': identities['fitted_sha256'], 'base_fit_report_sha256': identities['fit_report_sha256']}
    data = {'schema_version': 1, 'policy': POLICY, 'bindings': bindings, 'coordinate_space': 'BLENDER_WORLD_METERS',
            'chains': chains, 'fps': baseline['fps'], 'frames': frames,
            'render_frames': [1, center-half+1, center, center+half-1, count]}
    plan = read_symmetric_plan(data, bindings, baseline, profile, parents, base_plan)
    for frame, (s, b) in enumerate(zip(source, base.evidence['frames']), 1):
        fit_symmetric_frame(plan, s['target_global_poses'], b['target_global_poses'], frame)
    return data


def verify_on_preview(blender, store, preview, source, permission, folder, original_playback):
    from ci.verify_native_fit import fit_policy
    folder.mkdir(exist_ok=False); policy, _ = fit_policy(preview)
    base_path = folder/'original-ci-base.json'; base_path.write_text(json.dumps(policy), encoding='utf-8')
    common = dict(source_fbx=source, permission=permission, blender_exe=blender,
                  worker_script=ROOT/'blender_bridge/entrypoint.py', timeout_s=1200)
    base = fit_native_preview(store, preview, fit_policy=base_path, **common)
    document = layer_document(preview, base); path = folder/'original-ci-shoulder-layer.json'
    path.write_text(json.dumps(document, allow_nan=False), encoding='utf-8')
    watched = [source, store.root/'project.ucc.json', store.root/store.load().master_blend,
               Path(base.private_fitted_scene), Path(base.private_timeline), base_path, path]
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in watched}
    fitted = fit_native_preview(store, preview, fit_policy=path, base_preview=base, **common)
    cache = prepare_fitted_playback(store, fitted, **common)
    if cache.cache.frame_count != 300 or len(fitted.angular_audit) != 4 or fitted.angular_audit['tracked_joints'] != 8:
        raise RuntimeError('Symmetric CI did not cover the complete eight-joint correction')
    inactive = [i for i, row in enumerate(document['frames']) if not any(any(v) for k, v in row.items() if k != 'frame')]
    for index in inactive:
        for key in ('skin_sha256', 'raw_skin_sha256', 'triangle_sha256', 'target_global_poses'):
            if base.evidence['frames'][index][key] != fitted.evidence['frames'][index][key]:
                raise RuntimeError('Symmetric Action changed an inactive canonical base frame')
    from ucc.jobs.body_contact_review import review_complete_anatomical_safety
    from ucc.jobs.body_fit_guard import require_body_fit_guard
    from ucc.jobs.enclosure_fit_guard import require_enclosure_fit_guard
    from ucc.jobs.complete_trunk_fit_guard import require_complete_trunk_fit_guard
    review = review_complete_anatomical_safety(store, preview, original_playback, fitted=cache, **common)
    guards = [require_body_fit_guard(review), require_enclosure_fit_guard(review), require_complete_trunk_fit_guard(review)]
    if any(g.frames_checked != 300 for g in guards): raise RuntimeError('Incomplete symmetric anatomical guards')
    fault_folder=folder/'saved-scene-faults'
    subprocess.run([str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','13',
        '--python',str(ROOT/'tests/fixtures/blender_symmetric_action_faults.py'),'--',
        '--job',str(Path(cache.private_manifest).parent),'--output',str(fault_folder)],check=True,timeout=1200)
    faults=json.loads((fault_folder/'summary.json').read_text(encoding='utf-8'))
    if len(faults['faults'])!=4 or not faults['original_inputs_unchanged']:raise RuntimeError('Incomplete real symmetric saved-scene faults')
    if before != {p: sha256(Path(p).read_bytes()).hexdigest() for p in before}: raise RuntimeError('Symmetric CI changed original files')
    return {'status': 'REAL_ORIGINAL_SYMMETRIC_LAYER_GATE_PASSED', 'scope': 'ORIGINAL_CI_SOURCE_NOT_OWNER_OR_PACK_COMPATIBILITY',
            'source_frames': 300, 'mapped_joints': len(preview.evidence['mapped_pairs']), 'tracked_joints': 8,
            'independent_fit_workers': len(set(fitted.worker_job_ids)), 'private_images_decoded': 15,
            'inactive_base_frames_preserved_exactly': len(inactive), 'complete_skin_cache_frames': cache.cache.frame_count,
            'three_anatomical_guard_frames': [g.frames_checked for g in guards],
            'real_rehashed_scene_faults':faults,
            'original_inputs_unchanged': True, 'assets_uploaded': False, 'animation_quality_approved': False, 'engine_import_verified': False}


def verify(blender, folder):
    from ucc.jobs.humanoid_generation import generate_humanoid
    from ci.verify_native_body import verify_native_body
    folder.mkdir(parents=True, exist_ok=False); store = ProjectStore(folder/'project')
    project = store.save(CharacterProject.new('Original symmetric shoulder CI'))
    project = store.save(replace(project, parameters=tuple(sorted({'height': .66, 'muscle': .76, 'weight': .33}.items())),
                                 revision=project.revision+1), expected_revision=project.revision)
    generate_humanoid(store, blender_exe=blender, worker_script=ROOT/'blender_bridge/entrypoint.py',
                      expected_project_id=project.project_id, expected_revision=project.revision, timeout_s=300)
    body = verify_native_body(blender, store, folder/'original-native-source', hip_anchor=True, corrective=True,
                              neutral_reference=True, include_hands=True, symmetric_check=True)
    result = {'status': 'REAL_ORIGINAL_SYMMETRIC_LAYER_SUITE_PASSED', 'native_body': body,
              'symmetric_fit': body['symmetric_layer_contract'], 'assets_uploaded': False, 'engine_import_verified': False}
    (folder/'symmetric_fit_summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True); args = parser.parse_args()
    verify(args.blender, args.outdir); print('REAL_ORIGINAL_SYMMETRIC_LAYER_SUITE_PASSED', flush=True)
