"""Private working copies with nonshipping saved project / file fixtures only."""

from dataclasses import replace
import os
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from fixtures.target_action_logic import TargetFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.jobs.animation_reference_storage import _binding_path
from ucc.jobs.export_destination import rename_new
from ucc.jobs.private_target_copy import _read_exact
from ucc.jobs.private_target_copy import create_private_target_copy
from ucc.jobs.target_action_storage import read_target_action_binding


class PrivateTargetCopyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fixture = TargetFixture(Path(temp.name).resolve())
        self.store = self.fixture.store
        self.output = self.fixture.root/'workspace-copy'

    def copy(self, **changes):
        options = {'expected_project':self.fixture.project, 'destination':self.output} | changes
        with patch('ucc.jobs.runner.run_process', side_effect=AssertionError('Copy must not launch a worker')):
            return create_private_target_copy(self.store, **options)

    def test_copies_exact_saved_identity_history_and_actions_with_no_private_workspaces(self):
        directory, binding = self.fixture.payload()
        untouched = ['.ucc-jobs', '.ucc-candidates']
        for name in untouched:
            marker = self.store.root/name/'private.txt'
            marker.parent.mkdir()
            marker.write_bytes(b'Nonshipping work marker')
        before = {path.relative_to(self.store.root):path.read_bytes()
                  for path in self.store.root.rglob('*') if path.is_file()}
        self.assertEqual(self.copy(), self.output)
        target = ProjectStore(self.output)
        self.assertEqual(target.load(), self.fixture.project)
        self.assertEqual(target.file.read_bytes(), self.store.file.read_bytes())
        self.assertEqual(read_target_action_binding(target, binding.sha256), binding)
        self.assertTrue((self.output/directory.relative_to(self.store.root)).is_dir())
        self.assertEqual({path.relative_to(self.output):path.read_bytes()
                          for path in self.output.rglob('*') if path.is_file()},
                         {path:payload for path,payload in before.items() if path.parts[0] not in untouched})
        self.assertEqual({path.relative_to(self.store.root):path.read_bytes()
                          for path in self.store.root.rglob('*') if path.is_file()}, before)

    def test_refuses_unknown_files_missing_bindings_and_nonlocal_targets(self):
        unsupported = self.store.root/'unsupported.txt'
        unsupported.write_bytes(b'Nonshipping unknown source')
        with self.assertRaisesRegex(ValidationError, 'unsupported'):
            self.copy()
        unsupported.unlink()
        with self.assertRaisesRegex(ValidationError, 'separate'):
            self.copy(destination=self.store.root/'nested')
        with self.assertRaisesRegex(ValidationError, 'absolute local'):
            self.copy(destination=Path('relative-project'))
        _binding_path(self.store, self.fixture.clip_id).unlink()
        with self.assertRaisesRegex(ValidationError, 'no saved animation reference'):
            self.copy()
        self.assertFalse(self.output.exists())

    def test_refuses_incomplete_retained_actions_and_shared_files(self):
        directory, _ = self.fixture.payload()
        (directory/'native_mapping.json').unlink()
        with self.assertRaisesRegex(ProjectStorageError, 'saved file inventory'):
            self.copy()
        os.link(self.fixture.master, self.fixture.root/'shared-master.blend')
        with self.assertRaisesRegex(ProjectStorageError, 'independent local'):
            self.copy()
        self.assertFalse(self.output.exists())

    def test_preserves_a_destination_created_by_a_concurrent_writer(self):
        def collision(stage, target):
            target.mkdir()
            (target/'keep.txt').write_bytes(b'Unrelated synthetic destination')
            return rename_new(stage, target)

        with patch('ucc.jobs.private_target_copy.rename_new', collision):
            with self.assertRaises(ProjectStorageError):
                self.copy()
        self.assertEqual((self.output/'keep.txt').read_bytes(), b'Unrelated synthetic destination')
        self.assertFalse(list(self.output.parent.glob('.ucc-export-*')))

    def test_withdraws_own_copy_on_source_edit_at_publication(self):
        def change_source(stage, target):
            rename_new(stage, target)
            old = self.store.load()
            self.store.save(replace(old, name='Concurrent edit', revision=old.revision+1),
                            expected_revision=old.revision)

        with patch('ucc.jobs.private_target_copy.rename_new', change_source):
            with self.assertRaisesRegex(ProjectConflict, 'inputs changed'):
                self.copy()
        self.assertEqual(self.store.load().name, 'Concurrent edit')
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.output.parent.glob('.ucc-export-*')))

    def test_cancellation_preserves_concurrent_foreign_output(self):
        cancel = Event()
        foreign = self.output/'keep.txt'

        def cancel_publish(stage, target):
            rename_new(stage, target)
            foreign.write_bytes(b'Unrelated synthetic file')
            cancel.set()

        with patch('ucc.jobs.private_target_copy.rename_new', cancel_publish):
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled') as failure:
                self.copy(cancel=cancel)
        self.assertEqual(foreign.read_bytes(), b'Unrelated synthetic file')
        self.assertTrue(any(str(self.output) in note for note in failure.exception.__notes__))

    def test_mid_file_read_failure_cleans_exact_partial_but_preserves_foreign_edit(self):
        rewritten = b'!' * 17

        def interrupt(path, stamp, budget, write=None):
            if write is None:
                return _read_exact(path, stamp, budget)
            with path.open('rb') as source:
                write(source.read(len(rewritten)))
            if edit:
                staged = next(self.output.parent.glob('.ucc-export-*'))
                partial = next(item for item in staged.rglob('*') if item.is_file())
                with partial.open('r+b') as foreign:
                    foreign.write(rewritten)
            raise OSError('Synthetic interrupted source read')

        with patch('ucc.jobs.private_target_copy._read_exact', interrupt):
            for edit in (False, True):
                with self.subTest(foreign_edit=edit), self.assertRaises(ProjectStorageError) as failure:
                    self.copy()
                self.assertFalse(self.output.exists())
                stages = list(self.output.parent.glob('.ucc-export-*'))
                self.assertEqual(len(stages), int(edit))
                if edit:
                    partial = next(item for item in stages[0].rglob('*') if item.is_file())
                    self.assertEqual(partial.read_bytes(), rewritten)
                    self.assertTrue(any(str(stages[0]) in note for note in failure.exception.__notes__))

    def test_cleanup_preserves_empty_directory_replaced_during_cleanup(self):
        (self.store.root/'materials').mkdir()
        cancel = Event()
        displaced = self.fixture.root/'displaced-owned-directory'
        replaced = self.output/'materials'
        unlink = Path.unlink

        def cancel_after_publish(stage, target):
            rename_new(stage, target)
            cancel.set()

        def replace_directory_on_first_cleanup_unlink(path, *args, **kwargs):
            if path.is_relative_to(self.output) and not displaced.exists():
                replaced.rename(displaced)
                replaced.mkdir()
            return unlink(path, *args, **kwargs)

        with (patch('ucc.jobs.private_target_copy.rename_new', cancel_after_publish),
              patch.object(Path, 'unlink', replace_directory_on_first_cleanup_unlink)):
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled') as failure:
                self.copy(cancel=cancel)
        self.assertTrue(replaced.is_dir())
        self.assertTrue(displaced.is_dir())
        self.assertTrue(any('folder changed during cleanup' in note for note in failure.exception.__notes__))
