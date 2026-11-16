"""Faults around real filesystem publication; engine calls use named byte markers."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile
import json
import unittest
import ucc.jobs.unity_export as unity_job
from unittest.mock import patch
from fixtures.unity_export_transaction import UnityTransactionFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.unity_export import export_unity, verify_unity_export_result
from ucc.jobs.skin_material_preparation import _BudgetCancel


class UnityExportTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = UnityTransactionFixture(Path(temporary.name).resolve())
        self.mocks = []
        for item in self.f.patches():
            self.mocks.append(item.start()); self.addCleanup(item.stop)

    def invoke(self, **changes):
        return export_unity(self.f.store, **(self.f.options | changes))

    def test_success_binds_final_files_and_keeps_saved_character_unchanged(self):
        before = self.f.store.file.read_bytes()
        phases = []; result = self.invoke(progress=phases.append)
        receipt = verify_unity_export_result(result)
        self.assertTrue(receipt['export_published']); self.assertTrue(receipt['final_payload_verified'])
        self.assertEqual(phases[-1], 'COMPLETE')
        self.assertEqual(self.f.store.file.read_bytes(), before)
        self.mocks[-1].assert_called_once()
        self.assertFalse((result.destination/'Assets/UCC/source_reference.json').exists())

    def test_stale_revision_or_review_never_launches_worker(self):
        for field, value in (('revision', self.f.request.revision+1), ('project_sha256', 'f'*64)):
            with self.subTest(field=field):
                # Production source resolver rejects stale revisions; mimic that independently.
                if field == 'revision':
                    self.mocks[0].side_effect = ProjectConflict('stale revision')
                with self.assertRaises(ProjectConflict):
                    self.invoke(request=replace(self.f.request, **{field:value}))
                self.mocks[0].side_effect = None
        self.mocks[2].assert_not_called(); self.assertFalse(self.f.destination.path.exists())

    def test_reviewed_executable_mismatch_fails_before_worker(self):
        with self.assertRaises(ValidationError):
            self.invoke(request=replace(self.f.request, unity_executable_sha256='a'*64))
        self.mocks[2].assert_not_called()

    def test_changed_proof_executable_resource_and_source_fail_guard(self):
        for name in ('proof', 'executable', 'source', 'resource'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                f = UnityTransactionFixture(Path(temporary).resolve())
                patches = f.patches(); mocks = [p.start() for p in patches]
                try:
                    target = {'proof':f.proofs/('b'*64+'.json'), 'executable':f.exe,
                              'source':f.sources['expression_library'], 'resource':f.worker}[name]
                    def mutate(*args, **kwargs):
                        target.write_bytes(target.read_bytes()+b'UNIT_MUTATION')
                        return f.prepared
                    mocks[2].side_effect = mutate
                    with self.assertRaises(ProjectStorageError):
                        export_unity(f.store, **f.options)
                    self.assertFalse(f.destination.path.exists())
                finally:
                    for item in reversed(patches): item.stop()

    def test_cancellation_and_one_total_deadline_stop_between_stages(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as temporary:
                f = UnityTransactionFixture(Path(temporary).resolve())
                patches = f.patches(); mocks = [p.start() for p in patches]
                try:
                    cancel = Event()
                    clock = [0.]
                    def stop(*args, **kwargs):
                        if timeout: clock[0] = 2.
                        else: cancel.set()
                        return f.prepared
                    mocks[2].side_effect = stop
                    with patch('ucc.jobs.unity_export.time.monotonic', side_effect=lambda:clock[0]), self.assertRaises(ProjectStorageError):
                        export_unity(f.store, **f.options, cancel=cancel, timeout_s=1 if timeout else 60)
                    self.assertFalse(f.destination.path.exists()); mocks[2].assert_called_once(); mocks[3].assert_not_called()
                finally:
                    for item in reversed(patches): item.stop()

    def test_failure_during_final_verification_rolls_back_owned_folder(self):
        self.mocks[-1].side_effect = ProjectStorageError('UNIT_FINAL_VERIFICATION_FAILURE')
        with self.assertRaisesRegex(ProjectStorageError, 'UNIT_FINAL_VERIFICATION_FAILURE'):
            self.invoke()
        self.assertFalse(self.f.destination.path.exists())
        self.assertEqual(len(list(self.f.root.glob('.ucc-export-*'))), 1)
        self.assertEqual(self.f.store.load(), self.f.project)

    def test_failure_after_success_receipt_withdraws_publication_claim(self):
        def fail(state):
            if state == 'COMPLETE':
                raise OSError('UNIT_COMPLETION_FAILURE')
        with self.assertRaisesRegex(OSError, 'UNIT_COMPLETION_FAILURE'):
            self.invoke(progress=fail)
        self.assertFalse(self.f.destination.path.exists())
        stage, = self.f.root.glob('.ucc-export-*')
        receipt = json.loads((stage/'export_receipt.json').read_text())
        self.assertFalse(receipt['export_published']); self.assertFalse(receipt['final_payload_verified'])
        self.assertTrue(receipt['publication_rolled_back'])

    def test_byte_identical_proof_replacement_is_stale(self):
        proof = self.f.proofs/('b'*64+'.json')
        def mutate(*args, **kwargs):
            saved = proof.read_bytes(); proof.unlink(); proof.write_bytes(saved)
            return self.f.prepared
        self.mocks[2].side_effect = mutate
        with self.assertRaises(ProjectStorageError):
            self.invoke()
        self.assertFalse(self.f.destination.path.exists())

    def test_extra_private_fields_in_engine_recipe_never_publish(self):
        path = self.f.engine.directory/'engine_recipe.json'
        recipe = json.loads(path.read_text()); recipe['PRIVATE_DATA_MUST_NOT_EXPORT'] = 'UNIT_PRIVATE_MARKER'
        path.write_text(json.dumps(recipe))
        with self.assertRaises(ValidationError):
            self.invoke()
        self.assertFalse(self.f.destination.path.exists())

    def test_deadline_and_cancel_inside_initial_digest_are_truthfully_classified(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout):
                clock = [0.]; cancel = Event()
                def expire(*args, **kwargs):
                    if timeout: clock[0] = 2.
                    else: cancel.set()
                    raise ProjectStorageError('Saved-master preview cancelled; UNIT_UNDERLYING_DIGEST')
                with patch('ucc.jobs.unity_export.time.monotonic', side_effect=lambda:clock[0]), \
                        patch('ucc.jobs.unity_export._digest', side_effect=expire):
                    with self.assertRaisesRegex(ProjectStorageError, 'total deadline' if timeout else 'cancelled by caller') as caught:
                        self.invoke(cancel=cancel, timeout_s=1.)
                self.assertIn('UNIT_UNDERLYING_DIGEST', str(caught.exception.__cause__))
                self.assertFalse(self.f.destination.path.exists())
        self.mocks[2].assert_not_called()

    def test_deadline_expiry_inside_postpublication_digest_is_journalled_and_rolled_back(self):
        clock = [0.]
        actual_digest = unity_job._digest
        def expire(path, cancel=None):
            if self.f.destination.path.exists() and Path(path) == self.f.exe:
                clock[0] = 2.
            return actual_digest(path, cancel)
        with patch('ucc.jobs.unity_export.time.monotonic', side_effect=lambda:clock[0]), \
                patch('ucc.jobs.unity_export._digest', side_effect=expire):
            with self.assertRaisesRegex(ProjectStorageError, 'total deadline') as caught:
                self.invoke(timeout_s=1.)
        self.assertFalse(self.f.destination.path.exists())
        self.assertIn('Saved-master preview cancelled', str(caught.exception.__cause__))
        self.assertTrue(any('diagnostics retained' in note for note in caught.exception.__notes__))
        status, = (self.f.store.root/'.ucc-jobs').glob('unity-export-*/job_status.json')
        record = json.loads(status.read_text())
        self.assertEqual(record['failure_reason'], 'total_deadline')
        self.assertTrue(record['total_deadline_exceeded']); self.assertFalse(record['cancelled'])
        self.assertIn('Saved-master preview cancelled', record['raw_error'])
        self.assertIn('total deadline', record['error'])

    def test_nested_budget_deadline_is_distinct_from_actual_user_or_budget_flags(self):
        for mode in ('deadline', 'user', 'budget_flag'):
            with self.subTest(mode=mode):
                clock = [0.]; user = Event()
                inner = _BudgetCancel(user, 1. if mode == 'deadline' else 100.)
                outer = _BudgetCancel(inner, 10. if mode == 'deadline' else 200.)
                actual = unity_job._digest
                def expire(path, budget=None):
                    if mode == 'deadline': clock[0] = 2.
                    elif mode == 'user': user.set()
                    else: inner.set()
                    return actual(path, budget)
                with patch('ucc.jobs.unity_export.time.monotonic', side_effect=lambda:clock[0]), \
                        patch('ucc.jobs.unity_export._digest', side_effect=expire):
                    with self.assertRaisesRegex(ProjectStorageError,
                            'total deadline' if mode == 'deadline' else 'cancelled by caller'):
                        self.invoke(cancel=outer, timeout_s=60.)
                self.assertFalse(self.f.destination.path.exists())
        self.mocks[2].assert_not_called()


if __name__ == '__main__':
    unittest.main()
