"""Normal MainWindow boundaries with NONSHIPPING skeleton/catalog fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.source_skeleton import build_source_skeleton_cache
from ucc.jobs.source_skeleton_preview import LoadedSourceSkeletonPreview
from ucc.jobs.source_skeleton_files import watch_identity
from ucc.library.provenance import LicensePolicy
try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
    from ucc.desktop import source_skeleton_workflow as flow
except ImportError as error:
    QApplication = None
    QT_IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class SourceSkeletonWorkflowQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None: raise RuntimeError(QT_IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['source-skeleton-boundaries'])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.database = self.root/'owned.sqlite3'
        self.controller = DesktopController(); self.controller.create(self.root/'p', 'Synthetic source preview')
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.deleteLater); self.addCleanup(self.window._clear_preview)
        self.source = self.root/'synthetic.fbx'; self.source.write_bytes(b'NONSHIPPING_NOT_FBX')
        self.policy = LicensePolicy('Original test', 'Synthetic', 'test://qt', reviewed=True,
                                    no_ai=True, local_preview_allowed=True)
        with AnimationCatalog(self.database) as c: c.index_file('source', self.source, self.policy)
        table = self.window.animations.catalog; table.setRowCount(1)
        table.setItem(0, 0, QTableWidgetItem('source')); table.setCurrentCell(0, 0)
        self.executable = self.root/'synthetic-not-blender.exe'; self.executable.write_bytes(b'NOT_EXECUTABLE')
        self.window._blender_executable = self.executable
        self.queued = []; self.errors = []
        self.addCleanup(patch.stopall)
        patch.object(self.window, '_catalog_path', return_value=self.database).start()
        patch.object(self.window, '_submit', side_effect=self.submit).start()
        patch.object(self.window, '_error', side_effect=self.errors.append).start()
        patch.object(flow, 'bundled_worker_path', return_value=self.root/'unused-worker.py').start()
        self.prep = patch.object(flow, 'prepare_source_skeleton_preview', side_effect=lambda *a,**kw:self.loaded()).start()

    def submit(self, kind, operation, **kwargs):
        self.window._work_kind = kind
        self.queued.append((operation, kwargs))

    def loaded(self):
        payload = json.dumps(snapshot()).encode()
        cache = build_source_skeleton_cache(payload, source_sha256='a'*64,
            snapshot_sha256=sha256(payload).hexdigest())
        paths = [self.source, self.database, self.root]
        identities = {p:watch_identity(p) for p in paths}
        for suffix in ('-wal','-shm','-journal'):
            p = Path(str(self.database)+suffix); identities[p] = watch_identity(p)
        return LoadedSourceSkeletonPreview(cache, 'source#clip-0000','a'*64,sha256(payload).hexdigest(),
            'b'*64,self.database,tuple(p for p,v in identities.items() if v!=(0,0,0,0)),
            MappingProxyType(identities),lambda **kw: (_ for _ in ()).throw(AssertionError('No GUI heavy guard')))

    def start(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.source_skeleton_action.trigger()

    def finish(self):
        operation, options = self.queued[-1]; result = operation()
        self.window._job_success(result)
        return result, options

    def test_normal_action_default_no_and_no_gui_catalog_reads(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as consent, \
                patch.object(flow, 'AnimationCatalog', side_effect=AssertionError('GUI SQL forbidden')):
            self.window.source_skeleton_action.trigger()
        self.assertEqual(consent.call_args.args[-1], QMessageBox.StandardButton.No)
        self.assertFalse(self.queued); self.prep.assert_not_called()
        with patch.object(flow, 'AnimationCatalog', side_effect=AssertionError('GUI SQL forbidden')):
            self.start()
        self.assertEqual(len(self.queued), 1); self.prep.assert_not_called()

    def test_normal_job_adoption_uses_cheap_guard_and_close_clears_every_reference(self):
        self.start(); self.finish()
        viewer = self.window._source_skeleton_viewer
        self.assertIsNotNone(viewer.cache); self.assertIn('Source frame 1', viewer.status.text())
        viewer.toggle_play(); self.assertTrue(viewer.timer.isActive())
        self.window._source_skeleton_dock.close()
        self.assertIsNone(viewer.cache); self.assertIsNone(viewer.clock)
        self.assertEqual(viewer.canvas.segments,b''); self.assertFalse(viewer.timer.isActive())
        self.assertIsNone(self.window._source_skeleton_result)
        self.assertFalse(self.window._source_skeleton_watcher.files())
        viewer.tick(); self.assertIsNone(viewer.cache)

    def test_selected_source_change_or_empty_selection_rejects_adoption(self):
        for selection in ('other', None):
            self.start(); operation, _ = self.queued[-1]; result = operation()
            table = self.window.animations.catalog
            if selection is None: table.clearContents()
            else: table.item(0,0).setText(selection)
            self.window._job_success(result)
            self.assertIsNone(getattr(self.window,'_source_skeleton_result',None))
            table.setItem(0,0,QTableWidgetItem('source'))

    def test_project_owner_change_rejects_pending_result(self):
        self.start(); operation, _ = self.queued[-1]; result = operation()
        self.controller.create(self.root/'different-project','Other')
        self.window._job_success(result)
        self.assertIsNone(getattr(self.window,'_source_skeleton_result',None))

    def test_late_cancel_after_worker_return_cannot_adopt(self):
        self.start(); operation, options = self.queued[-1]; result = operation()
        options['cancel'].set(); self.window._job_success(result)
        self.assertIsNone(getattr(self.window,'_source_skeleton_result',None))

    def test_superseded_completion_does_not_discard_new_request(self):
        self.start(); old_operation, old_options = self.queued[-1]; old_result = old_operation()
        self.start(); pending = self.window._source_skeleton_pending
        self.assertTrue(old_options['cancel'].is_set())
        self.window._job_success(old_result)
        self.assertIs(self.window._source_skeleton_pending, pending)
        self.assertIsNone(getattr(self.window,'_source_skeleton_result',None))
        self.finish(); self.assertIsNotNone(self.window._source_skeleton_viewer.cache)

    def test_main_window_close_cancels_pending_and_late_result_stays_hidden(self):
        self.start(); operation, options = self.queued[-1]; result = operation()
        self.window.close()
        self.assertTrue(options['cancel'].is_set())
        self.window._job_success(result)
        self.assertIsNone(getattr(self.window,'_source_skeleton_result',None))

    def test_busy_clears_loaded_but_keeps_own_pending_cancel_control(self):
        self.start(); pending = self.window._source_skeleton_pending
        self.window._busy_changed(True)
        self.assertIs(self.window._source_skeleton_pending,pending)
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertFalse(self.window.source_skeleton_action.isEnabled())
        self.window._busy_changed(False)
        self.finish(); self.assertIsNotNone(self.window._source_skeleton_viewer.cache)

    def test_missing_sidecar_poll_failure_clears_without_signal_or_heavy_guard(self):
        self.start(); self.finish(); viewer = self.window._source_skeleton_viewer
        Path(str(self.database)+'-journal').write_bytes(b'owned new namespace')
        viewer.guard_timer.timeout.emit()
        self.assertIsNone(viewer.cache); self.assertIsNone(self.window._source_skeleton_result)
        self.assertEqual(viewer.canvas.segments,b'')

    def test_committed_owned_wal_notification_clears_playback_authority(self):
        self.start(); self.finish(); viewer = self.window._source_skeleton_viewer
        viewer.toggle_play()
        with AnimationCatalog(self.database) as c:
            c.db.execute('PRAGMA journal_mode=WAL'); c.db.execute('PRAGMA wal_autocheckpoint=0')
            p = self.policy.to_dict(); p['local_preview_allowed']=False
            c.db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(p),)); c.db.commit()
            self.window._source_skeleton_watcher.directoryChanged.emit(str(self.root))
            self.assertIsNone(self.window._source_skeleton_result)
            self.assertIsNone(viewer.cache); self.assertFalse(viewer.timer.isActive())

    def test_error_route_clears_existing_view_and_never_logs_success(self):
        self.start(); self.finish(); viewer = self.window._source_skeleton_viewer
        self.window._job_error('Synthetic source guard rejection')
        self.assertIsNone(viewer.cache); self.assertIsNone(self.window._source_skeleton_result)
        self.assertIn('Synthetic source guard rejection', self.errors)


if __name__ == '__main__': unittest.main()
