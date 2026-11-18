"""Real Qt workers with explicit native API doubles; no native/quality proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fixtures.body_sprite_ui import ui_request, ui_origin
from ucc.core.errors import ProjectStorageError, UCCError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.body_sprite_export import BodySpriteExport

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit
    from ucc.desktop.background import BackgroundJobs
    from ucc.desktop import body_sprite_workflow as workflow
    from ucc.desktop.target_action_workflow import TargetActionContext, finish_target_action, target_action_error, resume_target_action
except ImportError:
    QApplication=None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 not installed')
class BodySpriteDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError('Body sprite desktop tests require Qt')
        cls.app=QApplication.instance() or QApplication(['body-sprite-desktop-tests'])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.request=ui_request();self.project=self.request.project
        file=self.root/'project.ucc.json';file.write_bytes(canonical_bytes(self.project.to_dict()))
        digest=sha256(file.read_bytes()).hexdigest()
        self.binding=replace(self.request.target_binding,target=replace(self.request.target_binding.target,project_sha256=digest))
        self.request=replace(self.request,target_binding=self.binding)
        self.database=self.root/'catalog.db';self.database.write_bytes(b'UNIT metadata token')
        self.store=SimpleNamespace(root=self.root,file=file,load=lambda:self.project)
        self.context=TargetActionContext(self.store,self.project,self.database,digest)
        self.review=SimpleNamespace(source=self.binding.source,project_sha256=digest,policy=object())
        class Harness(QMainWindow):
            def on_success(self,result):finish_target_action(self,result)
            def on_error(self,error):target_action_error(self,error)
            def on_busy(self,value):
                if not value:resume_target_action(self)
        self.window=Harness();self.window.log=QTextEdit(self.window)
        self.window.controller=SimpleNamespace(has_project=True,store=self.store,dirty=False,require_project=lambda:self.project)
        self.window._catalog_path=lambda:self.database
        self.window._error=Mock();self.window._work_kind=None
        self.window._blender_executable=self.root/'UNIT_blender.exe';self.window._blender_executable.write_bytes(b'UNIT_NOT_EXECUTABLE')
        self.window.jobs=BackgroundJobs(self.window.on_success,self.window.on_error,self.window.on_busy)
        def submit(kind,func,*,cancel):
            self.window._work_kind=kind
            self.assertTrue(self.window.jobs.submit(func,cancel=cancel))
        self.window._submit=submit
        self.addCleanup(self.cleanup_window)
        self.addCleanup(patch.stopall)
        self.load=patch('ucc.jobs.target_action.load_target_action',return_value=SimpleNamespace(
            binding_sha256=self.binding.sha256,project_sha256=digest)).start()
        patch('ucc.jobs.target_action.read_target_action_binding',return_value=self.binding).start()
        self.source_review=patch('ucc.jobs.target_action.review_target_action_source',return_value=self.review).start()
        self.origin_path=self.root/'UNIT_origin.json';self.origin_path.write_bytes(b'UNIT_PIN_REVIEWED_BY_EXPLICIT_DOUBLE')
        self.origin=ui_origin(self.origin_path)
        self.origin_reader=patch('ucc.jobs.body_sprite_provenance.review_original_motion_record',return_value=(
            self.origin,{'record_format':'UNIT_ONLY','original_script_exit_success':False})).start()

    def wait(self):
        stop=time.monotonic()+8
        while self.window.jobs.busy and time.monotonic()<stop:
            self.app.processEvents();time.sleep(.002)
        self.app.processEvents()
        self.assertFalse(self.window.jobs.busy,'Qt worker did not finish')

    def cleanup_window(self):
        self.window.jobs.cancel();self.wait()
        workflow.clear_body_sprite(self.window);self.window.deleteLater();self.app.processEvents()

    def start(self):
        workflow.start_body_sprite(self.window,self.context,self.review,self.binding.sha256)
        self.wait();self.window._error.assert_not_called()
        return self.window._body_sprite_dialog

    def review_origin(self,dialog):
        with patch('ucc.desktop.body_sprite_dialog.QFileDialog.getOpenFileName',return_value=(str(self.origin_path),'')):
            dialog.browse_origin()
        self.wait()

    def complete(self,dialog):
        self.review_origin(dialog)
        for check in dialog.checks:check.setChecked(True)
        dialog.note.setText('UNIT_ONLY explicit private per-source review')
        dialog.origin_declaration.setChecked(True);dialog.matte_consent.setChecked(True)
        dialog.destination.setText(str(self.root/'new-private-output'))
        self.assertTrue(dialog.render_button.isEnabled(),dialog.status.text()+' / '+dialog.origin_summary.text())

    def test_saved_binding_load_and_origin_review_use_real_QThread_and_no_grants(self):
        from PySide6.QtCore import QThread
        observed=[]
        def load(*args,**kwargs):
            observed.append(QThread.currentThread() is self.app.thread())
            return SimpleNamespace(binding_sha256=self.binding.sha256,project_sha256=self.context.project_sha256)
        self.load.side_effect=load
        dialog=self.start();self.review_origin(dialog)
        self.assertEqual(observed,[False])
        self.assertEqual(self.load.call_args.kwargs['database_path'],self.database)
        self.assertEqual(self.origin_reader.call_args.args[1],self.binding)
        self.assertFalse(any(check.isChecked() for check in dialog.checks))
        self.assertFalse(dialog.origin_declaration.isChecked());self.assertFalse(dialog.matte_consent.isChecked())
        self.assertFalse(dialog.render_button.isEnabled())
        self.assertIn('historical original script failed',dialog.origin_summary.text())

    def test_saved_selector_routes_exact_binding_to_sprite_flow_without_preparation(self):
        from ucc.desktop.target_action_dialog import TargetActionChoice
        from ucc.desktop.target_action_workflow import _chosen
        self.window._target_action_context=self.context
        choice=TargetActionChoice('body_sprites',self.binding.source.clip_id,self.binding.sha256,
                                  None,None,'',True)
        dialog=SimpleNamespace(choice=choice,review=self.review,deleteLater=Mock())
        with patch('ucc.desktop.body_sprite_workflow.start_body_sprite') as start:
            _chosen(self.window,dialog)
        start.assert_called_once_with(self.window,self.context,self.review,self.binding.sha256)
        self.load.assert_not_called()

    def test_render_forwards_complete_immutable_request_common_catalog_origin_and_cancel(self):
        dialog=self.start();self.complete(dialog)
        captured={}
        def export(store,**kwargs):
            captured.update(kwargs);request=kwargs['request']
            return BodySpriteExport(kwargs['destination'].path,'e'*64,request.image_count,
                request.window.target_frames,request.window.source_frames,(str(uuid4()),str(uuid4())),
                str(uuid4()),str(uuid4()),self.root/'UNIT_work')
        with patch('ucc.jobs.body_sprite_export.export_body_sprite_sample',side_effect=export),patch(
                'ucc.desktop.body_sprite_receipt.verify_body_sprite_delivery',side_effect=lambda result,*args:result) as checked,patch(
                'ucc.desktop.generation.bundled_worker_path',return_value=self.root/'UNIT_worker.py'):
            dialog.render_button.click();self.wait()
        self.window._error.assert_not_called()
        self.assertEqual(captured['database_path'],self.database)
        self.assertEqual(captured['original_author_record'],self.origin_path)
        self.assertEqual(captured['original_author_record_sha256'],self.origin.expected_sha256)
        self.assertEqual(captured['request'].target_binding,self.binding)
        self.assertEqual(captured['request'].project_snapshot_json,canonical_bytes(self.project.to_dict()))
        self.assertTrue(all(permission.reviewed for permission in captured['request'].permissions))
        self.assertIsInstance(captured['cancel'],Event)
        self.assertEqual(captured['timeout_s'],2400);checked.assert_called_once()
        self.assertIn('PRIVATE REGISTERED BODY SPRITE SAMPLE',self.window.log.toPlainText())
        self.assertIsNone(self.window._body_sprite_selection)

    def test_catalog_switch_or_dirty_project_invalidates_dialog_before_render(self):
        for change in ('catalog','dirty'):
            self.database=self.context.database;self.window.controller.dirty=False
            dialog=self.start();self.complete(dialog)
            if change=='catalog':self.database=self.root/'OTHER.db'
            else:self.window.controller.dirty=True
            with patch('ucc.jobs.body_sprite_export.export_body_sprite_sample') as export:
                workflow.refresh_body_sprite(self.window)
                self.assertIsNone(self.window._body_sprite_selection);export.assert_not_called()
                self.assertFalse(dialog.render_button.isVisible())

    def test_late_or_wrong_origin_result_cannot_restore_authority(self):
        dialog=self.start();selection=self.window._body_sprite_selection
        self.window._work_kind='body_sprite_origin';self.window._body_sprite_origin_path=self.origin_path
        workflow.finish_body_sprite(self.window,workflow.OriginReview(object(),self.origin_path,self.origin,'STALE'))
        self.assertFalse(dialog.render_button.isEnabled())
        self.assertIsNone(dialog._origin)
        self.assertIs(self.window._body_sprite_selection,selection)

    def test_queued_former_dialog_callbacks_cannot_review_or_render_another_selection(self):
        old=self.start();workflow.clear_body_sprite(self.window)
        self.assertIsNone(self.window._body_sprite_binding)
        workflow._origin(self.window,str(self.origin_path),old)
        workflow._render(self.window,old)
        current=self.start()
        workflow._origin(self.window,str(self.origin_path),old)
        workflow._render(self.window,old)
        self.origin_reader.assert_not_called()
        self.assertIs(self.window._body_sprite_dialog,current)
        current.context_token=object()
        with patch.object(current,'request') as request:
            workflow._origin(self.window,str(self.origin_path),current)
            workflow._render(self.window,current)
        request.assert_not_called();self.origin_reader.assert_not_called()

    def test_cancel_and_failure_notes_cross_actual_QThread_string_boundary(self):
        dialog=self.start();self.complete(dialog);entered=Event()
        def export(*args,**kwargs):
            entered.set()
            kwargs['cancel'].wait(5)
            error=ProjectStorageError('UNIT cancellation')
            error.add_note('UNIT foreign output retained; never removed')
            raise error
        with patch('ucc.jobs.body_sprite_export.export_body_sprite_sample',side_effect=export),patch(
                'ucc.desktop.generation.bundled_worker_path',return_value=self.root/'UNIT_worker.py'):
            dialog.render_button.click()
            self.assertTrue(entered.wait(2));self.assertTrue(self.window.jobs.cancel());self.wait()
        self.assertIn('UNIT foreign output retained',self.window._error.call_args.args[0])

    def test_changed_context_after_completed_export_reports_retained_output(self):
        dialog=self.start();self.complete(dialog)
        selection=self.window._body_sprite_selection;request=dialog.request()
        destination=dialog.destination_path()
        self.window._body_sprite_request=request;self.window._body_sprite_destination=destination
        self.window._work_kind='body_sprite_export';self.window.controller.dirty=True
        result=BodySpriteExport(destination,'f'*64,request.image_count,request.window.target_frames,
            request.window.source_frames,(str(uuid4()),str(uuid4())),str(uuid4()),str(uuid4()),self.root/'UNIT_work')
        workflow.finish_body_sprite(self.window,workflow.BodyCompleted(selection.token,result))
        self.assertIn('retained',self.window._error.call_args.args[0])
        self.assertNotIn('PRIVATE REGISTERED BODY SPRITE SAMPLE',self.window.log.toPlainText())


class BodySpriteDeliveryTests(unittest.TestCase):
    def fixture(self,*,frames=None):
        # Reuse existing explicit native doubles; these are unit filesystem bytes.
        import test_body_sprite_export
        helper=test_body_sprite_export.BodySpriteExportTests()
        helper.setUp();self.addCleanup(helper.doCleanups)
        if frames is not None:
            from ucc.core.body_sprites import BodySpriteWindow
            helper.f.request=replace(helper.f.request,window=BodySpriteWindow(1,frames))
        return helper,helper.invoke()

    def test_valid_seventeen_frame_sample_retains_both_exact_atlas_sheets(self):
        from ucc.desktop.body_sprite_receipt import verify_body_sprite_delivery
        helper,result=self.fixture(frames=17)
        self.assertEqual(result.image_count,68)
        self.assertEqual(sorted(path.name for path in result.destination.glob('sprite_sheet_*.png')),
                         ['sprite_sheet_000.png','sprite_sheet_001.png'])
        self.assertEqual(verify_body_sprite_delivery(result,helper.f.request,result.destination),result)

    def test_real_host_receipt_is_rehashed_and_foreign_or_modified_output_rejected(self):
        from ucc.desktop.body_sprite_receipt import verify_body_sprite_delivery
        helper,result=self.fixture();request=helper.f.request
        self.assertEqual(verify_body_sprite_delivery(result,request,result.destination),result)
        pixel=next(result.destination.glob('body-*.png'));original=pixel.read_bytes()
        pixel.write_bytes(original+b'UNIT_EDIT')
        with self.assertRaises(UCCError):verify_body_sprite_delivery(result,request,result.destination)
        pixel.write_bytes(original);foreign=result.destination/'UNIT_foreign.txt';foreign.write_bytes(b'USER_FILE')
        with self.assertRaises(UCCError):verify_body_sprite_delivery(result,request,result.destination)
        self.assertEqual(foreign.read_bytes(),b'USER_FILE')

    def test_coherently_rehashed_receipt_cannot_change_flags_request_worker_ids_or_clock(self):
        import json
        from ucc.desktop.body_sprite_receipt import verify_body_sprite_delivery
        helper,result=self.fixture();path=result.destination/'body_sprite_receipt.json'
        original=json.loads(path.read_bytes())
        for key,value in (('visual_quality_approved',True),('request_sha256','f'*64),
                          ('blender_executable_sha256','f'*64),
                          ('source_intake_job_ids',[result.stage_job_id,result.stage_job_id]),
                          ('full_clock',{'fps_numerator':24}),('UNREQUESTED',False)):
            raw=dict(original);raw[key]=value;payload=canonical_bytes(raw);path.write_bytes(payload)
            changed=replace(result,receipt_sha256=sha256(payload).hexdigest())
            with self.subTest(field=key),self.assertRaises(UCCError):
                verify_body_sprite_delivery(changed,helper.f.request,result.destination)

    def test_receipt_read_bytes_cannot_be_replaced_by_original_before_path_hash(self):
        import json
        from ucc.desktop.body_sprite_receipt import verify_body_sprite_delivery
        from ucc.jobs.master_preview import _digest
        helper,result=self.fixture();root=result.destination;path=root/'body_sprite_receipt.json'
        original=path.read_bytes();raw=json.loads(original)
        pixel=next(root.glob('body-*.png'));pixel.write_bytes(pixel.read_bytes()+b'UNIT_FOREIGN_EDIT')
        raw['files'][pixel.name]=_digest(pixel);path.write_bytes(canonical_bytes(raw))
        def raced_digest(current,cancel=None):
            if current==path:path.write_bytes(original)
            return _digest(current,cancel)
        with patch('ucc.desktop.body_sprite_receipt._digest',side_effect=raced_digest),self.assertRaises(UCCError):
            verify_body_sprite_delivery(result,helper.f.request,root)

    def test_recipe_read_bytes_are_bound_after_inventory_check(self):
        from ucc.desktop.body_sprite_receipt import verify_body_sprite_delivery
        from ucc.jobs.body_sprite_transactions import file_inventory
        helper,result=self.fixture();root=result.destination;path=root/'body_sprite_recipe.json'
        original=path.read_bytes()
        def raced_inventory(*args,**kwargs):
            inventory=file_inventory(*args,**kwargs)
            path.write_bytes(original+b' ')
            return inventory
        with patch('ucc.desktop.body_sprite_receipt.file_inventory',side_effect=raced_inventory),self.assertRaisesRegex(UCCError,'recipe changed'):
            verify_body_sprite_delivery(result,helper.f.request,root)


if __name__=='__main__':unittest.main()
