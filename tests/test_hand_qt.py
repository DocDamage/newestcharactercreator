"""Actual Qt controls with structural-only fixtures; real Blender gates are separate."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from hashlib import sha256
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication=None;IMPORT_ERROR=str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class HandQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError('Hand Qt tests required: '+IMPORT_ERROR)
        cls.app=QApplication.instance() or QApplication(['hand-contract-tests'])

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.controller=DesktopController();self.controller.create(self.root/'project','Hand controls fixture')
        self.window=MainWindow(self.controller);self.addCleanup(self.window.deleteLater)

    def library_fixture(self):
        from ucc.core.master_versions import stage_unverified_master
        from ucc.core.hand_parts import build_hand_library_recipe,build_hand_manifest
        from ucc.jobs.hand_storage import publish_asset,publish_manifest
        worker=self.root/'worker';worker.mkdir()
        # Synthetic structural bytes only, not usable Blender geometry.
        source=worker/'master.blend';source.write_bytes(b'BLENDER'+b'unit-structure-only'*150)
        stage_unverified_master(self.controller.store,source,authorized_source_root=worker)
        self.controller.open(self.controller.store.root);project=self.controller.require_project();assets={}
        for variant in ('shorter','longer'):
            path=worker/(variant+'.blend');path.write_bytes(b'BLENDER'+variant.encode()*500)
            digest=sha256(path.read_bytes()).hexdigest();publish_asset(self.controller.store,path,digest,worker)
            assets[variant]={'sha256':digest,'observation_sha256':'b'*64}
        identity=publish_manifest(self.controller.store,build_hand_manifest(
            build_hand_library_recipe(project,sha256(source.read_bytes()).hexdigest()),assets))
        self.window.refresh_project()
        return identity,worker

    def test_choices_are_disabled_until_saved_master_and_registered_library(self):
        controls=self.window.character.hands
        self.assertFalse(controls.build.isEnabled());self.assertFalse(controls.apply.isEnabled())
        identity,_=self.library_fixture()
        self.assertEqual(controls.manifest_sha256,identity)
        self.assertTrue(controls.build.isEnabled());self.assertTrue(controls.choice.isEnabled())
        self.assertTrue(controls.preview.isEnabled());self.assertFalse(controls.apply.isEnabled())

    def test_choice_is_provisional_and_dispatch_captures_exact_selection(self):
        from ucc.desktop.hand_workflow import start_hands
        identity,_=self.library_fixture();controls=self.window.character.hands
        before=self.controller.require_project();data=self.controller.store.file.read_bytes()
        controls.choice.setCurrentIndex(controls.choice.findData('longer'))
        self.assertTrue(controls.apply.isEnabled());self.assertFalse(self.controller.dirty)
        self.assertEqual(self.controller.require_project(),before)
        with (patch('ucc.desktop.hand_workflow._executable',return_value=Path('selected-blender.exe')),
              patch.object(self.window,'_submit') as submit,patch.object(self.window,'_clear_preview') as clear):
            start_hands(self.window)
        self.assertEqual(submit.call_args.args[0],'hand_revision');clear.assert_called_once()
        with patch('ucc.desktop.hand_workflow._run') as run:
            submit.call_args.args[1]()
        self.assertEqual(run.call_args.args[-2:],(identity,'longer'))
        self.assertEqual(self.controller.store.file.read_bytes(),data)

    def test_unsaved_settings_cannot_start_a_hand_job(self):
        from ucc.desktop.hand_workflow import start_hands
        self.library_fixture();self.controller.rename('Unsaved change')
        with patch.object(self.window,'_error') as error,patch.object(self.window,'_submit') as submit:
            start_hands(self.window,build=True)
        submit.assert_not_called();self.assertIn('Save',error.call_args.args[0])

    def test_hand_tasks_freeze_edits_and_allow_cooperative_cancellation(self):
        for kind in ('hand_library','hand_revision','hand_preview'):
            self.window._work_kind=kind;self.window._busy_changed(True)
            self.assertFalse(self.window.character.isEnabled())
            self.assertTrue(self.window.cancel_generation_action.isEnabled())
            self.assertIn('hand',self.window.statusBar().currentMessage())
            self.window._busy_changed(False)

    def test_saved_part_adoption_undo_restores_both_pointer_and_selection(self):
        from ucc.core.master_versions import stage_unverified_master
        from ucc.core.models import PartInstance
        from ucc.core.hand_parts import hand_asset_id
        identity,worker=self.library_fixture();before=self.controller.require_project()
        source=worker/'changed.blend';source.write_bytes(b'BLENDER'+b'changed-unit-structure-only'*130)
        result=stage_unverified_master(self.controller.store,source,authorized_source_root=worker,
             expected_project=before,proposed_parts=(PartInstance('unit-hand',hand_asset_id(identity,'shorter'),'hand.L'),))
        self.controller.accept_saved_part_master(result.project,manifest_sha256=identity)
        self.window.refresh_project();self.assertFalse(self.window.character.face.isEnabled())
        self.assertFalse(self.window.character.morph_box.isEnabled())
        self.window.undo();previous=self.controller.require_project()
        self.assertEqual(previous.parts,before.parts);self.assertEqual(previous.master_blend,before.master_blend)
        self.assertTrue(self.window.character.morph_box.isEnabled())
        self.window.redo();self.assertEqual(self.controller.require_project().parts,result.project.parts)


if __name__=='__main__':unittest.main()
