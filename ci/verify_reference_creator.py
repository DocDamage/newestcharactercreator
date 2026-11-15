"""Original-only reference-aware creator gate; retain its closed summary only."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ci.regional_sources import require, digest, expected, protected_inputs
from ci.verify_regional_skin import fixture
from ci.verify_source_references import build_target
from ci.source_reference_checks import clone
from ci.reference_creator_positive import master_cases, expression_case, jobs, objects
from ci.reference_creator_guards import admission_guards, pending_body_guard, live_guards
from ci.reference_creator_faults import saved_faults
from ci.reference_creator_summary import STATUS, FLAGS, validate_summary
from ucc.animations.catalog import AnimationCatalog
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.project_animation_references import attach_catalog_reference
from ucc.library.provenance import LicensePolicy


def setup(blender: Path, out: Path):
    original, common, installed, identity = build_target(blender, out)
    protected = {**protected_inputs({'original': original}), **installed}
    authored = out/'authored-source'; project = original.load()
    fixture(blender, ROOT/'tests/fixtures/blender_native_body.py',
        ['--mode', 'author', '--master', original.root/project.master_blend, '--folder', authored,
         '--origin', 'ground', '--corrective-challenge', '--posed-origin-challenge', '--include-hands'],
        out/'author.log', 300)
    source = authored/'original-native-body.fbx'; source_sha = digest(source); protected[str(source)] = source_sha
    policy = LicensePolicy('Original UCC reference-creator CI armature', 'CC0',
                           'ci-original://reference-creator', reviewed=True, local_preview_allowed=True, no_ai=True)
    database = out/'catalog.sqlite3'
    with AnimationCatalog(database) as catalog: catalog.index_file('original', source, policy)
    runtime = {key: value for key, value in common.items() if key != 'mpfb_data_dir'}
    measured = measure_catalog_fbx(database, 'original', jobs_root=authored/'.ucc-jobs', **runtime)
    require(len(measured['clips']) == 1, 'Original creator source must have one measured actual Action')
    clip = measured['clips'][0]['clip_id']; stores = {}; source_jobs = set((authored/'.ucc-jobs').glob('*/request.json'))
    for name in ('hand', 'nohand'):
        store = clone(original, out/name)
        if name == 'nohand':
            reset = apply_hand_revision(store, manifest_sha256=identity, selection='neutral', **common, **expected(store.load()))
            require(reset.revision is not None and not reset.project.parts, 'Original no-hand fixture did not actually reset')
        before_jobs = jobs(store); current = store.load()
        attached = attach_catalog_reference(store, database, clip, expected_source_sha256=source_sha,
                                            expected_policy=policy, **runtime, **expected(current))
        require(attached.changed and attached.project.animations == (clip,), 'Actual creator source attachment failed')
        binding = check_registered_source(store, database, current.project_id, clip)
        require(binding['license'] == policy.to_dict() and binding['source_only'] is True
                and all(binding[k] is False for k in ('editing_authorized', 'target_preview_verified', 'engine_import_verified')),
                'Creator source attachment upgraded rights or acceptance')
        source_jobs.update(p for p in jobs(store)-before_jobs
                           if json.loads(p.read_text(encoding='utf-8'))['operation'] == 'inspect_fbx_animation')
        stores[name] = store
    require(len(source_jobs) == 6, 'Creator setup lacks paired measurement and two fresh attachments')
    for request in source_jobs:
        reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
        snapshot = json.loads((request.parent/'source_snapshot.json').read_text(encoding='utf-8'))
        require(reply['status'] == 'ok' and len(snapshot['bones']) == 71
                and [f['frame'] for f in snapshot['frames']] == list(range(2, 302))
                and digest(request.parent/'source.fbx') == source_sha, 'Incomplete creator setup source evidence')
    snapshot = clone(stores['hand'], out/'registered-snapshot')
    protected.update({str(snapshot.root/p): h for p, h in objects(snapshot).items()})
    protected[str(snapshot.file)] = digest(snapshot.file)
    print('ORIGINAL_REFERENCE_CREATOR_SETUP_PASSED', flush=True)
    return stores, snapshot, database, common, protected, source_jobs


def verify(blender: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    stores, snapshot, database, common, protected, source_jobs = setup(blender, out)
    with closing(sqlite3.connect(database)) as db: catalog_rows = tuple(db.iterdump())
    positive = {}; changed = noop = 0; previews = {}
    for name, store in stores.items():
        counts, count_changed, count_noop = master_cases(store, database, common, hand=name == 'hand')
        positive['master_'+name] = counts; changed += count_changed; noop += count_noop
        result, counts = expression_case(store, database, common, hand=name == 'hand')
        previews[name] = result; positive['preview_'+name] = counts
    faults = out/'saved-master-faults'
    fixture(blender, ROOT/'tests/fixtures/blender_source_reference_faults.py',
        ['--master', snapshot.root/snapshot.load().master_blend, '--folder', faults], out/'fault-author.log', 300)
    guards = admission_guards(snapshot, database, common, out, faults)
    guards.update(pending_body_guard(stores['nohand'], database, common, out))
    guards.update(live_guards(snapshot, database, common, out))
    guards.update(saved_faults(stores['hand'], previews['hand'], out/'saved-preview-faults'))
    require(all(digest(Path(p)) == sha for p, sha in protected.items()), 'Original creator inputs or installed assets changed')
    with closing(sqlite3.connect(database)) as db:
        require(tuple(db.iterdump()) == catalog_rows, 'Creator operations changed source catalog rows')
    summary = {'status': STATUS, **{flag: True for flag in FLAGS}, 'source_frames': 300, 'source_bones': 71,
        'setup_source_workers': len(source_jobs), 'setup_source_frame_observations': len(source_jobs)*300,
        'positive_source_frame_observations': sum(v['inspect_fbx_animation'] for v in positive.values())*300,
        'changed_master_transactions': changed, 'verified_noop_transactions': noop,
        'decoded_expression_frames': sum(p.preview.cache.frame_count for p in previews.values()),
        'expression_vertices': previews['hand'].preview.cache.vertex_count,
        'expression_triangles': previews['hand'].preview.cache.triangle_count, 'positive_workers': positive,
        'guards': guards, 'visual_quality_approved': False, 'engine_import_verified': False}
    return validate_summary(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.blender, args.outdir)
    (args.outdir/'reference_creator_summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(STATUS, flush=True)
