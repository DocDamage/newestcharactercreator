"""Original-only source-reference integration; retain source_reference_summary.json only."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ci.regional_sources import require, digest, expected, protected_inputs
from ci.verify_regional_skin import fixture
from ci.source_reference_checks import clone, transaction_guards
from ci.source_reference_summary import STATUS, FLAGS, WORKERS, validate_summary
from ucc.animations.catalog import AnimationCatalog
from ucc.core.commands import CharacterSession
from ucc.core.hand_parts import hand_selection
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.customized_humanoid import generate_customized_humanoid
from ucc.jobs.expression_preparation import prepare_saved_expressions
from ucc.jobs.expression_keys import installed_expression_inputs
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.hand_library import build_hand_library
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.hand_storage import installed_inputs
from ucc.jobs.project_animation_references import attach_catalog_reference, detach_catalog_reference
from ucc.jobs.reference_hand_revision import apply_referenced_hand_revision
from ucc.library.provenance import LicensePolicy

WORKER = ROOT/'blender_bridge/entrypoint.py'


def build_target(blender: Path, out: Path) -> tuple[ProjectStore, dict, dict, str]:
    store = ProjectStore(out/'original')
    initial = store.save(replace(CharacterProject.new('Original source-reference CI humanoid'),
        schema_version=2, facial_parameters=(('nose_width', .5),)))
    data = discover_face_data(store, blender_exe=blender, worker_script=WORKER)
    common = dict(blender_exe=blender, worker_script=WORKER, mpfb_data_dir=data, timeout_s=900)
    generate_customized_humanoid(store, **common, expected_project_id=initial.project_id,
                                 expected_revision=initial.revision)
    prepare_saved_expressions(store, **common, **expected(store.load()))
    for name, _ in store.load().expression.parameters:
        before = store.load(); session = CharacterSession(before)
        session.set_expression_parameter(name, .5)
        store.save(session.project, expected_revision=before.revision)
    library = build_hand_library(store, **common, **expected(store.load())).library
    apply_hand_revision(store, manifest_sha256=library.sha256, selection='shorter',
                        **common, **expected(store.load()))
    project = store.load()
    require(project.parts and project.expression and all(v == .5 for _, v in project.expression.parameters)
            and not project.animations, 'Original prepared hand/expression target is incomplete')
    installed = {str(p): digest(p) for p in installed_expression_inputs(data).values()}
    installed.update({str(p): digest(p) for p in installed_inputs(data).values()})
    return store, common, installed, library.sha256


def save_history(store: ProjectStore, session: CharacterSession, before) -> None:
    """Exercise native undo/save/redo/save without rebuilding accepted geometry."""
    current = store.load()
    undone = session.undo()
    require(undone == replace(before, revision=undone.revision), 'Undo lost complete original intent')
    store.save(undone, expected_revision=current.revision, expected_project=current)
    redone = session.redo()
    require(redone == replace(current, revision=redone.revision), 'Redo lost the saved result')
    store.save(redone, expected_revision=undone.revision, expected_project=undone)
    require(ProjectStore(store.root).load() == redone, 'Independent native project reopen differs')


def verify(blender: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    original, common, installed, identity = build_target(blender, out)
    protected = protected_inputs({'original': original})
    print('ORIGINAL_SOURCE_REFERENCE_TARGET_BUILT', flush=True)
    authored = out/'authored-source'; project = original.load()
    fixture(blender, ROOT/'tests/fixtures/blender_native_body.py',
        ['--mode', 'author', '--master', original.root/project.master_blend, '--folder', authored,
         '--origin', 'ground', '--corrective-challenge', '--posed-origin-challenge', '--include-hands'],
        out/'author.log', 300)
    source = authored/'original-native-body.fbx'; source_sha = digest(source)
    protected[str(source)] = source_sha
    policy = LicensePolicy('Original UCC source-reference CI armature', 'CC0',
                           'ci-original://source-references', reviewed=True, local_preview_allowed=True, no_ai=True)
    database = out/'catalog.sqlite3'
    with AnimationCatalog(database) as catalog: catalog.index_file('original', source, policy)
    runtime = {key: value for key, value in common.items() if key != 'mpfb_data_dir'}
    measured = measure_catalog_fbx(database, 'original', jobs_root=authored/'.ucc-jobs', **runtime)
    require(len(measured['clips']) == 1, 'Measured source did not produce its one actual Action')
    clip = measured['clips'][0]['clip_id']
    with sqlite3.connect(database) as db: catalog_rows = tuple(db.iterdump())
    store = clone(original, out/'character'); initial = store.load(); session = CharacterSession(initial)
    attached = attach_catalog_reference(store, database, clip, expected_source_sha256=source_sha,
        expected_policy=policy, **runtime, **expected(initial))
    require(attached.changed and attached.project == replace(initial, animations=(clip,), revision=initial.revision+1),
            'Source attachment changed master/body/face/parts/expression intent')
    session.accept_saved_animation_references(attached.project); save_history(store, session, initial)
    binding = check_registered_source(store, database, initial.project_id, clip)
    require(binding['license'] == policy.to_dict() and binding['source_only'] is True
            and all(binding[k] is False for k in ('editing_authorized', 'target_preview_verified', 'engine_import_verified')),
            'Source-only binding gained rights or target acceptance')
    snapshot = clone(store, out/'registered-snapshot')
    before = store.file.read_bytes(); history = store.list_backups()
    duplicate = attach_catalog_reference(store, database, clip, expected_source_sha256=source_sha,
        expected_policy=policy, **runtime, **expected(store.load()))
    require(not duplicate.changed and store.file.read_bytes() == before and store.list_backups() == history,
            'Duplicate source attachment advanced history/revision')
    for ordinal, selection in enumerate(('longer', 'longer', 'neutral')):
        current = store.load(); before = store.file.read_bytes(); history = store.list_backups()
        result = apply_referenced_hand_revision(store, database, manifest_sha256=identity,
            selection=selection, **common, **expected(current))
        require((result.revision is not None) == (ordinal != 1)
                and hand_selection(result.project, identity) == selection,
                'Hand transaction changed/no-op status or saved selection differs')
        require(result.project.expression == initial.expression and result.project.animations == (clip,)
                and result.project.parameters == initial.parameters and result.project.facial_parameters == initial.facial_parameters,
                'Hand editing lost references or saved creator intent')
        require(check_registered_source(store, database, initial.project_id, clip) == binding, 'Immutable source binding changed')
        if result.revision is None:
            require(selection == 'longer' and store.file.read_bytes() == before and store.list_backups() == history,
                    'Verified hand no-op changed history/revision')
        else:
            session.accept_saved_part_master(result.project, manifest_sha256=identity)
            save_history(store, session, current)
        print('ORIGINAL_REFERENCED_HAND_TRANSACTION_PASSED', selection, flush=True)
    from ucc.jobs.hand_storage import load_hand_library
    library = load_hand_library(store, identity)
    require(not store.load().parts and store.load().master_blend ==
            'master/versions/'+library.manifest['recipe']['bindings']['master_sha256']+'.blend',
            'Original hand reset did not restore the exact library master')
    before = store.load()
    detached = detach_catalog_reference(store, clip, **runtime, **expected(before))
    require(detached.changed and detached.project.animations == (), 'Actual reference detach failed')
    session.accept_saved_animation_references(detached.project); save_history(store, session, before)
    counts = {}; source_jobs = []
    for request in (store.root/'.ucc-jobs').rglob('request.json'):
        record = json.loads(request.read_text(encoding='utf-8'))
        reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
        require(reply['status'] == 'ok', 'A normal source-reference worker failed')
        kind = record['operation']; counts[kind] = counts.get(kind, 0)+1
        if kind == 'inspect_fbx_animation': source_jobs.append(request.parent)
    require(counts == WORKERS, 'Incomplete actual normal worker coverage: '+str(counts))
    catalog_jobs = list((authored/'.ucc-jobs').glob('*/request.json'))
    require(len(catalog_jobs) == 2, 'Catalog measurement must run two genuine source workers')
    for request in catalog_jobs:
        require(json.loads((request.parent/'result.json').read_text(encoding='utf-8'))['status'] == 'ok',
                'Catalog source worker failed')
        source_jobs.append(request.parent)
    for job in source_jobs:
        data = json.loads((job/'source_snapshot.json').read_text(encoding='utf-8'))
        require(len(data['bones']) == 71 and [f['frame'] for f in data['frames']] == list(range(2, 302))
                and digest(job/'source.fbx') == source_sha, 'Actual source snapshot coverage or identity differs')
    faults = out/'saved-faults'
    fixture(blender, ROOT/'tests/fixtures/blender_source_reference_faults.py',
        ['--master', snapshot.root/snapshot.load().master_blend, '--folder', faults], out/'fault-author.log', 300)
    guards = transaction_guards(snapshot, database, identity, common, out, faults)
    require(all(digest(Path(p)) == h for p, h in {**protected, **installed}.items()), 'Original inputs or installed data changed')
    with sqlite3.connect(database) as db: require(tuple(db.iterdump()) == catalog_rows, 'Source catalog rows changed')
    summary = {'status': STATUS, **{flag: True for flag in FLAGS}, 'source_frames': 300,
        'source_bones': 71, 'catalog_source_workers': len(catalog_jobs),
        'complete_source_frame_observations': len(source_jobs)*300, 'positive_workers': counts,
        'guards': guards, 'visual_quality_approved': False, 'engine_import_verified': False}
    return validate_summary(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.blender, args.outdir)
    (args.outdir/'source_reference_summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(STATUS, flush=True)
