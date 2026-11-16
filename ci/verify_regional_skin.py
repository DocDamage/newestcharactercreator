"""Original-only three-body regional skin integration; retain regional_skin_summary.json only."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ci.regional_sources import NAMES, build_targets, protected_inputs, require, digest, expected
from ucc.animations import native_math as nm
from ucc.animations.native_hands import with_hand_planes
from ucc.animations.native_skin_policy import REGIONAL_V2
from ucc.jobs.fbx_intake import inspect_selected_fbx
from ucc.jobs.native_body import preview_native_body
from ucc.jobs.native_playback import prepare_native_playback
from ucc.library.provenance import LicensePolicy
from ci.native_hand_metrics import hand_local_motion

WORKER = ROOT/'blender_bridge/entrypoint.py'
STATUS = 'REAL_ORIGINAL_REGIONAL_SKIN_THREE_CASES_900_FRAMES_TEN_FAULTS_PASSED'


def fixture(blender: Path, script: Path, args: list, log: Path, timeout: int = 900) -> None:
    with log.open('x', encoding='utf-8') as stream:
        result = subprocess.run([str(blender), '--background', '--factory-startup', '--disable-autoexec',
            '--python-exit-code', '13', '--python', str(script), '--', *map(str, args)],
            stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, 'Original regional fixture failed: '+str(log))


def verify(blender: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False); started = time.monotonic()
    stores, installed = build_targets(blender, WORKER, out)
    protected = protected_inputs(stores)
    middle = stores['middle-neutral']; project = middle.load()
    authored = out/'authored-source'
    fixture(blender, ROOT/'tests/fixtures/blender_native_body.py',
        ['--mode', 'author', '--master', middle.root/project.master_blend, '--folder', authored,
         '--origin', 'ground', '--corrective-challenge', '--posed-origin-challenge', '--include-hands'],
        out/'author.log', 300)
    source = authored/'original-native-body.fbx'; source_sha = digest(source)
    permission = LicensePolicy('Original authored UCC regional CI armature', 'CC0', 'ci-original://regional-skin',
                               reviewed=True, local_preview_allowed=True, no_ai=True)
    intake = inspect_selected_fbx(source, blender_exe=blender, worker_script=WORKER,
        jobs_root=authored/'.ucc-jobs', permission=permission, timeout_s=900)
    spec = json.loads((authored/'mapping-spec.json').read_text(encoding='utf-8'))
    protected[str(source)] = source_sha
    cases = {}; middle_preview = None
    for name in NAMES:
        store = stores[name]; saved = store.load(); master = store.root/saved.master_blend
        profile = with_hand_planes({'schema_version': 1, 'convention': 'NATIVE_ANATOMICAL_REFERENCE_V1',
            'source_sha256': source_sha, 'snapshot_sha256': intake['snapshot']['sha256'],
            'master_sha256': digest(master), 'root_motion_policy': 'SOURCE_HIP_MIDPOINT_V1',
            'skin_deformation_policy': REGIONAL_V2, 'mesh_strain_reference': 'TRUE_NEUTRAL_BIND_V2', **spec})
        mapping = out/(name+'-mapping.json')
        mapping.write_text(json.dumps(profile, indent=2), encoding='utf-8', newline='\n')
        protected[str(mapping)] = digest(mapping)
        preview = preview_native_body(store, source_fbx=source, mapping_profile=mapping,
            blender_exe=blender, worker_script=WORKER, permission=permission, timeout_s=900, **expected(saved))
        data = preview.evidence
        require(data['source_frame_count'] == 300 and len(data['mapped_pairs']) == 59 and
                data['skin_deformation']['schema_version'] == 2 and data['skin_deformation_policy'] == REGIONAL_V2,
                'Original regional case lost full source coverage or policy identity')
        motion = hand_local_motion(data)
        require(min(motion.values()) > 1., 'Original finger movement became inherited wrist movement')
        angle = 0.; previous = None
        for row in data['full_timeline_frames']:
            rotation, _ = nm.rotation(row['target_global_poses'][0], target_noise=True)
            if previous is not None:
                delta = nm.product(nm.transposed(previous), rotation)
                angle += math.degrees(math.acos(max(-1., min(1., (sum(delta[i][i] for i in range(3))-1)/2))))
            previous = rotation
        require(400 < angle < 420, 'Original complete root rotation path was lost')
        travel = math.dist(data['full_timeline_frames'][-1]['hip_midpoint_world'], data['hip_anchor']['target_bind_midpoint_world'])
        require(abs(travel-4*data['root_motion_scale']) < 1e-4, 'Original scaled four-meter hip trajectory was lost')
        playback = prepare_native_playback(store, preview, source_fbx=source, permission=permission,
                                          blender_exe=blender, worker_script=WORKER, timeout_s=900)
        cache = playback.cache
        require(cache.frame_count == 300 and cache.fps == 30 and cache.vertex_count == 13380 and cache.triangle_count == 26756 and
                cache.surface_review.status == 'CHECKED' and bool(playback.surface_verification_job_id),
                'Original regional cache or independent surface coverage is incomplete')
        vertices = set(); triangles = set()
        for frame in range(300):
            v, t = cache.frame(frame); vertices.add(sha256(v).hexdigest()); triangles.add(sha256(t).hexdigest())
        require(len(vertices) > 1, 'Original regional cache contains no actual articulation')
        independent = out/(name+'-independent.json')
        fixture(blender, ROOT/'tests/fixtures/blender_regional_checks.py',
            ['--job', Path(preview.private_timeline).parent, '--output', independent], out/(name+'-independent.log'))
        checked = json.loads(independent.read_text(encoding='utf-8'))
        require(checked['frames_verified'] == 300 and checked['original_binary_weights_and_mask_formula_verified'],
                'Independent regional geometry reader did not verify the complete saved scene')
        require(store.load() == saved and all(digest(Path(p)) == h for p, h in protected.items()),
                'Original regional verification changed saved state or protected inputs')
        cases[name] = {'frames': 300, 'fps': cache.fps, 'mapped_joints': 59, 'intrinsic_hand_motion_degrees': motion,
            'master_sha256': digest(master), 'source_sha256': source_sha, 'root_rotation_path_degrees': angle,
            'hip_travel_world': travel, 'skin_policy': REGIONAL_V2, 'skin_proof_schema': 2,
            'registered_hand': bool(saved.parts), 'saved_expression_strengths': dict(saved.expression.parameters),
            'neutral_error_local': data['skin_deformation']['max_neutral_displacement_local'],
            'min_edge_ratio': min(r['min_edge_length_ratio'] for r in data['master_relative_frames']),
            'max_edge_ratio': max(r['max_edge_stretch_ratio'] for r in data['master_relative_frames']),
            'max_correction_fraction': max(r['skin_correction']['max_correction_local'] for r in data['full_timeline_frames'])/data['model_baseline_diagonal_local'],
            'distinct_vertex_buffers': len(vertices), 'distinct_triangle_buffers': len(triangles),
            'surface_frames_verified': 300, 'surface_flagged_frames': len(cache.surface_review.flagged_frames),
            'independent_saved_reopen': checked, 'paired_workers_full_cache_and_surface_verified': True,
            'originals_unchanged': True}
        if name == 'middle-neutral': middle_preview = preview
        print('ORIGINAL_REGIONAL_CASE_PASSED', name, flush=True)
    from ci.regional_fault_checks import verify_faults
    faults = verify_faults(blender, WORKER, middle_preview, out/'faults')
    require(len(faults['saved_faults_rejected']) == 8 and len(faults['transaction_faults_rejected']) == 2,
            'Original regional fault coverage is incomplete')
    require(all(digest(Path(p)) == h for p, h in protected.items()), 'Original regional inputs changed')
    require(all(digest(Path(p)) == h for p, h in installed.items()), 'Installed MPFB inputs changed')
    return {'schema_version': 1, 'status': STATUS, 'cases': cases, 'faults': faults,
            'original_source_only': True, 'original_inputs_unchanged': True, 'installed_assets_unchanged': True,
            'private_or_purchased_inputs_used': False, 'generated_assets_uploaded': False,
            'visual_quality_approved': False, 'engine_import_verified': False, 'gpu_playback_tested': False,
            'elapsed_seconds': time.monotonic()-started}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('blender', 'outdir'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.blender.resolve(strict=True), args.outdir.resolve(strict=False))
    with (args.outdir/'regional_skin_summary.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(result['status'], flush=True)
