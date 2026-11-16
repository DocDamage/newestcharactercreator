"""Eight actual plain-master transactions with native save/reopen history."""
from collections import Counter
from dataclasses import replace
import json
from ci.regional_sources import require, digest, expected
from ci.reference_creator_positive import jobs, objects
from ci.verify_source_references import save_history
from ci.plain_reference_summary import WORKERS
from ucc.core.commands import CharacterSession
from ucc.core.hand_parts import hand_selection
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.reference_master_revision import revise_referenced_master


def observations(store, before, source_sha):
    counts = Counter()
    for request in sorted(jobs(store)-before):
        raw = json.loads(request.read_text(encoding='utf-8'))
        result = request.parent/'result.json'
        reply = json.loads(result.read_text(encoding='utf-8'))
        require(reply['status'] == 'ok' and reply['job_id'] == raw['job_id']
                and reply['operation'] == raw['operation'], 'Failed/substituted actual positive worker')
        op = raw['operation']; counts[op] += 1
        require('expression' not in op, 'Plain workflow unexpectedly introduced prepared expressions')
        if op == 'inspect_fbx_animation':
            snapshot = json.loads((request.parent/'source_snapshot.json').read_text(encoding='utf-8'))
            require(len(snapshot['bones']) == 71 and [f['frame'] for f in snapshot['frames']] == list(range(2, 302))
                    and digest(request.parent/'source.fbx') == source_sha, 'Incomplete actual source observations')
        if op == 'inspect_mpfb_neutral_master':
            require(reply['details']['exact_identity_pose_basis'] is True, 'Non-neutral plain master')
    require(counts['inspect_fbx_animation'] == 2, 'Plain edit omitted its fresh paired full source intake')
    require(counts['inspect_character'] >= 2, 'Plain edit omitted actual physical body read-back')
    return dict(counts)


def verify_cases(stores: dict, database, common: dict, source_sha: str) -> dict:
    completed = {}; changed = noop_count = 0
    for name, store in stores.items():
        initial = store.load(); hand = name == 'hand'
        binding = check_registered_source(store, database, initial.project_id, initial.animations[0])
        cases = [('face_revision', {'facial_parameters': (('nose_width', .65 if hand else .35),)}, False),
            ('body_refit', {'parameters': (('height', .6 if hand else .55), ('muscle', .5), ('weight', .5))}, False),
            ('body_generation', {'parameters': (('height', .6 if hand else .55), ('muscle', .5), ('weight', .55 if hand else .6))}, False),
            ('face_revision', {}, True)]
        for index, (operation, intent, noop) in enumerate(cases):
            current = store.load()
            if intent:
                current = store.save(replace(current, **intent, revision=current.revision+1),
                    expected_project=current, expected_revision=current.revision)
            before = store.file.read_bytes(); history = store.list_backups(); old = objects(store)
            session = CharacterSession(current); before_jobs = jobs(store)
            result = revise_referenced_master(store, database, operation=operation, **common, **expected(current))
            saved = store.load()
            require(result.project == saved and saved.expression is None and saved.animations == initial.animations,
                    'Plain edit changed source IDs or introduced expression controls')
            require(saved.parameters == current.parameters and saved.facial_parameters == current.facial_parameters,
                    'Plain edit lost saved shape intent')
            require(check_registered_source(store, database, saved.project_id, initial.animations[0]) == binding,
                    'Plain edit changed immutable source binding/NoAI policy')
            require(all(digest(store.root/p) == h for p, h in old.items()), 'Plain edit overwrote immutable objects')
            if hand:
                require(saved.parts[0].part_id == initial.parts[0].part_id
                        and hand_selection(saved, result.hand_manifest_sha256) == 'shorter', 'Hand instance/variant lost')
            else:
                require(not saved.parts and result.hand_manifest_sha256 is None, 'Plain no-hand edit introduced a part')
            if noop:
                require(result.revision is None and saved == current and before == store.file.read_bytes()
                        and history == store.list_backups() and objects(store) == old, 'Real no-op altered owner/history')
                noop_count += 1
            else:
                require(result.revision is not None and saved.master_blend != current.master_blend
                        and saved == replace(current, master_blend=saved.master_blend, parts=saved.parts,
                            geometry_state='generated_unverified', rig_profile=None, revision=current.revision+1),
                        'Plain atomic transaction changed unrelated metadata')
                if hand: require(saved.parts[0].part_asset_id != current.parts[0].part_asset_id, 'Hand library not rebuilt')
                session.accept_saved_reference_master(saved); save_history(store, session, current); changed += 1
            counts = observations(store, before_jobs, source_sha)
            key = name+'-'+str(index)+'-'+operation
            require(counts == WORKERS[key], 'Incomplete plain worker coverage '+key+': '+str(counts))
            completed[key] = counts
            print('REAL_PLAIN_REFERENCE_CASE_PASSED', key, 'workers', sum(counts.values()), flush=True)
    require((changed, noop_count) == (6, 2), 'Missing hand/no-hand plain operations or real no-ops')
    return completed
