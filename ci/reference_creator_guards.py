"""Real admission failures and cancellation/concurrency after private mutation."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, Thread
import time

from ci.regional_sources import require, digest, expected
from ci.source_reference_checks import clone, children
from ci.reference_creator_positive import objects, jobs
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.storage import ProjectStore
from ucc.jobs.expression_verification import registered_expression_source
from ucc.jobs.reference_master_revision import revise_referenced_master
from ucc.jobs.reference_expression_preview import preview_referenced_expressions
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError


def operation(kind: str, store, database: Path, common: dict, cancel=None):
    if kind == 'master':
        return revise_referenced_master(store, database, operation='face_revision', cancel=cancel,
                                       **common, **expected(store.load()))
    return preview_referenced_expressions(store, database, cancel=cancel, **common, **expected(store.load()))


def admission_guards(source, database: Path, common: dict, root: Path, faults: Path) -> dict:
    results = {}
    for kind in ('master', 'preview'):
        for fault, message in [('NoAI', ''), ('assigned_action', 'contains existing Actions'),
                               ('unregistered_neutral', 'no registered revision receipt')]:
            store = clone(source, root/(kind+'-'+fault)); current = store.load()
            if fault == 'NoAI':
                path = store.root/'animations/references'/(sha256(current.animations[0].encode()).hexdigest()+'.json')
                raw = json.loads(path.read_text(encoding='utf-8')); raw['license']['no_ai'] = False
                path.write_text(json.dumps(raw, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
            else:
                stage_unverified_master(store, faults/(fault+'.blend'), authorized_source_root=faults,
                                        expected_project=current, expected_revision=current.revision)
            before = store.file.read_bytes(); old = objects(store); history = store.list_backups()
            try: operation(kind, store, database, common)
            except (AssetPolicyError, ProjectStorageError, WorkerFailure) as error:
                if fault == 'NoAI': require(isinstance(error, AssetPolicyError), 'NoAI failed for an unrelated reason')
                else: require(message in str(error), 'Wrong saved creator admission rejection: '+str(error))
            else: raise RuntimeError('Creator accepted real admission fault '+kind+'-'+fault)
            require(store.file.read_bytes() == before and objects(store) == old and store.list_backups() == history,
                    'Admission failure changed owner/history/immutable files')
            observed = []
            for request in jobs(store):
                raw = json.loads(request.read_text(encoding='utf-8'))
                reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
                observed.append(raw['operation'])
                if fault == 'unregistered_neutral': require(reply['status'] == 'ok', 'Foreign neutral did not pass observation')
            if fault == 'NoAI': require(not observed, 'NoAI failure launched workers')
            elif fault == 'assigned_action': require(observed == ['inspect_mpfb_neutral_master'], 'Animated master passed first observation')
            else:
                require(len(observed) == 4 and observed.count('inspect_mpfb_neutral_master') == 2
                        and observed.count('inspect_fbx_animation') == 2, 'Unknown neutral bypassed actual source/neutral intake')
            results[kind+'_'+fault] = True
            print('ORIGINAL_CREATOR_ADMISSION_GUARD_PASSED', kind, fault, flush=True)
    return results


def pending_body_guard(source, database: Path, common: dict, root: Path) -> dict:
    # A selected hand intentionally rejects pending intent before macro inspection.
    # Use the real no-hand edit result to exercise the physical MPFB read-back.
    require(not source.load().parts, 'Pending physical-body guard needs the no-hand fixture')
    store = clone(source, root/'preview-pending-body'); before = store.load()
    store.save(replace(before, parameters=(('height', .8), ('muscle', .5), ('weight', .5)), revision=before.revision+1),
               expected_revision=before.revision, expected_project=before)
    metadata = store.file.read_bytes(); old = objects(store)
    try: operation('preview', store, database, common)
    except WorkerFailure as error: require('phenotype differed' in str(error), 'Wrong pending-body rejection')
    else: raise RuntimeError('Preview accepted unapplied physical body intent')
    require(store.file.read_bytes() == metadata and objects(store) == old, 'Pending-body rejection changed its owner')
    require(not any(json.loads(p.read_text(encoding='utf-8'))['operation'] == 'stage_mpfb_expression_clip'
                    for p in jobs(store)), 'Pending body reached facial clip staging')
    print('ORIGINAL_CREATOR_PENDING_PHYSICAL_BODY_GUARD_PASSED', flush=True)
    return {'preview_pending_body': True}


def live_guards(source, database: Path, common: dict, root: Path) -> dict:
    results = {}
    for kind in ('master', 'preview'):
        target = 'build_mpfb_hand_assets' if kind == 'master' else 'stage_mpfb_expression_clip'
        for mode in ('cancel', 'external'):
            store = clone(source, root/(kind+'-'+mode)); initial = store.load()
            if kind == 'master':
                initial = store.save(replace(initial, facial_parameters=(('nose_width', .65),), revision=initial.revision+1),
                                     expected_revision=initial.revision, expected_project=initial)
            before = store.file.read_bytes(); old = objects(store); history = store.list_backups()
            cancel = Event(); done = Event(); observed = []; errors = []

            def observe():
                try:
                    deadline = time.monotonic()+1500
                    while not done.is_set() and time.monotonic() < deadline:
                        candidates = []
                        for request in jobs(store):
                            try: raw = json.loads(request.read_text(encoding='utf-8'))
                            except (OSError, json.JSONDecodeError): continue  # A new request may still be writing.
                            if raw['operation'] == target: candidates.append(request)
                        if candidates:
                            for pid, command in children():
                                if not isinstance(command, str): continue  # A starting/exiting process can lack metadata.
                                matches = [p for p in candidates if str(p.resolve()).casefold() in command.casefold()]
                                if not matches: continue
                                require(store.load() == initial and objects(store) == old, 'Private mutation changed outer authority')
                                if kind == 'master':
                                    private = ProjectStore(matches[0].parent.parent.parent); project = private.load()
                                    _, receipt = registered_expression_source(private, project)
                                    require(private.root.is_relative_to(store.root/'.ucc-jobs') and not project.animations
                                            and not project.parts and project.expression == initial.expression
                                            and project.facial_parameters == initial.facial_parameters
                                            and project.master_blend != initial.master_blend
                                            and receipt['operation'] == 'face_revision',
                                            'Live hand builder did not follow a verified private face mutation')
                                observed.append(pid)
                                if mode == 'cancel': cancel.set()
                                else:
                                    store.save(replace(initial, name='Concurrent creator save', revision=initial.revision+1),
                                               expected_revision=initial.revision, expected_project=initial)
                                return
                        time.sleep(.1)
                    if not done.is_set(): raise RuntimeError('No live creator mutation worker observed within bound')
                except BaseException as error:
                    errors.append(str(error)); cancel.set()

            observer = Thread(target=observe); observer.start(); rejected = None
            try:
                try: operation(kind, store, database, common, cancel)
                except (ProjectConflict, ProjectStorageError, WorkerFailure) as error: rejected = error
            finally: done.set(); observer.join(20)
            require(not observer.is_alive() and not errors and len(observed) == 1,
                    'Live creator observer failed: '+str(errors))
            require(objects(store) == old, 'Failed private transaction published outer immutable objects')
            if mode == 'cancel':
                require(rejected is not None and 'cancel' in str(rejected).lower(), 'Wrong actual cancellation failure')
                require(store.file.read_bytes() == before and store.list_backups() == history
                        and observed[0] not in [pid for pid, _ in children()], 'Cancel lost authority/history or left its worker live')
            else:
                require(isinstance(rejected, ProjectConflict) and store.load() == replace(initial,
                    name='Concurrent creator save', revision=initial.revision+1), 'Concurrent saved revision was overwritten')
            suffix = ('cancel_after_face' if mode == 'cancel' else 'external_after_face') if kind == 'master' else mode+'_live_clip'
            results[kind+'_'+suffix] = True
            print('ORIGINAL_CREATOR_LIVE_GUARD_PASSED', kind, mode, flush=True)
    return results
