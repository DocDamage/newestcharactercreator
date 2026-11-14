"""Real Qt catalog controls; worker outputs below are isolated boundary fixtures."""
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

from ucc.animations.catalog import AnimationCatalog
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError, LicensePolicy


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 absent')
class FbxCatalogQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None: raise RuntimeError(QT_IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['catalog-boundary'])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.database = self.root/'catalog.db'
        self.controller = DesktopController(); self.controller.create(self.root/'character', 'Catalog test')
        self.window = MainWindow(self.controller); self.addCleanup(self.window.deleteLater)
        self.source = self.root/'source.fbx'; self.source.write_bytes(b'SYNTHETIC_QT_NOT_FBX')
        self.executable = self.root/'not-actual-blender.exe'; self.executable.write_bytes(b'UNIT_ONLY')
        self.window._blender_executable = self.executable
        self.pane = self.window.animations
        for field, value in ((self.pane.selected, str(self.source)), (self.pane.asset_id, 'unit-source'),
                (self.pane.provider, 'Original'), (self.pane.license, 'CC0'), (self.pane.uri, 'local-original://fixture')):
            field.setText(value)
        self.pane.local_preview_review.setChecked(True)
        self.queued = []
        self.addCleanup(patch.stopall)
        patch.object(self.window, '_catalog_path', return_value=self.database).start()
        patch.object(self.window, '_submit', side_effect=lambda kind, op, **kw: self.queued.append((kind, op, kw))).start()
        self.errors = patch.object(self.window, '_error').start()
        patch('ucc.desktop.animation_catalog.bundled_worker_path', return_value=Path('unit-worker')).start()

    def test_unchecked_fbx_keeps_unreviewed_metadata_path_without_blender(self):
        self.assertEqual(self.pane.index.text(), 'Index selected source')
        self.assertIn('Without local review', self.pane.index.toolTip())
        self.pane.local_preview_review.setChecked(False)
        with patch('ucc.desktop.animation_catalog.measure_catalog_fbx') as measure:
            self.pane.index.click()
            kind, operation, kwargs = self.queued.pop()
            self.assertEqual(kind, 'index'); self.assertEqual(kwargs, {})
            result = operation(); measure.assert_not_called()
        self.assertEqual(result['status'], 'REQUIRES_CONVERSION'); self.assertEqual(result['clips'], [])
        with AnimationCatalog(self.database) as catalog: self.assertFalse(catalog.library.get('unit-source').policy.reviewed)

    def test_reviewed_fbx_uses_captured_policy_source_jobs_and_cancellation(self):
        with patch('ucc.desktop.animation_catalog.measure_catalog_fbx', return_value={'unit-result': True}) as measure:
            self.pane.index.click(); kind, operation, kwargs = self.queued.pop()
            self.assertEqual(kind, 'fbx_catalog'); self.assertIn('cancel', kwargs)
            result = operation()
            self.assertEqual(result['source'], {'unit-result': True})
            self.assertEqual(len(result['catalog']), 1)
            self.assertEqual(measure.call_args.args, (self.database, 'unit-source'))
            self.assertIs(measure.call_args.kwargs['cancel'], kwargs['cancel'])
            self.assertEqual(measure.call_args.kwargs['jobs_root'], self.controller.store.root/'.ucc-jobs')
        with AnimationCatalog(self.database) as catalog:
            policy = catalog.library.get('unit-source').policy
            self.assertTrue(policy.reviewed); self.assertTrue(policy.local_preview_allowed); self.assertTrue(policy.no_ai)
            self.assertFalse(policy.can_use_non_unreal); self.assertFalse(policy.ai_input_allowed)

    def test_prior_unreviewed_policy_is_immutable_and_error_is_actionable(self):
        with AnimationCatalog(self.database) as catalog:
            catalog.index_file('unit-source', self.source, LicensePolicy('Original', 'CC0', 'local-original://fixture'))
        with patch('ucc.desktop.animation_catalog.measure_catalog_fbx') as measure:
            self.pane.index.click()
            with self.assertRaisesRegex(AssetPolicyError, 'new asset ID'): self.queued.pop()[1]()
            measure.assert_not_called()
        with AnimationCatalog(self.database) as catalog:
            self.assertFalse(catalog.library.get('unit-source').policy.reviewed)
            self.assertEqual(catalog.get('unit-source').clips, ())

    def test_missing_project_does_not_launch_or_create_database(self):
        self.controller.store = None
        self.pane.index.click()
        self.assertFalse(self.queued); self.assertFalse(self.database.exists())
        self.assertIn('Open a project', self.errors.call_args.args[0])

    def test_unknown_license_cannot_be_promoted_by_review_checkbox(self):
        self.pane.license.setText('unknown'); self.pane.local_preview_review.setChecked(True)
        self.pane.index.click()
        self.assertFalse(self.queued); self.assertIn('actual FBX license', self.errors.call_args.args[0])

    def test_cancellation_before_queued_work_keeps_catalog_untouched(self):
        self.pane.index.click(); _, operation, kwargs = self.queued.pop(); kwargs['cancel'].set()
        with self.assertRaises(WorkerFailure): operation()
        self.assertFalse(self.database.exists())

    def test_measured_index_freezes_controls_and_enables_existing_cancel_action(self):
        self.window._work_kind = 'fbx_catalog'; self.window._busy_changed(True)
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertFalse(self.pane.isEnabled())
        self.window._busy_changed(False)
        self.assertFalse(self.window.cancel_generation_action.isEnabled()); self.assertTrue(self.pane.isEnabled())

    def test_completion_refreshes_whole_catalog_and_preserves_project(self):
        project = self.controller.require_project()
        source = {'asset_id': 'first', 'format': 'fbx', 'status': 'METADATA_EXTRACTED',
                  'clips': [{'name': 'Source Action', 'frame_count': 300, 'fps': 30.}]}
        second = {**source, 'asset_id': 'second'}
        self.window._work_kind = 'fbx_catalog'
        self.window._job_success({'source': source, 'catalog': [source, second]})
        self.assertEqual(self.pane.catalog.rowCount(), 2)
        self.assertEqual(self.controller.require_project(), project)
        self.assertIn('No animation was applied', self.window.log.toPlainText())
        self.assertIn('unverified', self.window.log.toPlainText())


if __name__ == '__main__': unittest.main()
