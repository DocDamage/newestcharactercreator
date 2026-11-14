"""Actual Qt reference controls with synthetic worker boundary fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication = None
    QT_IMPORT_ERROR = str(error)

from fixtures.project_reference_contract import ReferenceFixture
from ucc.animations.catalog import AnimationCatalog
from ucc.jobs.project_animation_references import attach_catalog_reference


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 absent')
class AnimationReferenceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None: raise RuntimeError(QT_IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['reference-boundaries'])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = ReferenceFixture(Path(temporary.name)); self.controller = DesktopController(); self.controller.open(self.f.store.root)
        self.window = MainWindow(self.controller); self.addCleanup(self.window.deleteLater)
        self.window._blender_executable = self.f.executable
        self.addCleanup(patch.stopall)
        patch.object(self.window, '_catalog_path', return_value=self.f.database).start()
        self.errors = patch.object(self.window, '_error').start()
        self.queue = []
        patch.object(self.window, '_submit', side_effect=lambda kind, op, **kw: self.queue.append((kind, op, kw))).start()
        patch('ucc.jobs.project_animation_references.inspect_saved_neutral_master', side_effect=self.f.neutral).start()
        patch('ucc.jobs.project_animation_references.verify_catalog_fbx_clip', return_value=self.f.reference).start()
        with AnimationCatalog(self.f.database) as c: rows = [x.to_dict() for x in c.list_sources()]
        self.window.animations.display_catalog(rows); self.window.animations.catalog.selectRow(0)

    def complete(self):
        kind, operation, kwargs = self.queue.pop(); self.window._work_kind = kind
        result = operation(); self.window._job_success(result)
        return result, kwargs

    def test_real_attach_button_saves_and_updates_reference_list_without_master_change(self):
        pane = self.window.animations; self.assertTrue(pane.attach_reference.isEnabled())
        pane.attach_reference.click(); result, kwargs = self.complete()
        self.assertTrue(result.changed); self.assertIn('cancel', kwargs)
        self.assertEqual(pane.references.count(), 1); self.assertEqual(pane.references.item(0).text(), self.f.clip_id)
        self.assertEqual(self.controller.require_project(), self.f.store.load())
        self.assertFalse(self.controller.dirty); self.assertTrue(self.controller.view().can_undo)
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)
        self.assertIn('editing with references', self.window.log.toPlainText())

    def test_attach_history_undo_redo_save_and_reopen_preserve_references(self):
        self.window.animations.attach_reference.click(); self.complete()
        self.window.undo(); self.assertEqual(self.controller.require_project().animations, ())
        self.assertTrue(self.controller.dirty); self.assertFalse(self.window.animations.attach_reference.isEnabled())
        self.window.save_project(); self.window.redo(); self.window.save_project()
        self.assertEqual(self.controller.require_project().animations, (self.f.clip_id,))
        reopened = DesktopController(); reopened.open(self.f.store.root)
        self.assertEqual(reopened.require_project().animations, (self.f.clip_id,))
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)

    def test_detach_button_uses_no_catalog_and_retains_binding(self):
        self.window.animations.attach_reference.click(); self.complete()
        self.window._catalog_path.side_effect = AssertionError('Detach must not require source catalog')
        self.window.animations.detach_reference.click(); removed, _ = self.complete()
        self.assertTrue(removed.changed); self.assertEqual(self.window.animations.references.count(), 0)
        self.assertEqual(len(list((self.f.store.root/'animations/references').glob('*.json'))), 1)

    def test_unsaved_intent_blocks_reference_transaction(self):
        self.window.rename('Unsaved reference target')
        self.window.attach_animation_reference()
        self.assertFalse(self.queue); self.assertIn('Save the character', self.errors.call_args.args[0])

    def test_unmeasured_or_non_fbx_catalog_rows_do_not_enable_attach(self):
        row = {'asset_id': 'raw', 'format': 'fbx', 'clips': [], 'status': 'REQUIRES_CONVERSION'}
        self.window.animations.display_catalog([row]); self.window.animations.catalog.selectRow(0)
        self.assertFalse(self.window.animations.attach_reference.isEnabled())
        self.window.attach_animation_reference(); self.assertFalse(self.queue)

    def test_busy_reference_job_enables_existing_cancel_and_freezes_source_and_project_controls(self):
        self.window._work_kind = 'animation_reference_attach'; self.window._busy_changed(True)
        self.assertTrue(self.window.cancel_generation_action.isEnabled()); self.assertFalse(self.window.animations.isEnabled())
        self.assertFalse(self.window.character.isEnabled())
        self.window._busy_changed(False); self.assertTrue(self.window.animations.attach_reference.isEnabled())

    def test_failed_reference_transaction_clears_old_target_previews_without_discarding_intent(self):
        project = self.controller.require_project(); self.window._work_kind = 'animation_reference_attach'
        with patch.object(self.window, '_clear_preview') as clear:
            self.window._job_error('Synthetic reference failure')
            clear.assert_called_once()
        self.assertEqual(self.controller.require_project(), project)


if __name__ == '__main__': unittest.main()
