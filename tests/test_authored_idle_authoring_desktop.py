"""NONSHIPPING Qt workflow fixtures; no Blender, assets, or runtime rights proof."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from fixtures.authored_idle_host import HostFixture
from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import ProjectStorageError

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class AuthoredIdleDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Original idle desktop tests require Qt')
        cls.app = QApplication.instance() or QApplication(['authored-idle-desktop-tests'])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.f = HostFixture(directory.name)
        project = self.f.project
        self.f.store.save(replace(project, animations=(), revision=project.revision + 1),
                          expected_revision=project.revision)
        self.catalog = self.f.root / 'empty-session-catalog.db'
        with AnimationCatalog(self.catalog):
            pass
        self.window = MainWindow(catalog_path=self.catalog)
        self.window.controller.open(self.f.store.root)
        self.window.refresh_project()
        self.addCleanup(self.close_window)

    def wait_for_jobs(self):
        deadline = time.monotonic() + 5
        while self.window.jobs.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.window.jobs.busy)

    def close_window(self):
        if self.window.jobs.busy:
            self.window.jobs.cancel()
            self.wait_for_jobs()
        dialog = getattr(self.window, '_authored_idle_dialog', None)
        if dialog is not None:
            dialog.reject()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_source_review_requires_no_clip_and_does_not_author(self):
        self.assertTrue(self.window.authored_idle_action.isEnabled())
        self.assertFalse(self.window.target_action_action.isEnabled())
        with patch('ucc.jobs.authored_idle.author_original_idle') as author:
            self.window.authored_idle_action.trigger()
            self.wait_for_jobs()
            dialog = self.window._authored_idle_dialog
            self.assertIsNone(dialog.choice)
            dialog.reject()
            self.assertIsNone(self.window._authored_idle_context)
            author.assert_not_called()

    def test_candidate_result_remains_visible_after_proof_failure(self):
        from ucc.desktop.authored_idle_authoring_workflow import _accepted

        self.window.authored_idle_action.trigger()
        self.wait_for_jobs()
        actual_dialog = self.window._authored_idle_dialog
        context = self.window._authored_idle_context
        actual_dialog.reject()
        self.window._blender_executable = self.f.blender
        choice = SimpleNamespace(permissions=self.f.inspection.permissions, source_policy_records=self.f.records,
            purpose=self.f.inspection.purpose, original_procedural_recipe_declared=True,
            private_authored_output_preview_confirmed=True, candidate_destination=self.f.destination.path,
            proof_destination=self.f.root / 'outputs/loop-proof')
        dialog = SimpleNamespace(choice=choice, deleteLater=lambda: None)
        self.window._authored_idle_dialog = dialog
        output = SimpleNamespace(directory=choice.candidate_destination, receipt_sha256='a'*64)
        with patch('ucc.desktop.authored_idle_authoring_workflow.bundled_worker_path', return_value=self.f.worker), \
             patch('ucc.jobs.authored_idle.author_original_idle', return_value=output) as author, \
             patch('ucc.jobs.authored_idle_loop_proof.publish_authored_idle_loop_proof',
                   side_effect=ProjectStorageError('NONSHIPPING proof failure')) as proof:
            _accepted(self.window, context, dialog)
            self.wait_for_jobs()
        self.assertEqual(author.call_args.kwargs['inspection_request'].permissions, choice.permissions)
        self.assertEqual(proof.call_args.kwargs['expected_receipt_sha256'], output.receipt_sha256)
        self.assertIn('candidate saved', self.window.log.toPlainText())
        self.assertIn('NONSHIPPING proof failure', self.window.log.toPlainText())
