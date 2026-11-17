"""Saved-image UI lifecycle faults; synthetic bytes and doubled native authority."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ucc.library.provenance import LicensePolicy
from ucc.export.godot_candidate_contract import EngineInputPermission
from fixtures.godot_saved_preview_widget_logic import synthetic_loaded

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QPlainTextEdit
    from ucc.desktop.target_action_dialog import TargetActionDialog
    from ucc.desktop.godot_saved_preview_selection import ReviewedSavedPreviewFiles, SavedPreviewPolicyDialog
    from ucc.desktop import godot_saved_preview_workflow as flow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class SavedPreviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Saved preview tests require Qt')
        cls.app = QApplication.instance() or QApplication(['saved-preview-workflow-tests'])

    def test_new_action_needs_an_explicit_binding_and_fresh_source_confirmation(self):
        dialog = TargetActionDialog(('TEST_CLIP',))
        self.addCleanup(dialog.deleteLater)
        review = SimpleNamespace(source=SimpleNamespace(clip_id='TEST_CLIP',source_sha256='a'*64),
            policy=LicensePolicy('Synthetic author','Nonshipping fixture','unit:test',reviewed=True,local_preview_allowed=True))
        dialog.set_review(review,(SimpleNamespace(clip_id='TEST_CLIP',binding_sha256='b'*64),))
        self.assertFalse(dialog.godot_saved.isEnabled())
        dialog.bindings.setCurrentIndex(1)
        self.assertFalse(dialog.godot_saved.isEnabled())
        dialog.consent.setChecked(True)
        self.assertTrue(dialog.godot_saved.isEnabled())
        dialog.godot_saved.click()
        self.assertEqual(dialog.choice.operation,'godot_saved')
        self.assertEqual(dialog.choice.binding_sha256,'b'*64)
        self.assertIsNone(dialog.choice.mapping_profile)

    def test_per_source_confirmation_is_not_inherited_from_the_proof(self):
        proof = synthetic_loaded().draw_receipt
        policy = LicensePolicy('Synthetic author','Nonshipping fixture','unit:<b>literal</b>',
            reviewed=True,no_ai=True,can_use_non_unreal=True,local_preview_allowed=True)
        permission = EngineInputPermission('unit-master','a'*64,policy,False)
        reviewed = ReviewedSavedPreviewFiles(proof,proof,proof,(permission,))
        dialog = SavedPreviewPolicyDialog(reviewed)
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.consent.isChecked())
        self.assertFalse(dialog.open.isEnabled())
        self.assertIn('NoAI: True',dialog.details.toPlainText())
        self.assertIn('unit:<b>literal</b>',dialog.details.toPlainText())
        dialog.consent.setChecked(True)
        self.assertTrue(dialog.open.isEnabled())

    def window(self, loaded):
        window = QMainWindow()
        self.addCleanup(window.deleteLater)
        window.jobs = SimpleNamespace(cancel_requested=False,busy=False)
        window._work_kind = 'godot_saved_load'
        window.log = QPlainTextEdit(window)
        window.errors = []; window._error = window.errors.append
        selected = loaded.selection
        project = SimpleNamespace(project_id=selected.project_id,revision=selected.revision)
        context = SimpleNamespace(project=project,project_sha256=selected.project_sha256,database=loaded.database_path)
        review = SimpleNamespace(master_sha256=selected.master_sha256,
            source=SimpleNamespace(clip_id=selected.clip_id,source_binding_sha256=selected.source_binding_sha256,
                                   catalog_record_sha256=selected.catalog_record_sha256))
        window._godot_saved_request = (context,review,selected.binding_sha256,object())
        self.addCleanup(lambda:flow.clear_saved_godot_preview(window))
        return window

    def loaded(self, path):
        from ucc.jobs.godot_candidate_inputs import identity
        return replace(synthetic_loaded(),watch_paths=(path,path.parent),
                       watched_identities=((path,identity(path)),(path.parent,identity(path.parent))))

    def test_changed_input_clears_pixels_and_references_without_reopening_images(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)/'synthetic-bound-proof'; path.write_bytes(b'first')
            loaded = self.loaded(path); window = self.window(loaded)
            with patch.object(flow,'_current'):
                flow.finish_saved_godot_preview(window,loaded)
                self.assertFalse(window.errors)
                self.assertEqual(window._godot_saved_viewer.current_frame,1)
                path.write_bytes(b'changed')
                self.assertFalse(flow._visible_guard(window))
                self.assertIsNone(window._godot_saved_loaded)
                self.assertIsNone(window._godot_saved_viewer.current_frame)
                self.assertTrue(window._godot_saved_viewer.image_label.pixmap().isNull())

    def test_late_cancellation_never_adopts_the_returned_images(self):
        window = self.window(synthetic_loaded()); window.jobs.cancel_requested=True
        with patch.object(flow,'SavedGodotPreviewDialog') as viewer:
            flow.finish_saved_godot_preview(window,synthetic_loaded())
            viewer.assert_not_called()
        self.assertIsNone(window._godot_saved_request)

    def test_initial_watch_race_drops_deleted_widget_before_clear_and_reopen(self):
        from PySide6.QtCore import QCoreApplication, QEvent, QFileSystemWatcher
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'proof'; path.write_bytes(b'first')
            loaded=self.loaded(path); window=self.window(loaded)
            request=window._godot_saved_request
            class RacedWatcher(QFileSystemWatcher):
                def addPaths(self, paths):
                    result=super().addPaths(paths)
                    path.write_bytes(b'raced')
                    return result
            with patch.object(flow,'_current'), patch.object(flow,'QFileSystemWatcher',RacedWatcher):
                flow.finish_saved_godot_preview(window,loaded)
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.assertIsNone(window._godot_saved_viewer)
            flow.clear_saved_godot_preview(window)
            window._godot_saved_request=request
            with patch.object(flow,'_current'):
                flow.finish_saved_godot_preview(window,self.loaded(path))
            self.assertEqual(window._godot_saved_viewer.current_frame,1)

    def test_missing_watch_set_or_bad_qt_pixel_hash_cannot_log_success(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'proof';path.write_bytes(b'first')
            for loaded in (synthetic_loaded(),replace(self.loaded(path),frames=(
                    replace(synthetic_loaded().frames[0],rgba_sha256='0'*64),*synthetic_loaded().frames[1:]))):
                window=self.window(loaded)
                with patch.object(flow,'_current'):
                    flow.finish_saved_godot_preview(window,loaded)
                self.assertTrue(window.errors)
                self.assertNotIn('SAVED PRIVATE GODOT PREVIEW',window.log.toPlainText())
                self.assertIsNone(getattr(window,'_godot_saved_loaded',None))


    def test_conservative_directory_signal_rejects_equal_size_restored_mtime_tamper(self):
        from ucc.desktop.target_action_preview import _stamp
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw).resolve()/'proof';path.write_bytes(b'first')
            loaded=self.loaded(path);window=self.window(loaded)
            with patch.object(flow,'_current'):
                flow.finish_saved_godot_preview(window,loaded)
                watcher=window._godot_saved_watcher
                original=path.stat();stamp=_stamp(path)
                path.write_bytes(b'other')
                os.utime(path,ns=(original.st_atime_ns,original.st_mtime_ns))
                self.assertEqual(_stamp(path),stamp)
                self.assertNotEqual(path.read_bytes(),b'first')
                watcher.directoryChanged.emit(str(path.parent))
                self.assertIsNone(window._godot_saved_loaded)
                self.assertIsNone(window._godot_saved_viewer.current_frame)
                self.assertTrue(window._godot_saved_viewer.image_label.pixmap().isNull())


if __name__ == '__main__':
    unittest.main()
