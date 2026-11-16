"""Thirteen actual admission, live-worker and late-publication rejection guards."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Event, Thread
import time

from ci.regional_sources import require, digest, expected
from ci.source_reference_checks import clone, children
from ci.reference_creator_positive import jobs, objects
from ci.verify_regional_skin import fixture
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.storage import ProjectStore
from ucc.jobs import reference_plain_master as plain
from ucc.jobs.reference_master_revision import revise_referenced_master
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError

ROOT = Path(__file__).resolve().parents[1]


class PlainGuards:
    """Faults mutate disposable clones only; every worker remains real Blender."""

    def __init__(self, baselines: Path, out: Path, database: Path, common: dict) -> None:
        self.baselines = baselines
        self.out = out
        self.database = database
        self.common = common
        self.blender = common['blender_exe']
        self.completed: dict[str, bool] = {}

    def state(self, store: ProjectStore) -> tuple: return store.file.read_bytes(), objects(store), store.list_backups()

    def unchanged(self, store: ProjectStore, before: tuple) -> None:
        require(self.state(store) == before, 'Rejected private transaction altered owner/history/immutable objects')

    def operation(self, store: ProjectStore, database: Path | None = None, cancel: Event | None = None):
        return revise_referenced_master(store, self.database if database is None else database, operation='face_revision', cancel=cancel,
                                       **self.common, **expected(store.load()))

    def records(self, store: ProjectStore) -> list[dict]:
        found = []
        for request in sorted(jobs(store)):
            raw = json.loads(request.read_text(encoding='utf-8')); result = request.parent/'result.json'
            reply = json.loads(result.read_text(encoding='utf-8')) if result.exists() else None
            found.append({'request': str(request.relative_to(self.out)), 'operation': raw['operation'],
                'status': reply['status'] if reply else 'no_result', 'request_sha256': digest(request),
                'result_sha256': digest(result) if reply else None})
        return found

    def accepted(self, name: str, error: Exception) -> None:
        require(name not in self.completed and error is not None, 'Guard missing or repeated')
        self.completed[name] = True
        print('REAL_PLAIN_GUARD_PASSED', name, type(error).__name__, flush=True)

    def admission(self) -> None:
        for name in ('hand', 'nohand'):
            source = ProjectStore(self.baselines/('registered-'+name)); initial = source.load()
            faults = self.out/('faults-'+name)
            fixture(self.blender, ROOT/'tests/fixtures/blender_source_reference_faults.py',
                ['--master', source.root/initial.master_blend, '--folder', faults], self.out/(name+'-faults.log'), 300)
            cases = ['NoAI', 'assigned_action', 'tiny_pose', 'pending_body']
            if name == 'hand': cases.append('unregistered_neutral')
            for fault in cases:
                store = clone(source, self.out/(name+'-'+fault)); current = store.load()
                if fault == 'NoAI':
                    binding = store.root/'animations/references'/(sha256(current.animations[0].encode()).hexdigest()+'.json')
                    raw = json.loads(binding.read_text(encoding='utf-8')); raw['license']['no_ai'] = False
                    binding.write_text(json.dumps(raw, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
                elif fault == 'pending_body':
                    store.save(replace(current, parameters=(('height', .8), ('muscle', .5), ('weight', .5)),
                        revision=current.revision+1), expected_project=current, expected_revision=current.revision)
                else:
                    stage_unverified_master(store, faults/(fault+'.blend'), authorized_source_root=faults,
                        expected_project=current, expected_revision=current.revision)
                before = self.state(store); rejected = None
                try: self.operation(store)
                except (AssetPolicyError, ProjectStorageError, WorkerFailure) as error: rejected = error
                require(rejected is not None, 'Actual plain admission accepted '+name+'-'+fault)
                self.unchanged(store, before)
                evidence = self.records(store); ops = [row['operation'] for row in evidence]
                if fault == 'NoAI':
                    require(isinstance(rejected, AssetPolicyError) and not ops, 'NoAI failed late or for another reason')
                elif fault in ('assigned_action', 'tiny_pose'):
                    require(isinstance(rejected, WorkerFailure) and ops == ['inspect_mpfb_neutral_master'],
                            'Saved Action/pose did not fail first actual neutral worker')
                    require(('contains existing Actions' if fault == 'assigned_action' else 'exact identity') in str(rejected),
                            'Wrong actual neutral rejection: '+str(rejected))
                elif fault == 'pending_body':
                    require(isinstance(rejected, WorkerFailure) and 'phenotype differed' in str(rejected),
                            'Wrong physical pending-body failure: '+str(rejected))
                    require(ops.count('inspect_character') == 1 and 'stage_mpfb_face' not in ops
                            and len(ops) == (7 if name == 'hand' else 5), 'Pending body bypassed actual read-back')
                else:
                    require(isinstance(rejected, ProjectStorageError) and 'no registered revision receipt' in str(rejected)
                            and len(ops) == 4 and all(row['status'] == 'ok' for row in evidence),
                            'Foreign hand neutral did not fail immutable receipt admission')
                self.accepted(name+'_'+fault, rejected)

    def changed_face(self, store: ProjectStore):
        current = store.load()
        return store.save(replace(current, facial_parameters=(('nose_width', .65),), revision=current.revision+1),
                          expected_project=current, expected_revision=current.revision)

    def live(self) -> None:
        for mode in ('cancel', 'external'):
            store = clone(ProjectStore(self.baselines/'registered-hand'), self.out/('live-'+mode))
            initial = self.changed_face(store); before = self.state(store)
            cancel = Event(); done = Event(); seen = []; errors = []

            def observe():
                try:
                    deadline = time.monotonic()+1200
                    while not done.is_set() and time.monotonic() < deadline:
                        candidates = []
                        for request in jobs(store):
                            try: raw = json.loads(request.read_text(encoding='utf-8'))
                            except (OSError, json.JSONDecodeError): continue
                            if raw['operation'] == 'build_mpfb_hand_assets': candidates.append(request)
                        if candidates:
                            for pid, command in children():
                                if not isinstance(command, str): continue
                                matching = [p for p in candidates if str(p.resolve()).casefold() in command.casefold()]
                                if not matching: continue
                                private = ProjectStore(matching[0].parent.parent.parent); project = private.load()
                                require(private.root.resolve().is_relative_to((store.root/'.ucc-jobs').resolve())
                                        and not project.animations and not project.parts and project.expression is None
                                        and project.facial_parameters == initial.facial_parameters
                                        and project.master_blend != initial.master_blend, 'No actual private plain face mutation')
                                faced = [p for p in jobs(private) if json.loads(p.read_text(encoding='utf-8'))['operation'] == 'stage_mpfb_face']
                                require(len(faced) == 1 and json.loads((faced[0].parent/'result.json').read_text(encoding='utf-8'))
                                        ['details']['metrics']['geometry_changed'] is True, 'Live guard preceded real face geometry change')
                                self.unchanged(store, before); seen.append(pid)
                                if mode == 'cancel': cancel.set()
                                else:
                                    store.save(replace(initial, name='Concurrent plain saved edit', revision=initial.revision+1),
                                        expected_project=initial, expected_revision=initial.revision)
                                return
                        time.sleep(.1)
                    if not done.is_set(): raise RuntimeError('Actual live builder was never observed')
                except BaseException as error:
                    errors.append(str(error)); cancel.set()

            observer = Thread(target=observe); observer.start(); rejected = None
            try:
                try: self.operation(store, cancel=cancel)
                except (ProjectConflict, ProjectStorageError, WorkerFailure) as error: rejected = error
            finally: done.set(); observer.join(20)
            require(not observer.is_alive() and not errors and len(seen) == 1, 'Live observer failed: '+str(errors))
            require(objects(store) == before[1], 'Live failure published immutable owner objects')
            if mode == 'cancel':
                require(rejected is not None and 'cancel' in str(rejected).lower(), 'Wrong live cancellation failure')
                self.unchanged(store, before)
                require(seen[0] not in [pid for pid, _ in children()], 'Cancelled actual worker is still live')
            else:
                require(isinstance(rejected, ProjectConflict) and store.load() == replace(initial,
                    name='Concurrent plain saved edit', revision=initial.revision+1), 'External saved owner was overwritten')
            self.accepted('live_'+mode+'_after_face', rejected)

    def late(self) -> None:
        original_inspect = plain.inspect_saved_neutral_master
        for fault in ('rehashed_pointer', 'WAL_policy'):
            store = clone(ProjectStore(self.baselines/'registered-hand'), self.out/('late-'+fault)); self.changed_face(store)
            before = self.state(store); observed = []; writer = None; database = self.database
            if fault == 'WAL_policy':
                database = self.out/'disposable-policy.sqlite3'
                with closing(sqlite3.connect('file:'+self.database.as_posix()+'?mode=ro', uri=True)) as source:
                    with closing(sqlite3.connect(database)) as destination: source.backup(destination)
                writer = sqlite3.connect(database); writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('PRAGMA wal_autocheckpoint=0'); writer.commit()

            def after_verified(private, **kwargs):
                result = original_inspect(private, **kwargs)
                require(not observed, 'Final inspection hook ran twice')
                if fault == 'rehashed_pointer':
                    current = private.load(); folder = self.out/'late-actual-faults'
                    fixture(self.blender, ROOT/'tests/fixtures/blender_source_reference_faults.py',
                        ['--master', private.root/current.master_blend, '--folder', folder], self.out/'late-actual-faults.log', 300)
                    revised = stage_unverified_master(private, folder/'tiny_pose.blend', authorized_source_root=folder,
                        expected_project=current, expected_revision=current.revision)
                    require(revised.project.master_blend != current.master_blend, 'Coherent actual saved fault did not change pointer')
                    observed.append({'actual_fault_sha256': Path(revised.project.master_blend).stem})
                else:
                    writer.execute('SELECT * FROM asset_sources').fetchall()
                    db_hash = digest(database); mtime = database.stat().st_mtime_ns
                    asset = store.load().animations[0].split('#')[0]
                    raw = writer.execute('SELECT license_json FROM asset_sources WHERE asset_id=?', (asset,)).fetchone()[0]
                    policy = json.loads(raw); policy['no_ai'] = False
                    writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?', (json.dumps(policy), asset)); writer.commit()
                    require(digest(database) == db_hash and database.stat().st_mtime_ns == mtime,
                            'Actual committed policy fault did not remain in WAL')
                    require(Path(str(database)+'-wal').stat().st_size > 0, 'No actual committed WAL')
                    observed.append({'main_database_sha256_unchanged': db_hash, 'committed_NoAI_change_in_WAL': True})
                return result

            rejected = None
            try:
                # Inject a real saved-scene/policy change only AFTER the real worker returns.
                plain.inspect_saved_neutral_master = after_verified
                try:
                    try: self.operation(store, database=database)
                    except (AssetPolicyError, ProjectStorageError) as error: rejected = error
                finally:
                    plain.inspect_saved_neutral_master = original_inspect
                require(len(observed) == 1 and rejected is not None, 'Late verified-output fault was not rejected')
                if fault == 'WAL_policy': require(isinstance(rejected, AssetPolicyError), 'Wrong late policy failure')
                else: require('Verified plain body/hand output changed' in str(rejected), 'Wrong coherent pointer failure')
                self.unchanged(store, before)
                self.accepted('late_'+fault, rejected)
            finally:
                if writer is not None: writer.close()
