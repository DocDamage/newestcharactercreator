"""Transaction doubles only; actual engine acceptance is separately recorded."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

from fixtures.godot_transaction_contract import GodotTransactionFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.jobs.godot_candidate import verify_staged_godot_candidate
from ucc.jobs.runner import ProcessOutcome, WorkerFailure


class GodotCandidateTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = GodotTransactionFixture(Path(self.temp.name).resolve())
        self.calls = []

    def doubles(self, callback=None):
        stack = ExitStack(); self.addCleanup(stack.close)
        # These synthetic bytes cannot pass physical source/geometry checks.
        # Mock only those boundaries; exercise real copies, revision checks,
        # permissions, identities, journal and final filesystem transaction.
        stack.enter_context(patch('ucc.jobs.godot_candidate_inputs.project_sources',
                                 return_value={'master': self.f.master}))
        stack.enter_context(patch('ucc.jobs.godot_candidate_inputs.validate_candidate_files'))
        stack.enter_context(patch('ucc.jobs.godot_candidate.validate_candidate_files'))
        stack.enter_context(patch('ucc.jobs.godot_candidate.configuration', return_value={'unit_double': True}))
        stack.enter_context(patch('ucc.jobs.godot_candidate.verification', return_value={'unit_double': True}))

        def process(command, workdir, **kwargs):
            self.calls.append(workdir.name)
            workdir.mkdir(); (workdir/'stdout.log').write_text('UNIT PROCESS DOUBLE')
            engine = Path(command[command.index('--path')+1])
            if workdir.name == 'actual-verification':
                (engine/'verification.json').write_text('{"unit_double":"NOT_ENGINE_EVIDENCE"}')
            if callback:
                result = callback(workdir.name, engine)
                if result is not None:
                    return result
            return ProcessOutcome(0, 'UNIT ONLY', '', .001)

        return stack.enter_context(patch('ucc.jobs.godot_candidate.run_process', side_effect=process))

    def assert_originals(self):
        self.assertEqual(self.f.store.file.read_bytes(), self.f.original_metadata)
        self.assertEqual(self.f.master.read_bytes(), self.f.original_master)
        self.assertEqual((self.f.prior/'unit-marker').read_bytes(), b'PREVIOUS_UNIT_CANDIDATE_NO_ENGINE_CLAIM')

    def assert_no_new_candidate(self):
        self.assertFalse((self.f.prior.parent/self.f.request.job_id).exists())

    def test_success_is_atomic_private_candidate_not_project_or_engine_approval(self):
        self.doubles()
        result = verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertFalse(result.engine_import_verified)
        self.assertEqual(self.calls, ['initial-import', 'configure-import', 'configured-import', 'actual-verification'])
        self.assertTrue(result.directory.is_dir())
        work = self.f.store.root/'.ucc-jobs'/('godot-'+self.f.request.job_id)
        self.assertFalse((work/'engine').exists())
        self.assertEqual(json.loads((work/'job_status.json').read_text())['state'], 'PRIVATE_CANDIDATE_VERIFIED')
        self.assert_originals()

    def test_pre_cancel_and_stale_revision_launch_no_process(self):
        process = self.doubles(); cancel = Event(); cancel.set()
        with self.assertRaises(ProjectStorageError):
            verify_staged_godot_candidate(self.f.store, self.f.request, cancel=cancel, **self.f.kwargs())
        with self.assertRaises(ProjectConflict):
            verify_staged_godot_candidate(self.f.store, replace(self.f.request, revision=2), **self.f.kwargs())
        process.assert_not_called(); self.assert_no_new_candidate(); self.assert_originals()

    def test_live_source_mutation_stops_before_publication(self):
        def mutate(phase, engine):
            if phase == 'configure-import':
                self.f.motion.write_bytes(b'UNIT_SOURCE_CHANGED_DURING_JOB')
        self.doubles(mutate)
        with self.assertRaisesRegex(ProjectStorageError, 'identity changed'):
            verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertEqual(len(self.calls), 2)
        self.assert_no_new_candidate(); self.assert_originals()

    def test_midflight_cancel_and_process_failure_preserve_previous_candidate(self):
        cancel = Event()
        def stop(phase, engine):
            if phase == 'initial-import':
                cancel.set()
                return ProcessOutcome(None, '', '', .001, cancelled=True)
        self.doubles(stop)
        with self.assertRaises(WorkerFailure):
            verify_staged_godot_candidate(self.f.store, self.f.request, cancel=cancel, **self.f.kwargs())
        self.assert_no_new_candidate(); self.assert_originals()

    def test_total_deadline_does_not_reset_between_phases(self):
        def delay(phase, engine):
            time.sleep(.12)
        self.doubles(delay)
        with self.assertRaisesRegex(WorkerFailure, 'total time limit'):
            verify_staged_godot_candidate(self.f.store, self.f.request, timeout_s=.1, **self.f.kwargs())
        self.assertLessEqual(len(self.calls), 1)
        self.assert_no_new_candidate(); self.assert_originals()

    def test_nonzero_process_exit_does_not_publish_any_candidate(self):
        self.doubles(lambda phase, engine: ProcessOutcome(13, '', 'UNIT PROCESS FAILURE', .001))
        with self.assertRaises(WorkerFailure):
            verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertEqual(len(self.calls), 1)
        self.assert_no_new_candidate(); self.assert_originals()

    def test_unrelated_project_directory_entry_does_not_invalidate_bound_inputs(self):
        def unrelated(phase, engine):
            if phase == 'initial-import':
                (self.f.store.root/'unrelated-unit-note.txt').write_text('Unrelated file, not an input')
        self.doubles(unrelated)
        result = verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertTrue(result.directory.is_dir())
        self.assert_originals()

    def test_contended_commit_lock_uses_remaining_job_deadline(self):
        self.doubles()
        lock = self.f.store.root/'.project.ucc.lock'
        lock.write_text('UNIT_OTHER_EDITOR_LOCK_DO_NOT_REMOVE')
        started = time.monotonic()
        with self.assertRaises((ProjectConflict, WorkerFailure)):
            verify_staged_godot_candidate(self.f.store, self.f.request, timeout_s=.1, **self.f.kwargs())
        self.assertLess(time.monotonic()-started, 1.5)
        self.assertEqual(lock.read_text(), 'UNIT_OTHER_EDITOR_LOCK_DO_NOT_REMOVE')
        self.assert_no_new_candidate(); self.assert_originals()

    def test_competing_project_save_is_retained_and_candidate_is_not_published(self):
        def save(phase, engine):
            if phase == 'configure-import':
                current = self.f.store.load()
                self.f.store.save(replace(current, name='Other editor saved this', revision=current.revision+1),
                                  expected_revision=current.revision)
        self.doubles(save)
        with self.assertRaises(ProjectConflict):
            verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertEqual(self.f.store.load().name, 'Other editor saved this')
        self.assertEqual(self.f.master.read_bytes(), self.f.original_master)
        self.assert_no_new_candidate()

    def test_commit_failure_keeps_staging_and_retry_cannot_overwrite_evidence(self):
        self.doubles()
        with patch('ucc.jobs.godot_candidate.os.rename', side_effect=OSError('unit rename fault')):
            with self.assertRaisesRegex(OSError, 'unit rename fault'):
                verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        work = self.f.store.root/'.ucc-jobs'/('godot-'+self.f.request.job_id)
        self.assertTrue((work/'engine').is_dir())
        previous = sha256((work/'job_status.json').read_bytes()).hexdigest()
        with self.assertRaisesRegex(ProjectStorageError, 'already exists'):
            verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assertEqual(previous, sha256((work/'job_status.json').read_bytes()).hexdigest())
        self.assert_no_new_candidate(); self.assert_originals()

    def test_failure_after_rename_rolls_candidate_back_into_private_staging(self):
        self.doubles()
        real_replace = __import__('os').replace
        def replace_status(source, destination):
            if b'PRIVATE_CANDIDATE_VERIFIED' in Path(source).read_bytes():
                raise OSError('unit final-journal fault')
            return real_replace(source, destination)
        with patch('ucc.jobs.godot_candidate.os.replace', side_effect=replace_status):
            with self.assertRaisesRegex(OSError, 'unit final-journal fault'):
                verify_staged_godot_candidate(self.f.store, self.f.request, **self.f.kwargs())
        self.assert_no_new_candidate(); self.assert_originals()

    def test_external_producer_source_guard_rechecked_under_final_commit_lock(self):
        self.doubles()
        calls = []
        def source_guard():
            calls.append(len(self.calls))
            if len(calls) == 6:
                raise ProjectStorageError('unit external original source changed before commit')
        with self.assertRaisesRegex(ProjectStorageError, 'external original'):
            verify_staged_godot_candidate(self.f.store, self.f.request, source_guard=source_guard, **self.f.kwargs())
        self.assertEqual(calls, [0, 1, 2, 3, 4, 4])
        self.assert_no_new_candidate(); self.assert_originals()
