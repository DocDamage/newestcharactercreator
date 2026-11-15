"""Normal reference-aware master/history and complete facial-cache transactions."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path

from ci.regional_sources import require, digest, expected
from ci.verify_source_references import save_history
from ci.reference_creator_summary import WORKERS
from ucc.core.commands import CharacterSession
from ucc.core.hand_parts import hand_selection
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.reference_master_revision import revise_referenced_master
from ucc.jobs.reference_expression_preview import preview_referenced_expressions
from ucc.jobs.reference_expression_evidence import check_referenced_expression_preview


def objects(store) -> dict:
    return {str(p.relative_to(store.root)): digest(p)
        for role in ('master', 'parts', 'expressions', 'animations')
        for p in (store.root/role).rglob('*') if p.is_file()}


def jobs(store) -> set[Path]:
    return set((store.root/'.ucc-jobs').rglob('request.json'))


def observed_workers(store, before: set[Path], group: str, source_sha: str) -> dict:
    counts = Counter()
    for request in jobs(store)-before:
        raw = json.loads(request.read_text(encoding='utf-8'))
        reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
        require(reply['status'] == 'ok' and reply['job_id'] == raw['job_id']
                and reply['operation'] == raw['operation'], 'A normal creator worker failed or was substituted')
        counts[raw['operation']] += 1
        if raw['operation'] == 'inspect_fbx_animation':
            snapshot = json.loads((request.parent/'source_snapshot.json').read_text(encoding='utf-8'))
            require(len(snapshot['bones']) == 71 and [f['frame'] for f in snapshot['frames']] == list(range(2, 302))
                    and digest(request.parent/'source.fbx') == source_sha, 'Incomplete actual creator source observations')
        if raw['operation'] == 'inspect_mpfb_neutral_master':
            require(reply['details']['exact_identity_pose_basis'] is True, 'Master is not exactly neutral')
    require(dict(counts) == WORKERS[group], 'Incomplete creator worker coverage '+group+': '+str(dict(counts)))
    return dict(counts)


def master_cases(store, database: Path, common: dict, *, hand: bool) -> tuple[dict, int, int]:
    initial = store.load(); before_jobs = jobs(store)
    changed_count = noop_count = 0
    binding = check_registered_source(store, database, initial.project_id, initial.animations[0])
    cases = [('face_revision', {'facial_parameters': (('nose_width', .65 if hand else .35),)}, False),
             ('body_refit', {'parameters': (('height', .6 if hand else .55), ('muscle', .5), ('weight', .5))}, False)]
    if hand:
        cases.extend([('body_generation', {'parameters': (('height', .6), ('muscle', .5), ('weight', .55))}, False),
                      ('face_revision', {}, True)])
    for operation, changes, noop in cases:
        current = store.load()
        if changes:
            current = store.save(replace(current, **changes, revision=current.revision+1),
                expected_revision=current.revision, expected_project=current)
        before = store.file.read_bytes(); history = store.list_backups(); old = objects(store)
        session = CharacterSession(current)
        result = revise_referenced_master(store, database, operation=operation, **common, **expected(current))
        saved = store.load()
        require(result.project == saved and saved.animations == initial.animations and saved.expression == initial.expression
                and saved.parameters == current.parameters and saved.facial_parameters == current.facial_parameters,
                'Creator edit lost the saved source/body/face/expression intent')
        require(check_registered_source(store, database, saved.project_id, initial.animations[0]) == binding,
                'Immutable creator source binding or rights changed')
        require(all(digest(store.root/p) == h for p, h in old.items()), 'Creator edit overwrote an immutable original')
        if hand:
            require(saved.parts[0].part_id == initial.parts[0].part_id
                    and hand_selection(saved, result.hand_manifest_sha256) == 'shorter',
                    'Creator edit lost original hand instance or selected variant')
        else:
            require(saved.parts == () and result.hand_manifest_sha256 is None, 'No-hand edit introduced a part')
        if noop:
            require(result.revision is None and saved == current and store.file.read_bytes() == before
                    and store.list_backups() == history and objects(store) == old, 'Verified no-op mutated owner/history')
            noop_count += 1
        else:
            require(result.revision is not None and saved.master_blend != current.master_blend
                    and saved == replace(current, master_blend=saved.master_blend, parts=saved.parts,
                        geometry_state='generated_unverified', rig_profile=None, revision=current.revision+1),
                    'Creator transaction changed unrelated owner metadata')
            if hand: require(saved.parts[0].part_asset_id != current.parts[0].part_asset_id, 'Hand was not rebuilt')
            session.accept_saved_reference_master(saved); save_history(store, session, current)
            changed_count += 1
        print('ORIGINAL_REFERENCE_CREATOR_MASTER_CASE_PASSED', 'hand' if hand else 'nohand', operation, noop, flush=True)
    return (observed_workers(store, before_jobs, 'master_hand' if hand else 'master_nohand', binding['source_sha256']),
            changed_count, noop_count)


def expression_case(store, database: Path, common: dict, *, hand: bool):
    initial = store.load(); before = store.file.read_bytes(); history = store.list_backups()
    old = objects(store); before_jobs = jobs(store)
    result = preview_referenced_expressions(store, database, **common, **expected(initial))
    require(result.project == initial and store.load() == initial and store.file.read_bytes() == before
            and store.list_backups() == history and objects(store) == old, 'Facial preview mutated owner/master/history')
    check_referenced_expression_preview(store, database, result)
    cache = result.preview.cache
    require((cache.frame_count, cache.vertex_count, cache.triangle_count) == (25, 13380, 26756),
            'Incomplete full expression skin/cache')
    frames = [cache.frame(i) for i in range(25)]
    require(frames[0] == frames[-1] and len({a+b for a, b in frames}) > 2,
            'Facial preview lacks deformation or exact neutral endpoints')
    counts = observed_workers(store, before_jobs, 'preview_hand' if hand else 'preview_nohand',
                              result.references[0]['source_sha256'])
    print('ORIGINAL_REFERENCE_CREATOR_25_FRAMES_PASSED', 'hand' if hand else 'nohand', flush=True)
    return result, counts
