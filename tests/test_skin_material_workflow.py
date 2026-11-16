"""Actual Qt dispatch with synthetic storage only; never live Blender proof."""
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch
import os,unittest
import test_desktop_qt as qt
import test_material_master_desktop as base_tests
from ucc.core.errors import ValidationError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec


@unittest.skipIf(qt.QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class SkinMaterialWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if qt.QApplication is None:raise RuntimeError(qt.IMPORT_ERROR)
        cls.app=qt.QApplication.instance() or qt.QApplication(['skin-workflow-tests'])

    def setUp(self):
        base_tests.MaterialMasterHistoryTests.setUp(self)
        current=self.f.store.load()
        self.before=self.f.store.save(replace(current,appearance=(('other','retained'),),revision=current.revision+1),expected_revision=current.revision)
        from ucc.desktop.controller import DesktopController
        from ucc.desktop.window import MainWindow
        self.controller=DesktopController();self.controller.open(self.f.store.root)
        self.window=MainWindow(self.controller);self.addCleanup(self.window.deleteLater)
        self.exe=self.f.root/'UNIT-not-executed.exe';self.exe.write_bytes(b'UNIT NOT EXECUTABLE');self.window._blender_executable=self.exe
        self.spec=SkinMaterialSpec((148/255,96/255,61/255),.65)

    def test_draft_leaves_disk_and_session_unchanged_and_apply_captures_exact_source(self):
        controls=self.window.character.material;self.assertTrue(controls.isEnabled());before=self.f.store.file.read_bytes()
        controls.color.setText('#94603d');controls.roughness.setValue(.65)
        self.assertFalse(self.controller.dirty);self.assertEqual(self.controller.require_project(),self.before)
        self.assertEqual(self.f.store.file.read_bytes(),before)
        with patch.object(self.window,'_submit') as submit:controls.apply.click()
        self.assertEqual(submit.call_args.args[0],'skin_material')
        with patch('ucc.desktop.skin_material_workflow.apply_skin_from_desktop') as run:submit.call_args.args[1]()
        self.assertEqual(run.call_args.kwargs['spec'],self.spec);self.assertEqual(run.call_args.kwargs['master_blend'],self.before.master_blend)
        self.assertEqual(run.call_args.kwargs['revision'],self.before.revision)
        self.assertIs(run.call_args.kwargs['cancel'],submit.call_args.kwargs['cancel'])

    def test_explicit_first_assignment_completion_keeps_undo_and_redo(self):
        from ucc.core.master_versions import MasterRevision
        from ucc.jobs.skin_material_revision import SkinMaterialRevision
        saved=replace(self.saved,revision=self.before.revision+1)
        saved=self.f.store.save(saved,expected_revision=self.before.revision)
        result=SkinMaterialRevision(MasterRevision(saved,self.f.store.root/saved.master_blend,Path(saved.master_blend).stem,3300,False),'b'*64,'c'*64,'e'*64,{'UNIT_NOT_GEOMETRY':True})
        self.window._work_kind='skin_material'
        with patch('ucc.desktop.skin_material_workflow.registered_material_binding',return_value={'UNIT_NOT_PROOF':True}):self.window._job_success(result)
        self.assertEqual(self.controller.require_project(),saved)
        self.window.undo_action.trigger();self.window.save_action.trigger();self.assertNotIn(APPEARANCE_KEY,dict(self.controller.require_project().appearance))
        self.window.redo_action.trigger();self.window.save_action.trigger();self.assertEqual(self.controller.require_project().master_blend,saved.master_blend)

    def test_dirty_stale_and_unsupported_requests_never_start_material_worker(self):
        from ucc.desktop.skin_material_workflow import start_skin_material,apply_skin_from_desktop
        self.controller.rename('UNIT pending edit')
        with patch.object(self.window,'_error') as error,patch.object(self.window,'_submit') as submit:start_skin_material(self.window,self.spec)
        error.assert_called_once();submit.assert_not_called()
        with patch('ucc.desktop.skin_material_workflow.discover_face_data') as discover,self.assertRaises(ValidationError):
            apply_skin_from_desktop(self.f.store,spec=self.spec,blender_exe=self.exe,project_id=self.before.project_id,revision=999,master_blend=self.before.master_blend,cancel=Event())
        discover.assert_not_called()

    def test_pending_physical_intent_disables_material_apply_with_explanation(self):
        self.controller.set_morph('height',.7);self.window.save_project()
        self.assertFalse(self.window.character.material.isEnabled())
        self.assertIn('Apply saved body and face changes',self.window.character.material.status.text())
