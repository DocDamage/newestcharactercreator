"""Qt dispatch/progress/failure checks only; actual Blender/Unity acceptance is separate."""
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch
import os
import tempfile
import unittest

from fixtures.godot_export_logic import review

try:
    from PySide6.QtWidgets import QApplication, QDialog
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 unavailable')
class UnityExportDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop.controller import DesktopController
        from ucc.desktop.window import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.controller = DesktopController()
        self.controller.create(self.root/'project', 'UNIT_UI_ONLY')
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.deleteLater)
        self.window._error = Mock()

    def test_menu_defaults_dirty_and_busy_gate(self):
        from ucc.desktop.unity_export_workflow import refresh_unity_export
        self.assertFalse(self.window.unity_export_action.isEnabled())
        with patch('ucc.desktop.unity_export_workflow.supports_material_master_intent', return_value=True):
            refresh_unity_export(self.window)
            self.assertTrue(self.window.unity_export_action.isEnabled())
            self.window.rename('UNIT_UNSAVED')
            refresh_unity_export(self.window)
            self.assertFalse(self.window.unity_export_action.isEnabled())

    def test_unsaved_and_busy_reject_without_source_review(self):
        from ucc.desktop.unity_export_workflow import start_unity_export
        self.window.rename('UNIT_UNSAVED')
        with patch('ucc.desktop.unity_export_workflow.static_export_sources') as sources:
            start_unity_export(self.window)
            sources.assert_not_called()
        self.assertIn('Save character', self.window._error.call_args.args[0])
        self.window.jobs._thread = object()
        try:
            with patch('ucc.desktop.unity_export_workflow.static_export_sources') as sources:
                start_unity_export(self.window)
                sources.assert_not_called()
        finally:
            self.window.jobs._thread = None
        self.assertIn('Another local task', self.window._error.call_args.args[0])

    def dialog(self, accepted=True):
        d = Mock()
        d.exec.return_value = QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
        d.destination.text.return_value = str(self.root/'new-export')
        editor = self.root/'UNIT_EDITOR_NOT_ENGINE.exe'
        editor.write_bytes(b'UNIT_NOT_REAL_ENGINE')
        d.editor.text.return_value = str(editor)
        d.permissions.return_value = ()
        return d

    def resume(self):
        from ucc.desktop.unity_export_workflow import UnityDesktopReview, resume_unity_source_review
        self.window._unity_pending_review = UnityDesktopReview(
            self.controller.store, self.controller.require_project(), review())
        resume_unity_source_review(self.window)

    def test_cancelled_review_does_not_start_or_choose_blender(self):
        from ucc.desktop.unity_export_workflow import start_unity_export
        with patch('ucc.desktop.unity_export_workflow.static_export_sources', return_value=(review(), {}, {})), \
             patch('ucc.desktop.unity_export_workflow.UnityExportDialog', return_value=self.dialog(False)), \
             patch('ucc.desktop.hand_workflow._executable') as blender, \
             patch.object(self.window, '_submit') as submit:
            self.resume()
            blender.assert_not_called()
            submit.assert_not_called()

    def test_existing_destination_rejects_before_workers(self):
        from ucc.desktop.unity_export_workflow import start_unity_export
        d = self.dialog()
        (self.root/'new-export').mkdir()
        with patch('ucc.desktop.unity_export_workflow.static_export_sources', return_value=(review(), {}, {})), \
             patch('ucc.desktop.unity_export_workflow.UnityExportDialog', return_value=d), \
             patch.object(self.window, '_submit') as submit:
            self.resume()
            submit.assert_not_called()
        self.window._error.assert_called_once()

    def test_reviewed_editor_identity_permissions_cancel_and_progress_are_forwarded(self):
        from ucc.jobs.godot_candidate_inputs import identity
        from ucc.desktop.unity_export_workflow import start_unity_export, close_unity_progress
        d = self.dialog()
        with patch('ucc.desktop.unity_export_workflow.static_export_sources', return_value=(review(), {}, {})), \
             patch('ucc.desktop.unity_export_workflow.UnityExportDialog', return_value=d), \
             patch('ucc.desktop.hand_workflow._executable', return_value=self.root/'UNIT_BLENDER'), \
             patch.object(self.window, '_clear_preview'), \
             patch.object(self.window, '_submit') as submit, \
             patch('ucc.desktop.unity_export_workflow.run_desktop_unity_export', return_value='UNIT_BOUNDARY') as run:
            self.resume()
            d.permissions.assert_called_once_with()
            self.assertEqual(submit.call_args.args[0], 'unity_export')
            cancel = submit.call_args.kwargs['cancel']
            self.assertFalse(cancel.is_set())
            self.assertEqual(submit.call_args.args[1](), 'UNIT_BOUNDARY')
            self.assertEqual(run.call_args.kwargs['editor_identity'], identity(Path(d.editor.text())))
            self.assertIs(run.call_args.kwargs['permissions'], d.permissions.return_value)
            self.assertIs(run.call_args.kwargs['cancel'], cancel)
            self.window._unity_export_progress.request_cancel()
            self.assertTrue(cancel.is_set())
            close_unity_progress(self.window)

    def test_stale_project_during_review_rejects(self):
        from ucc.desktop.unity_export_workflow import start_unity_export
        d = self.dialog()
        def change_project():
            self.window.rename('UNIT_CHANGED_DURING_REVIEW')
            return QDialog.DialogCode.Accepted
        d.exec.side_effect = change_project
        with patch('ucc.desktop.unity_export_workflow.static_export_sources', return_value=(review(), {}, {})), \
             patch('ucc.desktop.unity_export_workflow.UnityExportDialog', return_value=d), \
             patch('ucc.desktop.hand_workflow._executable', return_value=self.root/'UNIT_BLENDER'), \
             patch.object(self.window, '_submit') as submit:
            self.resume()
            submit.assert_not_called()
        self.assertIn('changed during', self.window._error.call_args.args[0])

    def test_worker_progress_is_queued_to_qt_and_cancellation_waits(self):
        from ucc.desktop.unity_export_workflow import UnityExportProgress
        cancel = Event()
        progress = UnityExportProgress(self.window, cancel)
        self.addCleanup(progress.close)
        thread = Thread(target=lambda: progress.changed.emit('PUBLISHED_RUNTIME_VERIFICATION'))
        thread.start()
        thread.join()
        self.app.processEvents()
        self.assertIn('published Unity project', self.window.statusBar().currentMessage())
        progress.request_cancel()
        self.assertTrue(cancel.is_set())
        self.assertIn('waiting', self.window.statusBar().currentMessage())

    def test_error_preserves_cancellation_rollback_diagnostics(self):
        from ucc.desktop.unity_export_workflow import unity_export_error
        unity_export_error(self.window, 'UNIT rollback failed; retained output D:/unit-retained')
        message = self.window._error.call_args.args[0]
        self.assertIn('rollback failed', message)
        self.assertIn('D:/unit-retained', message)
        self.assertNotIn('cancelled. No', message)

    def test_background_boundary_preserves_exception_rollback_notes(self):
        from ucc.core.errors import ProjectStorageError
        from ucc.desktop.unity_export_workflow import run_desktop_unity_export
        failure = ProjectStorageError('UNIT final check failed')
        failure.add_note('UNIT rollback failed; retained destination D:/unit-owned-output')
        with patch('ucc.desktop.unity_export_workflow._run_desktop_unity_export', side_effect=failure), \
             self.assertRaises(ProjectStorageError) as caught:
            run_desktop_unity_export(None, review=None, permissions=(), editor_identity=None,
                                     destination=None, blender_exe=None, unity_exe=None, cancel=Event())
        self.assertIn('retained destination D:/unit-owned-output', str(caught.exception))

    def test_window_routes_unity_results_and_errors(self):
        self.window._work_kind = 'unity_export'
        result = object()
        with patch('ucc.desktop.unity_export_workflow.finish_unity_export') as finish:
            self.window._job_success(result)
            finish.assert_called_once_with(self.window, result)
        with patch('ucc.desktop.unity_export_workflow.unity_export_error') as fail:
            self.window._job_error('UNIT_FAILURE')
            fail.assert_called_once_with(self.window, 'UNIT_FAILURE')

    def test_background_source_review_keeps_qt_responsive_and_waits_for_cleanup(self):
        from PySide6.QtCore import QEventLoop, QTimer
        from ucc.desktop.unity_export_workflow import UnityDesktopReview, start_unity_export
        released = Event()
        called = []
        def background_review(store, project, cancel):
            called.append(cancel)
            if not released.wait(2):
                raise RuntimeError('Qt did not service its timer while source review ran')
            return UnityDesktopReview(store, project, review())
        loop = QEventLoop()
        watch = QTimer()
        watch.setInterval(10)
        watch.timeout.connect(lambda: loop.quit() if not self.window.jobs.busy else None)
        with patch('ucc.desktop.unity_export_workflow.review_unity_sources', side_effect=background_review), \
             patch('ucc.desktop.unity_export_workflow.UnityExportDialog', return_value=self.dialog(False)) as dialog:
            start_unity_export(self.window)
            self.assertTrue(self.window.jobs.busy)
            self.assertTrue(self.window.cancel_generation_action.isEnabled())
            dialog.assert_not_called()
            QTimer.singleShot(10, released.set)
            QTimer.singleShot(3000, loop.quit)
            watch.start()
            loop.exec()
            watch.stop()
            self.assertFalse(self.window.jobs.busy)
            dialog.assert_called_once()
        self.assertTrue(released.is_set())
        self.window._error.assert_not_called()

    def completion(self):
        from fixtures.unity_desktop_logic import receipt_result
        source_review = review()
        self.window._unity_export_context = (
            self.controller.store, self.controller.require_project(), source_review)
        return receipt_result(self.root/'UNIT_NOT_REAL_EXPORT', source_review)

    def test_completion_receipt_check_reports_narrow_scope(self):
        from ucc.desktop.unity_export_workflow import finish_unity_export
        result = self.completion()
        finish_unity_export(self.window, result)
        self.window._error.assert_not_called()
        text = self.window.log.toPlainText()
        self.assertIn('No animation clips', text)
        self.assertIn('remain unapproved', text)
        self.assertIn(str(result.destination), text)

    def test_changed_receipt_cannot_show_completion(self):
        from ucc.desktop.unity_export_workflow import finish_unity_export
        result = self.completion()
        (result.destination/'export_receipt.json').write_bytes(b'UNIT_ALTERED_RECEIPT')
        finish_unity_export(self.window, result)
        self.assertIn('receipt changed', self.window._error.call_args.args[0])
        self.assertNotIn('project created', self.window.log.toPlainText())

    def test_changed_desktop_project_cannot_show_completion(self):
        from ucc.desktop.unity_export_workflow import finish_unity_export
        result = self.completion()
        self.window.rename('UNIT_CHANGED_WHILE_EXPORTING')
        finish_unity_export(self.window, result)
        self.assertIn('context changed', self.window._error.call_args.args[0])
        self.assertNotIn('project created', self.window.log.toPlainText())
