"""NONSHIPPING Qt workflow fixtures; no Blender, assets, or runtime rights proof."""
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from fixtures.authored_idle_host import HostFixture
from fixtures.authored_idle_contract import saved_project
from ucc.animations.catalog import AnimationCatalog
from ucc.core.authored_idle import PROFILE
from ucc.core.errors import ProjectStorageError

try:
    from PySide6.QtWidgets import QApplication, QFileDialog
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

    def test_separate_target_copy_uses_saved_project_and_leaves_it_open(self):
        original = self.window.controller.store
        project = self.window.controller.require_project()
        original.save(replace(project, animations=self.f.project.animations, revision=project.revision + 1),
                      expected_revision=project.revision)
        self.window.controller.open(original.root)
        self.window.refresh_project()
        original = self.window.controller.store
        project = self.window.controller.require_project()
        self.assertTrue(project.animations)
        self.assertTrue(self.window.private_target_copy_action.isEnabled())
        destination = self.f.root / 'private-target'
        with patch('ucc.desktop.private_target_copy_workflow.QFileDialog.getExistingDirectory',
                   return_value=str(self.f.root)), patch(
                       'ucc.desktop.private_target_copy_workflow.QInputDialog.getText',
                       return_value=(destination.name, True)), patch(
                       'ucc.jobs.private_target_copy.create_private_target_copy', return_value=destination) as copy:
            self.window.private_target_copy_action.trigger()
            self.wait_for_jobs()
        self.assertIs(copy.call_args.args[0], original)
        self.assertEqual(copy.call_args.kwargs['expected_project'], project)
        self.assertEqual(copy.call_args.kwargs['destination'], destination)
        self.assertIs(self.window.controller.store, original)
        self.assertIn('Open that folder', self.window.log.toPlainText())

    def test_separate_target_copy_is_disabled_for_unsaved_changes(self):
        self.assertTrue(self.window.private_target_copy_action.isEnabled())
        self.window.rename('Unsaved character name')
        try:
            self.assertFalse(self.window.private_target_copy_action.isEnabled())
        finally:
            self.window.controller.save()

    def test_candidate_result_remains_visible_after_proof_failure(self):
        from ucc.core.authored_idle import CLEAR_IDLE_PROFILE
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
            proof_destination=self.f.root / 'outputs/loop-proof', profile=CLEAR_IDLE_PROFILE)
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
        self.assertEqual(author.call_args.kwargs['inspection_request'].profile, CLEAR_IDLE_PROFILE)
        self.assertEqual(proof.call_args.kwargs['expected_receipt_sha256'], output.receipt_sha256)
        self.assertIn('candidate saved', self.window.log.toPlainText())
        self.assertIn('NONSHIPPING proof failure', self.window.log.toPlainText())

    def ready_walk_dialog(self):
        from ucc.desktop.authored_idle_authoring_workflow import WALK_SOURCE_REVIEW

        self.window.authored_walk_action.trigger()
        self.assertEqual(self.window._work_kind, WALK_SOURCE_REVIEW)
        self.wait_for_jobs()
        dialog = self.window._authored_idle_dialog
        self.assertEqual(dialog.windowTitle(), 'Create private original walk')
        row, = dialog.rows
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(self.f.policy), '')):
            row.choose.click()
        row.confirm.setChecked(True)
        row.note.setText(self.f.inspection.permissions[0].note)
        dialog.purpose.setText('NONSHIPPING private walk workflow fixture')
        dialog.recipe.setChecked(True)
        dialog.preview.setChecked(True)
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(self.f.destination.path.parent)):
            dialog.choose_parent.click()
        dialog.candidate_name.setText(self.f.destination.path.name)
        self.window._blender_executable = self.f.blender
        self.assertTrue(dialog.create_button.isEnabled())
        return dialog

    def test_walk_menu_dispatches_walk_with_exact_review_and_no_idle_proof(self):
        from ucc.desktop.authored_idle_authoring_workflow import AUTHOR_WALK

        self.assertTrue(self.window.authored_walk_action.isEnabled())
        self.assertIn('original walk', self.window.authored_walk_action.text())
        output = SimpleNamespace(directory=self.f.destination.path, receipt_sha256='a'*64,
                                 fbx_path=self.f.destination.path/'original_walk.fbx',
                                 review_path=self.f.destination.path/'authored_walk_review.blend',
                                 snapshot_sha256='b'*64)
        author = Mock(return_value=output)
        with patch.dict(sys.modules, {'ucc.jobs.authored_walk': SimpleNamespace(author_original_walk=author)}), \
             patch('ucc.jobs.authored_idle.author_original_idle') as idle, \
             patch('ucc.jobs.authored_idle_loop_proof.publish_authored_idle_loop_proof') as proof, \
             patch('ucc.desktop.authored_idle_authoring_workflow.bundled_worker_path', return_value=self.f.worker):
            dialog = self.ready_walk_dialog()
            author.assert_not_called()
            dialog.create_button.click()
            self.assertEqual(self.window._work_kind, AUTHOR_WALK)
            self.wait_for_jobs()
        idle.assert_not_called()
        proof.assert_not_called()
        author.assert_called_once()
        self.assertIs(author.call_args.args[0], self.window.controller.store)
        sent = author.call_args.kwargs
        self.assertEqual(sent['inspection_request'].permissions, self.f.inspection.permissions)
        self.assertEqual(sent['inspection_request'].profile, PROFILE)
        self.assertEqual(sent['inspection_request'].purpose, 'NONSHIPPING private walk workflow fixture')
        self.assertEqual(sent['source_policy_records'], self.f.records)
        self.assertEqual(sent['database_path'], self.catalog)
        self.assertEqual(sent['destination'], self.f.destination)
        self.assertEqual(sent['worker_script'], self.f.worker)
        self.assertIsNone(self.window._authored_idle_context)
        self.assertIn('Private original walk candidate saved', self.window.log.toPlainText())
        self.assertIn(output.receipt_sha256, self.window.log.toPlainText())

    def test_walk_action_part_gate_preserves_idle_menu_and_stops_direct_invocation(self):
        from ucc.desktop.authored_idle_authoring_workflow import start_authored_walk_authoring

        store = self.window.controller.store
        project = self.window.controller.require_project()
        store.save(replace(project, parts=saved_project(hand=True).parts, revision=project.revision + 1),
                   expected_revision=project.revision)
        self.window.controller.open(store.root)
        self.window.refresh_project()
        self.assertFalse(self.window.authored_walk_action.isEnabled())
        self.assertTrue(self.window.authored_idle_action.isEnabled())
        with patch.object(self.window, '_error') as error, \
             patch('ucc.jobs.authored_idle.inspect_idle_authoring_sources') as review:
            start_authored_walk_authoring(self.window)
        review.assert_not_called()
        self.assertFalse(self.window.jobs.busy)
        self.assertIn('no installed parts', error.call_args.args[0])

    def test_cancelled_walk_review_clears_context_and_keeps_idle_available(self):
        self.window.authored_walk_action.trigger()
        self.wait_for_jobs()
        dialog = self.window._authored_idle_dialog
        self.assertIsNone(dialog.choice)
        dialog.reject()
        self.assertIsNone(self.window._authored_idle_context)
        self.assertTrue(self.window.authored_idle_action.isEnabled())
        self.assertTrue(self.window.authored_walk_action.isEnabled())

    def test_cancel_running_walk_routes_cooperatively_and_keeps_candidate_unpublished(self):
        dialog = self.ready_walk_dialog()
        seen = Event()

        def author(_store, *, cancel, **_options):
            if cancel.wait(3):
                seen.set()
            raise ProjectStorageError('NONSHIPPING cooperative author cancellation')

        with patch.dict(sys.modules, {'ucc.jobs.authored_walk': SimpleNamespace(author_original_walk=author)}), \
             patch('ucc.desktop.authored_idle_authoring_workflow.bundled_worker_path', return_value=self.f.worker), \
             patch.object(self.window, '_error') as error:
            dialog.create_button.click()
            self.assertTrue(self.window.cancel_generation_action.isEnabled())
            self.assertIn('walk', self.window._target_action_progress_dialog.windowTitle())
            self.window.cancel_generation_action.trigger()
            self.assertIn('original walk', self.window.statusBar().currentMessage())
            self.wait_for_jobs()
        self.assertTrue(seen.is_set())
        error.assert_not_called()
        self.assertIsNone(self.window._authored_idle_context)
        self.assertFalse(self.f.destination.path.exists())
