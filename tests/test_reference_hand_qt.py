"""Real Qt eligibility/dispatch with synthetic fixtures; not Blender evidence."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import test_hand_qt as legacy
from ucc.core.errors import CompatibilityError, ValidationError
from ucc.core.hand_parts import ensure_source_intent
from ucc.jobs.hand_storage import read_hand_manifest
if legacy.QApplication is not None:
    from ucc.desktop.hand_workflow import start_hands, start_hand_preview, _run


@unittest.skipIf(legacy.QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class ReferencedHandQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if legacy.QApplication is None:
            raise RuntimeError('Reference-hand Qt tests required: '+legacy.IMPORT_ERROR)
        cls.app = legacy.QApplication.instance() or legacy.QApplication(['reference-hand-tests'])

    def setUp(self):
        legacy.HandQtTests.setUp(self)
        self.identity, self.worker = legacy.HandQtTests.library_fixture(self)
        current = self.controller.require_project()
        saved = self.controller.store.save(replace(current, animations=('fixture-source#clip-0000',),
            revision=current.revision+1), expected_revision=current.revision)
        self.controller.open(self.controller.store.root); self.window.refresh_project()
        self.controls = self.window.character.hands
        self.initial = saved; self.before = self.controller.store.file.read_bytes()
        self.database = self.root/'structural-only-catalog.sqlite3'
        self.window._catalog_path = lambda: self.database

    def test_existing_apply_eligibility_does_not_remove_core_admission_guard(self):
        self.assertTrue(self.controls.choice.isEnabled())
        self.assertFalse(self.controls.build.isEnabled()); self.assertFalse(self.controls.preview.isEnabled())
        self.controls.choice.setCurrentIndex(self.controls.choice.findData('shorter'))
        self.assertTrue(self.controls.apply.isEnabled())
        self.assertIn('Source references retained', self.controls.status.text())
        manifest, _ = read_hand_manifest(self.controller.store, self.identity)
        with self.assertRaises(CompatibilityError): ensure_source_intent(self.initial, manifest['recipe'])
        self.assertEqual(self.controller.store.file.read_bytes(), self.before)

    def test_choice_dispatch_captures_catalog_and_keeps_provisional_intent(self):
        self.controls.choice.setCurrentIndex(self.controls.choice.findData('longer'))
        with (patch('ucc.desktop.hand_workflow._executable', return_value=Path('selected.exe')),
              patch.object(self.window, '_submit') as submit,
              patch.object(self.window, '_clear_preview') as clear):
            self.controls.apply.click()
        self.assertEqual(submit.call_args.args[0], 'hand_revision'); clear.assert_called_once()
        with patch('ucc.desktop.hand_workflow._run') as run:
            submit.call_args.args[1]()
        self.assertEqual(run.call_args.args[-2:], (self.identity, 'longer'))
        self.assertEqual(run.call_args.kwargs['database'], self.database)
        self.assertIs(run.call_args.args[3], submit.call_args.kwargs['cancel'])
        self.assertEqual(self.controller.require_project(), self.initial)
        self.assertFalse(self.controller.dirty); self.assertEqual(self.controller.store.file.read_bytes(), self.before)

    def test_background_dispatch_uses_fresh_reference_api_and_never_legacy_revision(self):
        with (patch('ucc.desktop.hand_workflow.discover_face_data', return_value=self.root/'installed') as data,
              patch('ucc.jobs.reference_hand_revision.apply_referenced_hand_revision', return_value='verified') as fresh,
              patch('ucc.desktop.hand_workflow.apply_hand_revision') as old):
            result = _run(self.controller.store, self.initial, Path('selected.exe'), None,
                          self.identity, 'longer', database=self.database)
        self.assertEqual(result, 'verified'); old.assert_not_called(); data.assert_called_once()
        self.assertEqual(fresh.call_args.args, (self.controller.store, self.database))
        self.assertEqual(fresh.call_args.kwargs['expected_revision'], self.initial.revision)
        self.assertEqual(fresh.call_args.kwargs['manifest_sha256'], self.identity)

    def test_missing_dispatch_catalog_rejects_before_installed_asset_probe(self):
        with patch('ucc.desktop.hand_workflow.discover_face_data') as data:
            with self.assertRaises(ValidationError):
                _run(self.controller.store, self.initial, Path('selected.exe'), None, self.identity, 'longer')
        data.assert_not_called()

    def test_start_keeps_history_actions_locked_after_synchronous_busy_callback(self):
        self.controller.rename('Saved rename with undo history'); self.controller.save()
        self.window.refresh_project(); self.assertTrue(self.controller.view().can_undo)
        self.controls.choice.setCurrentIndex(self.controls.choice.findData('longer'))
        def submit(kind, operation, **kwargs):
            self.window._work_kind = kind
            self.window._busy_changed(True)
        with (patch('ucc.desktop.hand_workflow._executable', return_value=Path('not-executed.exe')),
              patch.object(self.window, '_submit', side_effect=submit)):
            start_hands(self.window)
        self.assertFalse(self.window.undo_action.isEnabled())
        self.assertFalse(self.window.redo_action.isEnabled()); self.assertFalse(self.window.save_action.isEnabled())
        self.assertFalse(self.window.character.isEnabled()); self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertIn('hand', self.window.statusBar().currentMessage().casefold())
        self.window._busy_changed(False)

    def test_unsupported_build_and_preview_remain_guarded(self):
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_hands(self.window, build=True)
            self.assertIn('existing compatible hand library', error.call_args.args[0])
            start_hand_preview(self.window)
            self.assertIn('not yet validated', error.call_args.args[0])
        submit.assert_not_called(); self.assertEqual(self.controller.store.file.read_bytes(), self.before)

    def test_dirty_and_incompatible_intent_disable_apply_and_block_submission(self):
        self.controller.rename('Unsaved'); self.window.refresh_project()
        self.assertFalse(self.controls.choice.isEnabled()); self.assertFalse(self.controls.apply.isEnabled())
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_hands(self.window)
        submit.assert_not_called(); self.assertIn('Save', error.call_args.args[0])
        self.controller.open(self.controller.store.root)
        altered = replace(self.initial, parameters=(('height', .6), ('muscle', .5), ('weight', .5)),
                          revision=self.initial.revision+1)
        self.controller.store.save(altered, expected_revision=self.initial.revision)
        self.controller.open(self.controller.store.root); self.window.refresh_project()
        self.assertIsNone(self.controls.manifest_sha256); self.assertFalse(self.controls.choice.isEnabled())

    def test_history_save_reopen_retains_refs_and_couples_hand_with_master(self):
        from ucc.core.master_versions import stage_unverified_master
        from ucc.core.models import PartInstance
        from ucc.core.hand_parts import hand_asset_id
        source = self.worker/'new-unit-only.blend'; source.write_bytes(b'BLENDER'+b'unit-not-real-scene'*150)
        revision = stage_unverified_master(self.controller.store, source, authorized_source_root=self.worker,
            expected_project=self.initial, expected_revision=self.initial.revision,
            proposed_parts=(PartInstance('unit-hand', hand_asset_id(self.identity, 'shorter'), 'hand.L'),))
        self.controller.accept_saved_part_master(revision.project, manifest_sha256=self.identity)
        self.window.refresh_project(); self.window.undo_action.trigger(); self.window.save_action.trigger()
        undone = self.controller.store.load()
        self.assertEqual(undone.master_blend, self.initial.master_blend); self.assertEqual(undone.parts, ())
        self.assertEqual(undone.animations, self.initial.animations)
        self.window.redo_action.trigger(); self.window.save_action.trigger()
        self.controller.open(self.controller.store.root); self.window.refresh_project()
        self.assertEqual(self.controller.require_project().master_blend, revision.project.master_blend)
        self.assertEqual(self.controller.require_project().animations, self.initial.animations)
        self.assertEqual(self.controls.choice.currentData(), 'shorter')


if __name__ == '__main__': unittest.main()
