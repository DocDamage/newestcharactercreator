"""Original-only real expression integration; retain ONLY expression_summary.json."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ucc.core.commands import CharacterSession
from ucc.core.storage import ProjectStore
from ucc.jobs.customized_humanoid import generate_customized_humanoid, apply_saved_customized_body_revision
from ucc.jobs.expression_keys import installed_expression_inputs
from ucc.jobs.expression_preparation import prepare_saved_expressions
from ucc.jobs.expression_preview import preview_saved_expressions
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.face_revision import apply_saved_face_revision
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.hand_storage import load_hand_library
from ci.expression_fault_checks import verify_faults
from ci.expression_transaction_checks import verify_guards

WORKER = ROOT/'blender_bridge/entrypoint.py'
NAMES = ('short-light-narrow', 'middle-neutral', 'tall-muscular-wide')
STATUS = 'REAL_EXPRESSIONS_THREE_BODY_FACE_CASES_REGISTERED_HAND_PRESERVATION_25_FRAMES_AND_THIRTEEN_FAULTS_PASSED'


def require(condition, message):
    if not condition: raise RuntimeError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def expected(project):
    return dict(expected_project_id=project.project_id, expected_revision=project.revision,
                expected_master_blend=project.master_blend)


def edit(store, method, *args):
    old = store.load(); session = CharacterSession(old)
    getattr(session, method)(*args)
    return store.save(session.project, expected_revision=old.revision)


def copy_source(source: ProjectStore, root: Path) -> dict:
    """Copy only explicit generated source/provenance directories, never old jobs."""
    root.mkdir(exist_ok=False)
    protected = {}
    paths = [source.file, *[p for name in ('master', 'parts') if (source.root/name).exists()
                           for p in (source.root/name).rglob('*') if p.is_file()]]
    for path in paths:
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(source.root),
                'Original expression input is redirected')
        protected[str(path)] = digest(path)
        target = root/path.relative_to(source.root); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return protected


def verify(blender: Path, source_root: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False); started = time.monotonic()
    accepted = json.loads((source_root/'hand_parts_summary.json').read_text())
    require(accepted['status'] == 'REAL_HAND_ASSETS_THREE_BODY_FACE_CASES_SWAPS_RESET_AND_EIGHT_REHASHED_FAULTS_PASSED'
            and accepted['original_source_only'] is True, 'Expression gate requires accepted original-only hand sources')
    protected = {}; cases = {}; middle_preview = None; data = None; installed = None
    mutation_checks = {}
    for name in NAMES:
        source = ProjectStore(source_root/name); original = source.load()
        require(not original.parts and not original.animations and original.expression is None
                and digest(source.root/original.master_blend) == accepted['cases'][name]['source_master_sha256'],
                'Expression source differs from original generated hand-gate input')
        protected.update(copy_source(source, out/name))
        store = ProjectStore(out/name)
        if data is None:
            data = discover_face_data(store, blender_exe=blender, worker_script=WORKER)
            installed = {k: digest(p) for k, p in installed_expression_inputs(data).items()}
        common = dict(blender_exe=blender, worker_script=WORKER, mpfb_data_dir=data)
        if name == 'middle-neutral':
            manifests = [load_hand_library(store, p.stem) for p in (store.root/'parts/manifests').glob('*.json')]
            matching = [m for m in manifests if m.source_master == store.root/original.master_blend]
            require(len(matching) == 1, 'Expected one actual original compatible hand library')
            hand = apply_hand_revision(store, **common, manifest_sha256=matching[0].sha256,
                                      selection='shorter', **expected(store.load()))
            require(hand.project.parts and hand.revision is not None, 'Real hand selection did not publish')
        initial = store.load(); old_versions = {str(p): digest(p) for p in (store.root/'master/versions').glob('*.blend')}
        prepared = prepare_saved_expressions(store, **common, **expected(initial))
        ready = store.load(); session = CharacterSession(initial)
        session.accept_saved_expression_master(ready, library_sha256=prepared.library_sha256)
        require(session.undo().master_blend == initial.master_blend and session.project.parts == initial.parts,
                'Preparation undo lost complete original state')
        require(session.redo().expression == ready.expression and session.project.parts == ready.parts,
                'Preparation redo lost complete prepared state')
        require(ready.revision == initial.revision+1 and ready.expression.neutral, 'Preparation did not publish once neutral')
        if initial.parts:
            require(ready.parts[0].part_id == initial.parts[0].part_id
                    and ready.parts[0].part_asset_id != initial.parts[0].part_asset_id,
                    'Expression preparation reused an old hand receipt/manifest or replaced the instance')
        for key in dict(ready.expression.parameters): edit(store, 'set_expression_parameter', key, .5)
        strengths = store.load().expression
        if name == 'short-light-narrow':
            edit(store, 'set_morph', 'height', .35)
            before = store.load()
            revised = apply_saved_customized_body_revision(store, **common, **expected(before))
            require(revised.revision.project.revision == before.revision+1 and store.load().expression == strengths,
                    'Composed body refit discarded expression strengths or published more than once')
            before = store.load()
            generated = generate_customized_humanoid(store, **common, expected_project_id=before.project_id,
                                                     expected_revision=before.revision)
            require(generated.revision.project.revision == before.revision+1 and store.load().expression == strengths,
                    'Body generation discarded expression readiness/strengths')
            mutation_checks['refit_and_generation_preserve_neutral_keys_and_saved_strengths'] = True
        if name == 'tall-muscular-wide':
            edit(store, 'set_face_parameter', 'nose_width', .75)
            before = store.load(); revised = apply_saved_face_revision(store, **common, **expected(before))
            require(revised.revision is not None and store.load().expression == strengths,
                    'Static face revision lost expression intent')
            metadata = store.file.read_bytes()
            no_op = apply_saved_face_revision(store, **common, **expected(store.load()))
            require(no_op.revision is None and store.file.read_bytes() == metadata, 'Verified face no-op created a revision')
            mutation_checks['static_face_revision_and_verified_noop_preserve_expressions'] = True
        saved = store.load(); metadata = store.file.read_bytes()
        preview = preview_saved_expressions(store, **common, **expected(saved))
        require(store.file.read_bytes() == metadata, 'Private expression preview changed saved authority')
        cache = preview.cache; buffers = [cache.frame(i) for i in range(cache.frame_count)]
        require(cache.frame_count == 25 and cache.fps == 24 and cache.vertex_count == 13380
                and cache.triangle_count == 26756 and buffers[0][0] == buffers[-1][0]
                and buffers[0][0] != buffers[12][0], 'Complete actual expression timeline or neutral endpoints differ')
        require(all(len(v) == 13380*12 and len(t) == 26756*12 for v, t in buffers), 'Expression buffers omit geometry')
        session = CharacterSession(saved); session.reset_expression()
        require(session.project.expression.neutral and session.project.master_blend == saved.master_blend
                and session.project.parts == saved.parts, 'Strength reset changed neutral master/hand')
        require(session.undo().expression == strengths, 'Reset undo lost saved strengths')
        if initial.parts:
            middle_preview = preview
            # Actual asset ID parser is authoritative; do not relabel receipts.
            import re
            identity = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-shorter', ready.parts[0].part_asset_id).group(1)
            library = load_hand_library(store, identity)
            reset = apply_hand_revision(store, **common, manifest_sha256=identity, selection='neutral', **expected(store.load()))
            require(reset.project.parts == () and reset.project.expression == strengths
                    and digest(store.root/reset.project.master_blend) == digest(library.source_master),
                    'Normal hand reset did not restore exact prepared original and strengths')
            mutation_checks['genuine_selected_hand_rebuild_and_exact_prepared_original_reset'] = True
        require(old_versions == {p: digest(Path(p)) for p in old_versions}, 'Expression composition changed previous masters')
        cases[name] = {'prepared_once': True, 'complete_history_undo_redo': True, 'registered_hand': bool(initial.parts),
            'saved_strengths': dict(strengths.parameters), 'frame_count': 25, 'fps': 24,
            'visible_vertices_per_frame': 13380, 'triangles_per_frame': 26756,
            'distinct_vertex_buffers': len({sha256(v).hexdigest() for v, _ in buffers}),
            'distinct_triangle_buffers': len({sha256(t).hexdigest() for _, t in buffers}),
            'neutral_endpoints_exact': True, 'master_sha256': preview.master_sha256,
            'expression_library_sha256': preview.library_sha256, 'preview_readonly': True}
        print('REAL_ORIGINAL_EXPRESSION_CASE_PASSED', name, flush=True)
    require(middle_preview is not None, 'Missing real selected-hand preview')
    faults = verify_faults(blender, WORKER, middle_preview, out/'faults')
    guards = verify_guards(ProjectStore(out/NAMES[-1]), common, out/'guards')
    require(protected == {p: digest(Path(p)) for p in protected}, 'Authoritative original hand/face sources changed')
    require(installed == {k: digest(p) for k, p in installed_expression_inputs(data).items()}, 'Installed targets changed')
    return {'status': STATUS, 'cases': cases, 'mutations': mutation_checks, 'faults': faults, 'guards': guards,
            'original_source_only': True, 'original_inputs_unchanged': True, 'installed_assets_unchanged': True,
            'visual_quality_approved': False, 'engine_import_verified': False, 'elapsed_seconds': time.monotonic()-started}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('blender', 'source-root', 'outdir'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.blender.resolve(strict=True), args.source_root.resolve(strict=True), args.outdir.resolve(strict=False))
    with (args.outdir/'expression_summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    print(summary['status'], flush=True)
