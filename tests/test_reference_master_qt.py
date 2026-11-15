"""Desktop state/dispatch only; synthetic fixtures never prove Blender geometry."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.commands import CharacterSession
from ucc.core.errors import CompatibilityError, ValidationError
from ucc.core.models import PartInstance
from ucc.core.reference_master_intent import supports_referenced_master_intent
from ucc.jobs.reference_master_revision import ReferencedMasterResult
import test_hand_qt as legacy

if legacy.QApplication is not None:
    from PySide6.QtWidgets import QMessageBox
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
    from ucc.desktop.face_workflow import start_face, apply_face_from_desktop
    from ucc.desktop.generation import generate_from_desktop, refit_from_desktop
    from ucc.desktop.reference_master_workflow import run_referenced_master


@unittest.skipIf(legacy.QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class ReferencedMasterQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if legacy.QApplication is None:
            raise RuntimeError('Reference-master Qt tests required: '+legacy.IMPORT_ERROR)
        cls.app = legacy.QApplication.instance() or legacy.QApplication(['reference-master-tests'])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.f = ReferenceMasterFixture(self.root/'fixture')
        self.controller = DesktopController(); self.controller.open(self.f.store.root)
        self.window = MainWindow(self.controller); self.addCleanup(self.window.deleteLater)
        self.exe = self.root/'not-executed.exe'; self.exe.write_bytes(b'NOT_AN_EXECUTABLE')
        self.window._blender_executable = self.exe
        self.window._catalog_path = lambda: self.f.database
        self.initial = self.controller.require_project()

    def test_face_intent_controls_save_history_and_general_guard(self):
        self.assertTrue(self.controller.view().referenced_master_intent)
        self.assertTrue(self.window.character.face.isEnabled())
        self.assertTrue(self.window.character.morph_box.isEnabled())
        with self.assertRaises(CompatibilityError):
            CharacterSession(self.initial).set_face_parameter('nose_width', .7)
        before = self.f.store.file.read_bytes()
        self.window.character.face.value.setValue(.7)
        self.window.character.face.value.editingFinished.emit()
        self.assertTrue(self.controller.dirty)
        self.assertEqual(self.f.store.file.read_bytes(), before)
        self.assertEqual(dict(self.controller.require_project().facial_parameters), {'nose_width': .7})
        self.window.save_project()
        self.assertEqual(self.f.store.load().animations, self.initial.animations)
        self.assertEqual(self.f.store.load().parts, self.initial.parts)
        self.window.undo_action.trigger(); self.window.save_action.trigger()
        self.assertEqual(self.f.store.load().facial_parameters, self.initial.facial_parameters)
        self.window.redo_action.trigger(); self.window.save_action.trigger()
        self.assertEqual(dict(self.f.store.load().facial_parameters), {'nose_width': .7})

    def test_unsupported_metadata_remains_guarded(self):
        variants = [replace(self.initial, expression=None, schema_version=2), replace(self.initial, animations=()),
            replace(self.initial, parts=(PartInstance('unknown', 'unknown-asset', 'hand.L'),)),
            replace(self.initial, parts=(replace(self.initial.parts[0], visible=False),))]
        for current in variants:
            self.assertFalse(supports_referenced_master_intent(current))
            with self.assertRaises(CompatibilityError):
                CharacterSession(current).set_referenced_face_parameter('nose_width', .7)
        self.assertTrue(supports_referenced_master_intent(replace(self.initial, parts=())))

    def test_existing_face_button_captures_exact_catalog_and_saved_input(self):
        with patch.object(self.window, '_submit') as submit:
            self.window.character.face.apply.click()
        self.assertEqual(submit.call_args.args[0], 'face_revision')
        with patch('ucc.desktop.face_workflow.apply_face_from_desktop') as run:
            submit.call_args.args[1]()
        self.assertEqual(run.call_args.kwargs['database_path'], self.f.database)
        self.assertEqual(run.call_args.kwargs['master_blend'], self.initial.master_blend)
        self.assertEqual(run.call_args.kwargs['revision'], self.initial.revision)
        self.assertIs(run.call_args.kwargs['cancel'], submit.call_args.kwargs['cancel'])

    def test_existing_body_and_generate_capture_catalog_and_master(self):
        for method, function, kind in ((self.window.apply_saved_body, 'refit_from_desktop', 'body_refit'),
                (self.window.generate_humanoid, 'generate_from_desktop', 'generate_humanoid')):
            with (patch('ucc.desktop.window.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes),
                  patch('ucc.desktop.window.QFileDialog.getOpenFileName', return_value=(str(self.exe), '')),
                  patch.object(self.window, '_submit') as submit):
                method()
            self.assertEqual(submit.call_args.args[0], kind)
            with patch('ucc.desktop.window.'+function) as run:
                submit.call_args.args[1]()
            self.assertEqual(run.call_args.kwargs['database_path'], self.f.database)
            self.assertEqual(run.call_args.kwargs['master_blend'], self.initial.master_blend)

    def test_all_three_worker_adapters_route_only_to_reference_transaction(self):
        for adapter, operation in ((apply_face_from_desktop, 'face_revision'),
                (refit_from_desktop, 'body_refit'), (generate_from_desktop, 'body_generation')):
            with patch('ucc.desktop.reference_master_workflow.run_referenced_master', return_value='unit-result') as run:
                value = adapter(self.f.store, blender_exe=self.exe, project_id=self.initial.project_id,
                    revision=self.initial.revision, master_blend=self.initial.master_blend,
                    cancel=Event(), database_path=self.f.database)
            self.assertEqual(value, 'unit-result')
            self.assertEqual(run.call_args.kwargs['operation'], operation)
            self.assertEqual(run.call_args.args[1], self.f.database)

    def test_exact_dispatch_guard_precedes_probe_and_fresh_api_receives_bindings(self):
        args = dict(operation='face_revision', blender_exe=self.exe, project_id=self.initial.project_id,
            revision=self.initial.revision, master_blend=self.initial.master_blend, cancel=Event())
        module = 'ucc.desktop.reference_master_workflow.'
        with patch(module+'discover_face_data') as probe:
            with self.assertRaises(ValidationError): run_referenced_master(self.f.store, None, **args)
            with self.assertRaises(ValidationError):
                run_referenced_master(self.f.store, self.f.database, **{**args, 'master_blend':'master/foreign.blend'})
        probe.assert_not_called()
        with (patch(module+'discover_face_data', return_value=self.root) as probe,
              patch(module+'revise_referenced_master', return_value='verified') as fresh):
            self.assertEqual(run_referenced_master(self.f.store, self.f.database, **args), 'verified')
        self.assertEqual(fresh.call_args.kwargs['expected_master_blend'], self.initial.master_blend)
        self.assertEqual(fresh.call_args.kwargs['expected_revision'], self.initial.revision)

    def test_start_keeps_saved_history_actions_locked(self):
        self.controller.rename('Saved history'); self.controller.save(); self.window.refresh_project()
        self.assertTrue(self.controller.view().can_undo)
        for method in (lambda: start_face(self.window), self.window.apply_saved_body, self.window.generate_humanoid):
            def submit(kind, operation, **kwargs):
                self.window._work_kind = kind; self.window._busy_changed(True)
            with (patch('ucc.desktop.window.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes),
                  patch('ucc.desktop.window.QFileDialog.getOpenFileName', return_value=(str(self.exe), '')),
                  patch.object(self.window, '_submit', side_effect=submit)):
                method()
            for action in (self.window.undo_action, self.window.redo_action, self.window.save_action,
                           self.window.new_action, self.window.open_action):
                self.assertFalse(action.isEnabled())
            self.assertTrue(self.window.cancel_generation_action.isEnabled())
            self.window._busy_changed(False)

    def test_refresh_cannot_unlock_saved_history_during_live_job(self):
        self.controller.rename('Saved undo history'); self.controller.save(); self.window.refresh_project()
        with patch.object(type(self.window.jobs), 'busy', new_callable=lambda: property(lambda _: True)):
            self.window._work_kind = 'face_revision'; self.window._busy_changed(True)
            self.window.refresh_project()
            self.assertFalse(self.window.undo_action.isEnabled())
            self.assertFalse(self.window.redo_action.isEnabled())
            self.assertFalse(self.window.save_action.isEnabled())
        self.window._busy_changed(False)

    def test_completion_preserves_history_and_rejects_stale_disk(self):
        saved = self.f.saved_metadata_revision()
        result = ReferencedMasterResult(saved, object(), 'face_revision', 'e'*64, {})
        self.window._work_kind = 'face_revision'; self.window._job_success(result)
        self.assertEqual(self.controller.require_project(), saved)
        self.window.undo_action.trigger(); self.window.save_action.trigger()
        self.assertEqual(self.f.store.load().master_blend, self.initial.master_blend)
        self.window.redo_action.trigger(); self.window.save_action.trigger()
        redone = self.f.store.load(); self.assertEqual(redone.parts, saved.parts)
        with self.assertRaises(ValidationError): self.controller.accept_saved_reference_master(saved)

    def test_external_save_error_reloads_and_cancel_preserves_session(self):
        external = self.f.store.save(replace(self.initial, name='External edit', revision=self.initial.revision+1),
                                     expected_revision=self.initial.revision)
        self.window._work_kind = 'body_refit'; self.window._job_error('ProjectConflict: Actual saved edit')
        self.assertEqual(self.controller.require_project(), external)
        self.assertIn('preserved and reloaded', self.window.log.toPlainText())
        with patch.object(type(self.window.jobs), 'cancel_requested', new_callable=lambda: property(lambda _: True)):
            self.window._job_error('WorkerFailure: cancelled')
        self.assertEqual(self.controller.require_project(), external)
        self.assertIn('cancelled', self.window.log.toPlainText())


if __name__ == '__main__': unittest.main()
