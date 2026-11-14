"""Real installed-MPFB facial slice on original generated humans; no purchased data."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ucc.core.commands import CharacterSession
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.customized_humanoid import generate_customized_humanoid, apply_saved_customized_body_revision
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.face_revision import apply_saved_face_revision, bundled_face_assets
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner, WorkerFailure

FIXTURE = ROOT/'tests/fixtures/blender_face_checks.py'
WORKER = ROOT/'blender_bridge/entrypoint.py'
FAULTS = ('value', 'one-ulp-value', 'key-coordinate', 'weight', 'rest', 'uv', 'material')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fixture(blender, arguments, log):
    with log.open('x', encoding='utf-8') as stream:
        result = subprocess.run([str(blender), '--background', '--disable-autoexec', '--python-exit-code', '13',
                                 '--python', str(FIXTURE), '--', *map(str, arguments)],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    require(result.returncode == 0, 'Real Blender fixture failed: '+str(log))


def latest_stage(transaction, recipe_sha):
    matches = []
    for request in (transaction/'.ucc-jobs').glob('*/request.json'):
        job = json.loads(request.read_text(encoding='utf-8'))
        if job['operation'] == 'stage_mpfb_face' and job['options']['recipe_sha256'] == recipe_sha:
            matches.append((request.parent, job['options']))
    require(len(matches) == 1, 'Expected one exact bound facial stage')
    return matches[0]


def verify(blender: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    discovery = ProjectStore(out/'asset-inspection')
    discovery.save(CharacterProject.new('Original facial asset inspection'))
    data = discover_face_data(discovery, blender_exe=blender, worker_script=WORKER)
    asset_before = {name: digest(path) for name, (path, _) in bundled_face_assets(data).items()}
    common = dict(blender_exe=blender, worker_script=WORKER, mpfb_data_dir=data)
    cases = {}
    stores = {}
    for name, macros, value in [('short-light-narrow', (.3, .2, .25), 0.),
                                ('middle-neutral', (.5, .5, .5), .5),
                                ('tall-muscular-wide', (.8, .8, .75), 1.)]:
        store = ProjectStore(out/name)
        initial = store.save(replace(CharacterProject.new(name), schema_version=2,
                                     parameters=tuple(zip(('height', 'muscle', 'weight'), macros)),
                                     facial_parameters=(('nose_width', value),)))
        result = generate_customized_humanoid(store, **common, expected_project_id=initial.project_id,
                                              expected_revision=initial.revision)
        saved = store.load()
        require(saved == result.revision.project and saved.revision == initial.revision+1,
                'Customized generation did not publish exactly once')
        require(saved.facial_parameters == initial.facial_parameters and saved.parameters == initial.parameters,
                'Customized generation discarded saved intent')
        require(result.face_observed['authoritative_master_sha256'] == result.revision.sha256,
                'Published customized master differs from authoritative face result')
        require(len(list((store.root/'master/versions').glob('*.blend'))) == 1,
                'Intermediate masters escaped the private transaction')
        pose_path = out/(name+'-poses.json')
        fixture(blender, ['--source', result.revision.master_path, '--output', pose_path], out/(name+'-poses.log'))
        pose_proof = json.loads(pose_path.read_text(encoding='utf-8'))
        require(pose_proof['pose_count'] == 20 and pose_proof['exact_restores'] is True,
                'Missing complete real pose restoration')
        cases[name] = {'master_sha256': result.revision.sha256, 'saved_once': True,
                       'body_parameters': dict(saved.parameters), 'facial_parameters': dict(saved.facial_parameters),
                       'face_evidence': result.face_observed, 'poses': pose_proof}
        stores[name] = (store, result)
        print('REAL_CUSTOM_FACE_GENERATION_AND_20_POSES_PASSED', name, flush=True)

    wide_store, wide = stores['tall-muscular-wide']
    initial = wide_store.load(); old_master = wide_store.root/initial.master_blend; old_sha = digest(old_master)
    no_op_before = wide_store.file.read_bytes()
    no_op = apply_saved_face_revision(wide_store, **common, expected_project_id=initial.project_id,
                                      expected_revision=initial.revision, expected_master_blend=initial.master_blend)
    require(no_op.revision is None and wide_store.file.read_bytes() == no_op_before,
            'Already-applied face fabricated a master revision')
    changed = CharacterSession(initial).set_morph('height', .65)
    changed = wide_store.save(changed, expected_revision=initial.revision)
    refitted = apply_saved_customized_body_revision(wide_store, **common,
                expected_project_id=changed.project_id, expected_revision=changed.revision,
                expected_master_blend=changed.master_blend)
    require(refitted.revision.project.revision == changed.revision+1
            and refitted.revision.project.facial_parameters == initial.facial_parameters
            and digest(old_master) == old_sha, 'Existing body refit lost face intent or original master')
    pose_path = out/'refitted-wide-poses.json'
    fixture(blender, ['--source', refitted.revision.master_path, '--output', pose_path], out/'refitted-wide-poses.log')
    cases['refitted-wide'] = {'master_sha256': refitted.revision.sha256, 'saved_once': True,
                              'face_evidence': refitted.face_observed,
                              'poses': json.loads(pose_path.read_text(encoding='utf-8'))}

    stage, options = latest_stage(wide.private_transaction, wide.face_observed['recipe_sha256'])
    required = ('candidate.blend', 'face_recipe.json', 'nose-scale-horiz-decr.target.gz',
                'nose-scale-horiz-incr.target.gz', 'faced_human.blend', 'face_report.json')
    original_hashes = {name: digest(stage/name) for name in required}
    rejected = {}
    runner = BlenderJobRunner(blender, out/'fault-verifiers', WORKER)
    for fault in FAULTS:
        root = out/('fault-'+fault); root.mkdir()
        for name in required:
            shutil.copyfile(stage/name, root/name)
        fixture(blender, ['--root', root, '--fault', fault], out/(fault+'-mutation.log'))
        report = json.loads((root/'face_report.json').read_text(encoding='utf-8'))
        report['scene_sha256'] = digest(root/'faced_human.blend')
        (root/'face_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        hashes = dict(options, face_sha256=digest(root/'faced_human.blend'),
                      report_sha256=digest(root/'face_report.json'))
        try:
            runner.run(JobRequest.new('verify_mpfb_face', input_project='candidate.blend', options=hashes),
                       staged_inputs={name: root/name for name in required})
        except WorkerFailure as exc:
            message = str(exc)
            require(any(text in message for text in ('Saved facial', 'Existing facial key')),
                    'Fault failed for an unrelated setup/protocol reason: '+fault)
            rejected[fault] = True
        else:
            raise RuntimeError('Coherently rehashed saved-scene fault was accepted: '+fault)
    require(all(digest(stage/name) == sha for name, sha in original_hashes.items()), 'Fault tests changed accepted inputs')

    cancel = Event(); cancel.set(); before = wide_store.file.read_bytes(); saved = wide_store.load()
    try:
        apply_saved_face_revision(wide_store, **common, expected_project_id=saved.project_id,
                                  expected_revision=saved.revision, expected_master_blend=saved.master_blend, cancel=cancel)
    except ProjectStorageError:
        pass
    else:
        raise RuntimeError('Pre-cancelled face revision started')
    try:
        apply_saved_face_revision(wide_store, **common, expected_project_id=saved.project_id,
                                  expected_revision=saved.revision-1, expected_master_blend=saved.master_blend)
    except ProjectConflict:
        pass
    else:
        raise RuntimeError('Stale facial intent was accepted')
    require(wide_store.file.read_bytes() == before, 'Cancellation/conflict changed saved project')
    require(asset_before == {name: digest(path) for name, (path, _) in bundled_face_assets(data).items()},
            'Installed bundled assets changed')
    return {'status': 'REAL_CUSTOM_FACE_GENERATION_REFIT_80_POSES_AND_SEVEN_REHASHED_FAULTS_PASSED',
            'cases': cases, 'faults_rejected': rejected, 'already_applied_no_revision': True,
            'cancel_and_stale_revision_preserved_project': True, 'installed_assets_unchanged': True,
            'original_source_only': True, 'visual_quality_approved': False, 'engine_import_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.blender.resolve(strict=True), args.outdir.resolve(strict=False))
    with (args.outdir/'custom_face_summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    print(summary['status'], flush=True)
