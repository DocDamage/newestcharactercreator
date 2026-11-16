"""Synthetic metadata/Qt dispatch only; real Blender/app verification is separate."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import os,tempfile,unittest
from unittest.mock import patch,PropertyMock
from fixtures.material_desktop_logic import install_synthetic_desktop_master
from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.commands import CharacterSession
from ucc.core.errors import ValidationError,CompatibilityError
from ucc.core.skin_material import APPEARANCE_KEY
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.desktop.controller import DesktopController
import test_desktop_qt as qt


class MaterialMasterHistoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.f=ReferenceMasterFixture(Path(temp.name).resolve())
        current=self.f.store.load();self.before=self.f.store.save(replace(current,animations=(),appearance=tuple(sorted(((APPEARANCE_KEY,'a'*64),('other','retained')))),revision=current.revision+1),expected_revision=current.revision)
        relative=install_synthetic_desktop_master(self.f.store)
        self.saved=replace(self.before,master_blend=relative,
            parts=(replace(self.before.parts[0],part_asset_id='ucc-hand-v1-'+'e'*64+'-shorter'),),
            appearance=tuple(sorted(((APPEARANCE_KEY,'b'*64),('other','retained')))),revision=self.before.revision+1,geometry_state='generated_unverified',rig_profile=None)

    def test_atomic_master_material_hand_history_preserves_intent_and_variant(self):
        session=CharacterSession(self.before);session.accept_saved_material_master(self.saved)
        undone=session.undo();self.assertEqual(undone,replace(self.before,revision=undone.revision))
        redone=session.redo();self.assertEqual(redone,replace(self.saved,revision=redone.revision))
        self.assertEqual(dict(redone.appearance)[APPEARANCE_KEY],'b'*64)

    def test_unrelated_or_incomplete_changes_cannot_enter_history(self):
        changes=[{'name':'Unrelated'},{'appearance':self.before.appearance},{'parts':()},
            {'parameters':(('height',.8),('muscle',.5),('weight',.5))},{'animations':self.f.project.animations},
            {'expression':replace(self.before.expression,parameters=tuple((k,0.) for k,v in self.before.expression.parameters))},{'revision':999},
            {'parts':(replace(self.saved.parts[0],part_asset_id='ucc-hand-v1-'+'e'*64+'-longer'),)}]
        for change in changes:
            session=CharacterSession(self.before)
            with self.subTest(change=change),self.assertRaises((ValidationError,CompatibilityError)):
                session.accept_saved_material_master(replace(self.saved,**change))
            self.assertFalse(session.can_undo)

    def test_eligibility_and_face_intent_are_narrow_and_noop_has_no_history(self):
        self.assertTrue(supports_material_master_intent(self.before));session=CharacterSession(self.before)
        self.assertEqual(session.accept_saved_material_master(self.before),self.before);self.assertFalse(session.can_undo)
        changed=session.set_material_face_parameter('nose_width',.7);self.assertEqual(dict(changed.facial_parameters)['nose_width'],.7)
        for bad in (replace(self.before,appearance=()),replace(self.before,animations=self.f.project.animations),
                replace(self.before,parts=(replace(self.before.parts[0],visible=False),)),replace(self.before,expression=None,schema_version=2)):
            self.assertFalse(supports_material_master_intent(bad))
            with self.assertRaises(CompatibilityError):CharacterSession(bad).set_material_face_parameter('nose_width',.7)

    def test_controller_adoption_preserves_history_and_rejects_dirty_or_stale(self):
        controller=DesktopController();controller.open(self.f.store.root)
        saved=self.f.store.save(self.saved,expected_revision=self.before.revision)
        controller.accept_saved_material_master(saved);controller.undo();controller.save()
        self.assertEqual(controller.require_project().master_blend,self.before.master_blend)
        self.assertEqual(controller.require_project().appearance,self.before.appearance)
        controller.redo();controller.save();self.assertEqual(controller.require_project().master_blend,saved.master_blend)
        controller.rename('unsaved')
        with self.assertRaises(ValidationError):controller.accept_saved_material_master(saved)


@unittest.skipIf(qt.QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class MaterialMasterQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if qt.QApplication is None:raise RuntimeError(qt.IMPORT_ERROR)
        cls.app=qt.QApplication.instance() or qt.QApplication(['material-master-qt'])

    def setUp(self):
        MaterialMasterHistoryTests.setUp(self)
        from ucc.desktop.window import MainWindow
        self.controller=DesktopController();self.controller.open(self.f.store.root)
        self.window=MainWindow(self.controller);self.addCleanup(self.window.deleteLater)
        self.window._blender_executable=self.f.root/'UNIT-never-executed.exe';self.window._blender_executable.write_bytes(b'UNIT NOT EXECUTABLE')

    def test_existing_controls_allow_supported_intent_and_dispatch_three_operations(self):
        from PySide6.QtWidgets import QMessageBox
        self.assertTrue(self.window.character.morph_box.isEnabled());self.assertTrue(self.window.character.face.isEnabled())
        self.window.character.face.value.setValue(.7);self.window.character.face.value.editingFinished.emit()
        self.assertTrue(self.controller.dirty);self.window.save_project()
        for action,kind in [(self.window.apply_saved_body,'body_refit'),(self.window.generate_humanoid,'generate_humanoid'),(self.window.character.face.apply.click,'face_revision')]:
            with patch('ucc.desktop.window.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch.object(self.window,'_submit') as submit:
                action()
            self.assertEqual(submit.call_args.args[0],kind)

    def test_adapters_route_to_material_transaction_and_guard_stale_ids(self):
        from ucc.desktop.generation import generate_from_desktop,refit_from_desktop
        from ucc.desktop.face_workflow import apply_face_from_desktop
        for adapter,operation in [(generate_from_desktop,'body_generation'),(refit_from_desktop,'body_refit'),(apply_face_from_desktop,'face_revision')]:
            with patch('ucc.desktop.material_master_workflow.run_material_master',return_value='UNIT-only') as run:
                result=adapter(self.f.store,blender_exe=self.window._blender_executable,project_id=self.before.project_id,revision=self.before.revision,master_blend=self.before.master_blend,cancel=Event())
            self.assertEqual(result,'UNIT-only');self.assertEqual(run.call_args.kwargs['operation'],operation)
        from ucc.desktop.material_master_workflow import run_material_master
        with self.assertRaises(ValidationError):run_material_master(self.f.store,operation='body_refit',blender_exe=self.window._blender_executable,
            project_id=self.before.project_id,revision=999,master_blend=self.before.master_blend,cancel=Event())

    def test_successful_completion_adopts_one_history_step_and_dirty_completion_rejects(self):
        from ucc.core.master_versions import MasterRevision
        from ucc.jobs.skin_material_revision import SkinMaterialRevision
        from ucc.desktop.face_workflow import finish_face_build
        saved=self.f.store.save(self.saved,expected_revision=self.before.revision)
        revision=MasterRevision(saved,self.f.store.root/saved.master_blend,Path(saved.master_blend).stem,3300,False)
        result=SkinMaterialRevision(revision,'b'*64,'c'*64,'e'*64,{'UNIT_NOT_GEOMETRY':True})
        with patch('ucc.desktop.material_master_workflow.registered_material_binding',return_value={'UNIT_NOT_PROOF':True}):
            self.assertTrue(finish_face_build(self.window,result))
        self.assertEqual(self.controller.require_project(),saved);self.assertIn('Chosen material',self.window.log.toPlainText())
        self.window.undo_action.trigger();self.assertEqual(self.controller.require_project().appearance,self.before.appearance)
        self.window.redo_action.trigger();self.assertEqual(self.controller.require_project().appearance,saved.appearance)
        self.controller.rename('UNIT unsaved user edit')
        with patch('ucc.desktop.material_master_workflow.registered_material_binding'),patch.object(self.window,'_error') as error:
            self.assertTrue(finish_face_build(self.window,result))
        error.assert_called_once();self.assertEqual(self.controller.require_project().name,'UNIT unsaved user edit')

    def test_noop_completion_keeps_history_and_stale_result_does_not_replace_session(self):
        from ucc.jobs.skin_material_revision import MaterialMasterNoOp
        from ucc.desktop.face_workflow import finish_face_build
        result=MaterialMasterNoOp(self.before,'face_revision',{'UNIT_NOT_GEOMETRY':True},self.f.root)
        with patch('ucc.desktop.material_master_workflow.registered_material_binding'):
            self.assertTrue(finish_face_build(self.window,result))
        self.assertFalse(self.controller.session.can_undo);self.assertIn('no new master revision',self.window.log.toPlainText())
        current=self.f.store.load();concurrent=self.f.store.save(replace(current,name='UNIT external user change',revision=current.revision+1),expected_revision=current.revision)
        with patch('ucc.desktop.material_master_workflow.registered_material_binding'),patch.object(self.window,'_error') as error:
            self.assertTrue(finish_face_build(self.window,result))
        error.assert_called_once();self.assertEqual(self.f.store.load(),concurrent)
        self.assertEqual(self.controller.require_project(),self.before)

    def test_busy_material_action_freezes_editing_and_forwards_existing_cancel_action(self):
        self.window._work_kind='body_refit';self.window._busy_changed(True)
        self.assertFalse(self.window.character.isEnabled());self.assertFalse(self.window.undo_action.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        with patch.object(self.window.jobs,'cancel',return_value=True) as cancel:
            self.window.cancel_generation_action.trigger()
        cancel.assert_called_once()

    def test_cancelled_material_job_reports_without_error_dialog_or_session_reload(self):
        self.window._work_kind='body_refit';before=self.controller.require_project()
        with patch.object(type(self.window.jobs),'cancel_requested',new_callable=PropertyMock,return_value=True),patch.object(self.window,'_error') as error:
            self.window._job_error('WorkerFailure: Job cancelled')
        error.assert_not_called();self.assertIn('No new result was adopted',self.window.log.toPlainText())
        self.assertEqual(self.controller.require_project(),before)
        with patch.object(self.window,'_error') as error:self.window._job_error('UNIT source changed')
        error.assert_called_once_with('UNIT source changed')
