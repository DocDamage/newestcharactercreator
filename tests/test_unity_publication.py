"""Independent transaction fault injection; fake workers never prove engine quality."""
from pathlib import Path
from threading import Event
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from fixtures.unity_export_transaction import UnityTransactionFixture
from ucc.core.errors import ProjectStorageError
from ucc.jobs.export_destination import rename_new
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.unity_export import export_unity


class UnityPublicationFaultTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.f = UnityTransactionFixture(self.root)
        self.patches = self.f.patches()
        self.mocks = [p.start() for p in self.patches]
        for active in self.patches:
            self.addCleanup(active.stop)

    def invoke(self, **options):
        return export_unity(self.f.store, **(self.f.options | options))

    def assert_originals_and_no_success(self):
        self.assertEqual(self.f.store.load(), self.f.project)
        self.assertFalse(self.f.destination.path.exists())
        statuses = list((self.f.store.root/'.ucc-jobs').glob('unity-export-*/job_status.json'))
        if statuses:
            record = json.loads(statuses[0].read_bytes())
            self.assertEqual(record['state'], 'FAILED')
            self.assertFalse(record['export_published'])

    def test_atomic_publication_collision_preserves_raced_in_folder(self):
        marker = self.f.destination.path/'UNIT_UNRELATED_DATA'
        def race(source, destination):
            if destination == self.f.destination.path:
                destination.mkdir()
                marker.write_bytes(b'UNIT_NEVER_REPLACE')
            rename_new(source, destination)
        with patch('ucc.jobs.unity_export.rename_new', side_effect=race):
            with self.assertRaises(OSError):
                self.invoke()
        self.assertEqual(marker.read_bytes(), b'UNIT_NEVER_REPLACE')
        self.mocks[-1].assert_not_called()
        self.assertEqual(self.f.store.load(), self.f.project)

    def test_changed_file_immediately_after_rename_rolls_owned_folder_back(self):
        def mutate(source, destination):
            rename_new(source, destination)
            if destination == self.f.destination.path:
                (destination/'Assets/UCC/CharacterSkin.asset').write_bytes(b'UNIT_CORRUPTED_AFTER_RENAME')
        with patch('ucc.jobs.unity_export.rename_new', side_effect=mutate):
            with self.assertRaises(ProjectStorageError):
                self.invoke()
        self.assert_originals_and_no_success()
        self.mocks[-1].assert_not_called()
        self.assertEqual(len(list(self.root.glob('.ucc-export-*'))), 1)

    def test_runtime_failure_after_publication_rolls_back_without_success_receipt(self):
        self.mocks[-1].side_effect = ProjectStorageError('UNIT_FINAL_RUNTIME_REJECTED')
        with self.assertRaisesRegex(ProjectStorageError, 'UNIT_FINAL_RUNTIME_REJECTED'):
            self.invoke()
        self.assert_originals_and_no_success()
        retained = list(self.root.glob('.ucc-export-*'))
        self.assertEqual(len(retained), 1)
        self.assertFalse((retained[0]/'export_receipt.json').exists())

    def test_cancel_after_publication_uses_same_rollback_path(self):
        cancel = Event()
        def progress(state):
            if state == 'PUBLISHED_RUNTIME_VERIFICATION':
                cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, 'cancelled'):
            self.invoke(cancel=cancel, progress=progress)
        self.assert_originals_and_no_success()
        self.mocks[-1].assert_not_called()

    def test_one_total_deadline_cannot_be_reset_at_next_stage(self):
        clock = [100.0]
        def prepare(*args, **options):
            self.assertLessEqual(options['timeout_s'], 1.0)
            clock[0] += 2.0
            return self.f.prepared
        self.mocks[2].side_effect = prepare
        with patch('ucc.jobs.unity_export.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(ProjectStorageError, 'deadline'):
                self.invoke(timeout_s=1.0)
        self.assert_originals_and_no_success()
        self.mocks[3].assert_not_called()

    def test_replaced_byte_identical_ancestral_proof_is_rejected(self):
        proof = self.f.store.root/'expressions/inspections/UNIT_ANCESTRAL_PROOF.json'
        proof.parent.mkdir(parents=True)
        proof.write_bytes(b'{"UNIT_NONSHIPPING_PROOF":true}')
        def progress(state):
            if state == 'SOURCE_PREPARATION':
                replacement = proof.with_suffix('.replacement')
                replacement.write_bytes(proof.read_bytes())
                os.replace(replacement, proof)
        with self.assertRaisesRegex(ProjectStorageError, 'changed|closure'):
            self.invoke(progress=progress)
        self.assert_originals_and_no_success()
        self.mocks[2].assert_not_called()

    def test_final_journal_error_rolls_back_completed_payload(self):
        actual_replace = os.replace
        def fail_complete(source, destination):
            if Path(source).name == 'job_status.tmp' and json.loads(Path(source).read_bytes())['state'] == 'COMPLETE':
                raise OSError('UNIT_COMPLETION_JOURNAL_FAILURE')
            return actual_replace(source, destination)
        with patch('ucc.jobs.unity_export.os.replace', side_effect=fail_complete):
            with self.assertRaisesRegex(OSError, 'UNIT_COMPLETION_JOURNAL_FAILURE'):
                self.invoke()
        self.assert_originals_and_no_success()

    def test_rollback_does_not_adopt_external_destination_replacement(self):
        relocated = self.root/'UNIT_OWNED_OUTPUT_MOVED_EXTERNALLY'
        marker = self.f.destination.path/'UNIT_UNRELATED_DATA'
        def replace_destination(*args, **options):
            rename_new(self.f.destination.path, relocated)
            self.f.destination.path.mkdir()
            marker.write_bytes(b'UNIT_NEVER_TOUCH')
            raise ProjectStorageError('UNIT_DESTINATION_REPLACED_EXTERNALLY')
        self.mocks[-1].side_effect = replace_destination
        with self.assertRaisesRegex(ProjectStorageError, 'UNIT_DESTINATION_REPLACED_EXTERNALLY'):
            self.invoke()
        self.assertEqual(marker.read_bytes(), b'UNIT_NEVER_TOUCH')
        self.assertTrue(relocated.is_dir())
        self.assertEqual(self.f.store.load(), self.f.project)

    def create_directory_redirect(self, link, target):
        # Both final absolute paths are disposable children of this fixture.
        self.assertTrue(link.is_absolute() and target.is_absolute())
        self.assertTrue(link.is_relative_to(self.root) and target.is_relative_to(self.root))
        self.assertEqual(link.parent.resolve(), link.parent)
        self.assertTrue(target.is_dir() and target.resolve() == target)
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)

    @staticmethod
    def remove_directory_redirect(link):
        if os.name == 'nt':
            os.rmdir(link)  # Unlink the junction only; never recurse into its target.
        else:
            link.unlink()

    def test_real_export_parent_redirect_rejects_without_touching_either_target(self):
        parent = self.root/'UNIT_EXPORT_PARENT'
        parent.mkdir()
        (parent/'UNIT_ORIGINAL').write_bytes(b'UNIT_PARENT_ORIGINAL')
        original = self.root/'UNIT_EXPORT_PARENT_SAVED'
        target = self.root/'UNIT_REDIRECT_TARGET'
        target.mkdir()
        marker = target/'UNIT_EXTERNAL'
        marker.write_bytes(b'UNIT_REDIRECT_TARGET_UNCHANGED')
        destination = plan_destination(parent/'output', self.f.store.root)
        redirected = [False]
        def progress(state):
            if state == 'SOURCE_PREPARATION':
                parent.rename(original)
                self.create_directory_redirect(parent, target)
                redirected[0] = True
        try:
            with self.assertRaisesRegex(ProjectStorageError, 'changed|redirected'):
                self.invoke(destination=destination, progress=progress)
            self.assertFalse((target/'output').exists())
            self.assertEqual(marker.read_bytes(), b'UNIT_REDIRECT_TARGET_UNCHANGED')
            self.assertEqual((original/'UNIT_ORIGINAL').read_bytes(), b'UNIT_PARENT_ORIGINAL')
            self.mocks[2].assert_not_called()
        finally:
            if redirected[0]:
                self.remove_directory_redirect(parent)
                original.rename(parent)
        self.assert_originals_and_no_success()

    def test_real_proof_directory_redirect_rejects_and_preserves_original_proof(self):
        directory = self.f.store.root/'expressions/inspections'
        directory.mkdir(parents=True)
        proof = directory/'UNIT_PROOF.json'
        proof.write_bytes(b'{"UNIT_NONSHIPPING_PROOF":true}')
        original = self.root/'UNIT_ORIGINAL_PROOF_DIRECTORY'
        target = self.root/'UNIT_REDIRECT_PROOF_TARGET'
        target.mkdir()
        (target/proof.name).write_bytes(proof.read_bytes())
        redirected = [False]
        def progress(state):
            if state == 'SOURCE_PREPARATION':
                directory.rename(original)
                self.create_directory_redirect(directory, target)
                redirected[0] = True
        try:
            with self.assertRaisesRegex(ProjectStorageError, 'changed|redirected'):
                self.invoke(progress=progress)
            self.assertEqual((original/proof.name).read_bytes(), b'{"UNIT_NONSHIPPING_PROOF":true}')
            self.assertEqual((target/proof.name).read_bytes(), b'{"UNIT_NONSHIPPING_PROOF":true}')
            self.mocks[2].assert_not_called()
        finally:
            if redirected[0]:
                self.remove_directory_redirect(directory)
                original.rename(directory)
        self.assert_originals_and_no_success()
