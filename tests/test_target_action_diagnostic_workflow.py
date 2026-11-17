"""NONSHIPPING real-Qt lifecycle faults; no assets, engines or proof admission."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
from dataclasses import replace
import unittest
from unittest.mock import patch

from fixtures.target_action_diagnostic_ui_logic import synthetic_loaded, synthetic_report
from ucc.core.errors import ProjectConflict, ValidationError
try:
    from PySide6.QtCore import QCoreApplication, QEvent, QFileSystemWatcher
    from PySide6.QtWidgets import QApplication, QMainWindow, QPlainTextEdit
    from ucc.desktop import target_action_diagnostic_workflow as flow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class DiagnosticWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Diagnostic workflow tests require Qt')
        cls.app = QApplication.instance() or QApplication(['diagnostic-workflow-tests'])

    def window(self, loaded):
        window = QMainWindow()
        window.jobs = SimpleNamespace(busy=False, cancel_requested=False)
        window._work_kind = 'target_action_diagnostic'
        window._target_action_cancel = Event()
        window.log = QPlainTextEdit(window)
        window.errors = []
        window._error = window.errors.append
        selected = loaded.report.selection
        project = SimpleNamespace(project_id=selected.project_id, revision=selected.revision)
        store = object()
        context = SimpleNamespace(store=store, project=project, database=loaded.database_path,
                                  project_sha256=selected.project_sha256)
        window.controller = SimpleNamespace(has_project=True, dirty=False, store=store,
                                           require_project=lambda: project)
        token = object()
        window._target_diagnostic_request = (context, selected, token)
        self.addCleanup(window.deleteLater)
        def cleanup():
            flow.clear_target_action_diagnostic(window)
            viewer = getattr(window, '_target_diagnostic_viewer', None)
            if viewer is not None:
                viewer.close()
        self.addCleanup(cleanup)
        return window, context, token

    def input(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name).resolve()/'synthetic-catalog'
        path.write_bytes(b'first')
        return path, synthetic_loaded(path)

    def test_normal_result_displays_captured_report_without_background_guard(self):
        _, loaded = self.input()
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        self.assertEqual(window.errors, [])
        self.assertIs(window._target_diagnostic_viewer.report, loaded.report)
        self.assertIn('PRIVATE REGISTERED CLIP DIAGNOSTICS', window.log.toPlainText())
        self.assertTrue(flow._visible_guard(window))

    def test_untyped_result_and_wrong_selection_never_log_success(self):
        _, loaded = self.input()
        for bad in (None, {}, replace(loaded, report=replace(loaded.report,
                selection=replace(loaded.report.selection, revision=2)))):
            window, _, token = self.window(loaded)
            flow.finish_target_action_diagnostic(window, (token, bad))
            self.assertTrue(window.errors)
            self.assertIsNone(getattr(window, '_target_diagnostic_loaded', None))
            self.assertEqual(window.log.toPlainText(), '')

    def test_cancel_or_superseded_token_never_adopts_report(self):
        _, loaded = self.input()
        for cancelled in (True, False):
            window, _, token = self.window(loaded)
            window.jobs.cancel_requested = cancelled
            flow.finish_target_action_diagnostic(window, (token if cancelled else object(), loaded))
            self.assertIsNone(getattr(window, '_target_diagnostic_loaded', None))
            self.assertEqual(window.log.toPlainText(), '')

    def test_project_changes_reject_late_result_and_cancel_pending_operation(self):
        _, loaded = self.input()
        window, _, token = self.window(loaded)
        window.controller.dirty = True
        flow.finish_target_action_diagnostic(window, (token, loaded))
        self.assertTrue(window.errors)
        self.assertIsNone(window._target_diagnostic_loaded)
        window, _, _ = self.window(loaded)
        window.jobs.busy = True
        window.controller.dirty = True
        flow.refresh_target_action_diagnostic(window)
        self.assertTrue(window._target_action_cancel.is_set())
        self.assertIsNone(window._target_diagnostic_request)

    def test_changed_input_clears_measurements_and_all_authority_references(self):
        path, loaded = self.input()
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        path.write_bytes(b'changed')
        self.assertFalse(flow._visible_guard(window))
        self.assertIsNone(window._target_diagnostic_loaded)
        self.assertIsNone(window._target_diagnostic_viewer.report)
        self.assertEqual(window._target_diagnostic_viewer.details.toPlainText(), '')
        self.assertIsNone(window._target_diagnostic_context)
        self.assertIsNone(window._target_diagnostic_timer)
        self.assertIsNone(window._target_diagnostic_watcher)

    def test_directory_signal_clears_same_size_restored_mtime_mutation(self):
        path, loaded = self.input()
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        old = path.stat()
        path.write_bytes(b'other')
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        window._target_diagnostic_watcher.directoryChanged.emit(str(path.parent))
        self.assertIsNone(window._target_diagnostic_loaded)
        self.assertEqual(window._target_diagnostic_viewer.details.toPlainText(), '')

    def test_new_catalog_wal_directory_notification_clears_report(self):
        path, loaded = self.input()
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        Path(str(path)+'-wal').write_bytes(b'nonshipping synthetic WAL namespace')
        window._target_diagnostic_watcher.directoryChanged.emit(str(path.parent))
        self.assertIsNone(window._target_diagnostic_loaded)

    def test_absent_catalog_wal_sentinel_is_retained_and_creation_clears_report(self):
        path, loaded = self.input()
        wal = Path(str(path)+'-wal')
        loaded = replace(loaded, watched_identities=(*loaded.watched_identities, (wal, (0, 0, 0, 0))))
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        self.assertEqual(window.errors, [])
        self.assertEqual(window._target_diagnostic_identities[wal], (0, 0, 0, 0))
        self.assertNotIn(str(wal), window._target_diagnostic_watcher.files())
        wal.write_bytes(b'NONSHIPPING synthetic coordination namespace')
        self.assertFalse(flow._visible_guard(window))
        self.assertIsNone(window._target_diagnostic_viewer.report)

    def test_absent_noncoordination_input_or_unwatched_parent_rejected(self):
        path, loaded = self.input()
        for identities, paths in (
            ((*loaded.watched_identities, (path.parent/'unknown-proof', (0, 0, 0, 0))), loaded.watch_paths),
            (((path, flow._stamp(path)), (Path(str(path)+'-wal'), (0, 0, 0, 0))), (path,)),
        ):
            window, _, token = self.window(loaded)
            bad = replace(loaded, watched_identities=identities, watch_paths=paths)
            flow.finish_target_action_diagnostic(window, (token, bad))
            self.assertTrue(window.errors)
            self.assertIsNone(getattr(window, '_target_diagnostic_loaded', None))

    def test_report_is_parent_owned_and_parent_cleanup_hides_child_and_drops_references(self):
        _, loaded = self.input()
        window, _, token = self.window(loaded)
        window.show()
        flow.finish_target_action_diagnostic(window, (token, loaded))
        viewer = window._target_diagnostic_viewer
        self.assertIs(viewer.parent(), window)
        self.assertTrue(viewer.isVisible())
        window.close()
        self.assertFalse(viewer.isVisible())
        self.assertIsNone(viewer.report)
        self.assertIsNone(window._target_diagnostic_loaded)

    def test_failed_watch_install_or_missing_watch_set_never_adopts(self):
        _, loaded = self.input()
        class FailedWatcher(QFileSystemWatcher):
            def addPaths(self, paths):
                return paths
        for value in (loaded, replace(loaded, watch_paths=(), watched_identities=())):
            window, _, token = self.window(loaded)
            with patch.object(flow, 'QFileSystemWatcher', FailedWatcher):
                flow.finish_target_action_diagnostic(window, (token, value))
            self.assertTrue(window.errors)
            self.assertIsNone(getattr(window, '_target_diagnostic_loaded', None))
            self.assertEqual(window.log.toPlainText(), '')

    def test_watch_install_race_cleans_deleted_dialog_then_allows_explicit_reopen(self):
        path, loaded = self.input()
        window, context, token = self.window(loaded)
        class RacedWatcher(QFileSystemWatcher):
            def addPaths(self, paths):
                result = super().addPaths(paths)
                path.write_bytes(b'raced with another size')
                return result
        with patch.object(flow, 'QFileSystemWatcher', RacedWatcher):
            flow.finish_target_action_diagnostic(window, (token, loaded))
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertIsNone(window._target_diagnostic_viewer)
        flow.clear_target_action_diagnostic(window)
        loaded = synthetic_loaded(path)
        window._target_diagnostic_request = (context, loaded.report.selection, token)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        self.assertIs(window._target_diagnostic_viewer.report, loaded.report)

    def test_close_removes_live_references_and_disposes_watch_and_timer(self):
        _, loaded = self.input()
        window, _, token = self.window(loaded)
        flow.finish_target_action_diagnostic(window, (token, loaded))
        window._target_diagnostic_viewer.close()
        self.assertIsNone(window._target_diagnostic_viewer)
        self.assertIsNone(window._target_diagnostic_loaded)
        self.assertIsNone(window._target_diagnostic_watcher)
        self.assertIsNone(window._target_diagnostic_timer)

    def test_start_requires_consent_and_uses_existing_submit_event_progress(self):
        _, loaded = self.input()
        window, context, _ = self.window(loaded)
        selected = loaded.report.selection
        review = SimpleNamespace(master_sha256=selected.master_sha256, source=SimpleNamespace(
            clip_id=selected.clip_id, source_binding_sha256=selected.source_binding_sha256,
            catalog_record_sha256=selected.catalog_record_sha256))
        with patch('ucc.desktop.target_action_workflow._submit') as submit:
            for binding, consent in ((selected.binding_sha256, False), (None, True)):
                with self.assertRaises(ValidationError):
                    flow.start_target_action_diagnostic(window, context, review, binding,
                                                        local_preview_confirmed=consent)
            submit.assert_not_called()
            flow.start_target_action_diagnostic(window, context, review, selected.binding_sha256,
                                                local_preview_confirmed=True)
            args, kwargs = submit.call_args
            self.assertEqual(args[1], 'target_action_diagnostic')
            self.assertTrue(kwargs['progress'])
            cancel = Event(); progress = lambda _phase: None
            with patch('ucc.jobs.target_action_diagnostic.inspect_saved_target_action', return_value=loaded) as inspect:
                token, returned = args[2](cancel, progress)
            self.assertIs(returned, loaded)
            self.assertIs(token, window._target_diagnostic_request[2])
            self.assertIs(inspect.call_args.kwargs['cancel'], cancel)
            self.assertIs(inspect.call_args.kwargs['progress'], progress)
            self.assertIs(inspect.call_args.kwargs['local_preview_confirmed'], True)


if __name__ == '__main__':
    unittest.main()
