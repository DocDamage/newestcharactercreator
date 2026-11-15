"""Real Qt dispatch/watchers with structural fixtures; no geometry/GPU claim."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.reference_expression_preview import ReferenceExpressionPreview
import test_hand_qt as legacy

if legacy.QApplication is not None:
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
    from ucc.desktop.expression_workflow import start_expression, finish_expression
    from ucc.desktop.expression_binding import clear_expression
    from ucc.desktop.reference_expression_binding import bind_referenced_expression, catalog_signature


@unittest.skipIf(legacy.QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 unavailable')
class ReferencedExpressionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if legacy.QApplication is None: raise RuntimeError('Required Qt unavailable: '+legacy.IMPORT_ERROR)
        cls.app = legacy.QApplication.instance() or legacy.QApplication(['referenced-expression-tests'])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.f = ReferenceMasterFixture(self.root/'fixture')
        self.controller = DesktopController(); self.controller.open(self.f.store.root)
        self.window = MainWindow(self.controller); self.addCleanup(self.close_window)
        self.window._catalog_path = lambda: self.f.database
        self.window._blender_executable = self.f.executable
        private = self.f.store.root/'.ucc-jobs/rx-unit'; private.mkdir(parents=True)
        self.evidence = private/'unit-only-receipt.json'; self.evidence.write_text('{}', encoding='utf-8')
        # This DTO is only for publication/ownership logic. Cache validation is
        # mocked explicitly; it is not usable skin or saved-worker evidence.
        self.result = ReferenceExpressionPreview(self.controller.require_project(), 'a'*64,
            SimpleNamespace(store=SimpleNamespace(root=private)), SimpleNamespace(cache=None), (), {}, (),
            private/'unit-only-receipt.json', 'b'*64, self.f.database.resolve(), (self.f.source.resolve(),))
        self.window.expression_viewer = SimpleNamespace(clear=Mock())

    def close_window(self):
        clear_expression(self.window); self.window.deleteLater(); self.app.processEvents()

    def bind(self):
        with patch('ucc.desktop.reference_expression_binding.check_referenced_expression_preview') as check:
            bind_referenced_expression(self.window, self.result)
        self.assertEqual(check.call_count, 2)
        self.window.expression_viewer.clear.reset_mock()

    def wait_clear(self):
        deadline = time.monotonic()+2
        while self.window._expression_preview is not None and time.monotonic()<deadline:
            self.app.processEvents(); time.sleep(.01)
        self.assertIsNone(self.window._expression_preview)
        self.window.expression_viewer.clear.assert_called()

    def drain(self):
        for _ in range(20): self.app.processEvents(); time.sleep(.005)

    def test_existing_controls_edit_save_and_capture_reference_preview_dispatch(self):
        controls = self.window.character.expressions
        self.assertFalse(controls.prepare.isEnabled()); self.assertTrue(controls.preview.isEnabled())
        controls.values['mouth_open'].setValue(.375); controls.values['mouth_open'].editingFinished.emit()
        self.assertTrue(self.controller.dirty); self.assertFalse(controls.preview.isEnabled())
        self.window.save_project(); self.assertTrue(controls.preview.isEnabled())
        saved = self.controller.require_project()
        with patch.object(self.window, '_submit') as submit: controls.preview.click()
        self.assertEqual(submit.call_args.args[0], 'expression_preview')
        with (patch('ucc.desktop.expression_workflow.discover_face_data', return_value=self.root),
              patch('ucc.desktop.expression_workflow.preview_referenced_expressions', return_value='verified') as fresh,
              patch('ucc.desktop.expression_workflow.preview_saved_expressions') as old):
            self.assertEqual(submit.call_args.args[1](), 'verified')
        old.assert_not_called()
        self.assertEqual(fresh.call_args.args[0].root, self.f.store.root)
        self.assertEqual(fresh.call_args.args[1], self.f.database)
        self.assertEqual(fresh.call_args.kwargs['expected_revision'], saved.revision)
        self.assertEqual(fresh.call_args.kwargs['expected_master_blend'], saved.master_blend)
        self.assertIs(fresh.call_args.kwargs['cancel'], submit.call_args.kwargs['cancel'])

    def test_dirty_unsupported_and_prepare_with_references_remain_guarded(self):
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_expression(self.window, prepare=True)
        submit.assert_not_called(); error.assert_called_once()
        self.controller.rename('Dirty')
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_expression(self.window)
        submit.assert_not_called(); self.assertIn('Save', error.call_args.args[0])

    def test_preview_start_keeps_saved_history_actions_locked(self):
        self.controller.rename('Saved undo history'); self.controller.save(); self.window.refresh_project()
        def submit(kind, operation, **kwargs):
            self.window._work_kind = kind; self.window._busy_changed(True)
        with patch.object(self.window, '_submit', side_effect=submit): start_expression(self.window)
        for action in (self.window.undo_action, self.window.redo_action, self.window.save_action,
                       self.window.new_action, self.window.open_action):
            self.assertFalse(action.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled()); self.window._busy_changed(False)

    def test_wrapper_owner_is_used_by_refresh_instead_of_private_revision(self):
        self.window._expression_preview = self.result
        self.window.refresh_project(); self.assertIs(self.window._expression_preview, self.result)
        self.controller.rename('Changed owner'); self.window.refresh_project()
        self.assertIsNone(self.window._expression_preview)

    def test_publication_calls_new_guard_twice_and_stale_owner_is_rejected(self):
        self.bind(); self.assertIs(self.window._expression_preview, self.result)
        self.assertIn(str(self.f.source), self.window._reference_expression_watcher.files())
        self.assertIn(str(self.evidence), self.window._reference_expression_watcher.files())
        self.controller.rename('Unsaved')
        with self.assertRaises(ProjectConflict): bind_referenced_expression(self.window, self.result)

    def test_actual_registered_source_file_change_revokes_cpu_and_gpu(self):
        self.bind(); self.f.source.write_bytes(b'changed test-owned source'); self.wait_clear()

    def test_actual_private_evidence_and_source_binding_changes_revoke(self):
        self.bind(); self.evidence.write_text('{"changed":true}', encoding='utf-8'); self.wait_clear()
        self.bind()
        binding = next((self.f.store.root/'animations/references').glob('*.json'))
        binding.write_text('{}', encoding='utf-8'); self.wait_clear()

    def test_unrelated_catalog_parent_file_and_read_only_lookup_do_not_self_invalidate(self):
        self.bind(); (self.f.database.parent/'unrelated-note.txt').write_text('not an input', encoding='utf-8')
        from ucc.jobs.catalog_clip import _saved_reference
        _saved_reference(self.f.database, self.f.clip_id, self.f.source_sha, self.f.policy)
        self.drain(); self.assertIs(self.window._expression_preview, self.result)

    def test_delayed_directory_notifications_require_an_actual_bound_change(self):
        from ucc.desktop.reference_expression_binding import _changed
        self.bind()
        directory = self.f.store.root/'expressions'
        _changed(self.window, str(directory))
        self.assertIs(self.window._expression_preview, self.result)
        (directory/'new-file.json').write_text('{}', encoding='utf-8')
        _changed(self.window, str(directory))
        self.assertIsNone(self.window._expression_preview)

    def test_empty_WAL_is_armed_and_later_real_committed_policy_write_revokes(self):
        self.bind(); writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA wal_autocheckpoint=0'); writer.execute('SELECT * FROM asset_sources').fetchall()
        self.drain(); self.assertIs(self.window._expression_preview, self.result)
        before = self.f.database.stat().st_mtime_ns
        policy = replace(self.f.policy, no_ai=False)
        writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?',
            (json.dumps(policy.to_dict()), self.f.reference.asset_id)); writer.commit()
        self.assertEqual(self.f.database.stat().st_mtime_ns, before)
        self.wait_clear()

    def test_catalog_signature_ignores_only_empty_WAL_not_database_changes(self):
        before = catalog_signature(self.f.database); wal = Path(str(self.f.database)+'-wal')
        wal.write_bytes(b''); self.assertEqual(catalog_signature(self.f.database), before)
        wal.write_bytes(b'not-empty-WAL-data'*4); self.assertNotEqual(catalog_signature(self.f.database), before)

    def test_path_budget_and_failed_watcher_attachment_cannot_publish(self):
        with patch('ucc.desktop.reference_expression_binding.MAX_PATHS', 2):
            with self.assertRaises(ProjectStorageError): self.bind()
        with (patch('ucc.desktop.reference_expression_binding.check_referenced_expression_preview'),
              patch('ucc.desktop.reference_expression_binding.QFileSystemWatcher.addPaths', return_value=['unwatched'])):
            with self.assertRaises(ProjectStorageError): bind_referenced_expression(self.window, self.result)
        self.assertIsNone(self.window._expression_preview)

    def _parent_replacement(self, *, catalog=False, hardlink=False):
        folder = self.root/'external'; folder.mkdir()
        leaf = folder/('catalog.sqlite3' if catalog else 'source.fbx')
        leaf.write_bytes((self.f.database if catalog else self.f.source).read_bytes())
        if catalog:
            self.result = replace(self.result, database_path=leaf.resolve())
            self.window._catalog_path = lambda: leaf
        else:
            self.result = replace(self.result, source_paths=(leaf.resolve(),))
        self.bind(); self.drain(); self.assertIs(self.window._expression_preview, self.result)
        watcher = self.window._reference_expression_watcher; notifications = []
        watcher.directoryChanged.connect(notifications.append)
        before = leaf.stat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        # An OS-lost file watch must not defeat the directory fallback.
        self.assertTrue(watcher.removePath(str(leaf)))
        self.assertIn(str(folder), watcher.directories())
        relocated = self.root/'relocated'
        self.assertTrue(folder.resolve().is_relative_to(self.root.resolve()))
        self.assertTrue(relocated.resolve().is_relative_to(self.root.resolve()))
        folder.rename(relocated)
        try:
            if hardlink:
                folder.mkdir(); os.link(relocated/leaf.name, leaf)
            elif os.name == 'nt':
                quote = lambda p: "'"+str(p).replace("'", "''")+"'"
                command = ('New-Item -ItemType Junction -Path '+quote(folder)+' -Target '+quote(relocated)
                           +' -ErrorAction Stop | Out-Null')
                subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                    check=True, capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                folder.symlink_to(relocated, target_is_directory=True)
            after = leaf.stat()
            self.assertEqual(identity, (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
            self.assertEqual(leaf.resolve() == leaf, hardlink)
            deadline = time.monotonic()+2
            while self.window._expression_preview is not None and time.monotonic() < deadline:
                self.app.processEvents(); time.sleep(.01)
            self.assertTrue(notifications, 'Parent replacement produced no observed ancestor notification')
            self.assertTrue(self.window._expression_preview is None, 'Parent replacement retained publication')
            self.window.expression_viewer.clear.assert_called()
        finally:
            if hardlink:
                leaf.unlink(); folder.rmdir()
            elif folder.exists():
                if os.name == 'nt': os.rmdir(folder)  # Remove only the junction, never its target.
                else: folder.unlink()

    def test_source_parent_redirect_revokes_with_unchanged_file_identity(self):
        self._parent_replacement()

    def test_catalog_parent_redirect_revokes_with_unchanged_database_identity(self):
        self._parent_replacement(catalog=True)

    def test_replaced_real_parent_with_same_hardlinked_file_revokes(self):
        self._parent_replacement(hardlink=True)


if __name__ == '__main__': unittest.main()
