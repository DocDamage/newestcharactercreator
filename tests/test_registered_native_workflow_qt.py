"""Normal desktop registered-source routes with NONSHIPPING native boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,PropertyMock

from fixtures.registered_native_ui_contract import synthetic_environment,synthetic_canvas_type
from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError, ValidationError
from ucc.jobs.native_preview_profiles import catalog_preview_profile_path
from ucc.library.provenance import AssetPolicyError
try:
    from PySide6.QtWidgets import QApplication,QMessageBox,QTableWidgetItem
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
    from ucc.desktop import registered_native_workflow as flow
    from ucc.desktop import registered_native_binding as binding
except ImportError as error:
    QApplication=None; QT_IMPORT_ERROR=str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional Qt unavailable')
class RegisteredNativeWorkflowQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError(QT_IMPORT_ERROR)
        cls.app=QApplication.instance() or QApplication(['registered-native-boundaries'])

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.controller=DesktopController()
        self.f=synthetic_environment(self.root,self.controller)
        self.window=MainWindow(self.controller);self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window._clear_preview);self.addCleanup(patch.stopall)
        self.window._blender_executable=self.root/'synthetic-not-blender.exe'
        self.window._blender_executable.write_bytes(b'NOT_EXECUTABLE')
        table=self.window.animations.catalog;table.setRowCount(1)
        table.setItem(0,0,QTableWidgetItem('source'));table.setCurrentCell(0,0)
        self.queued=[];self.errors=[]
        patch.object(self.window,'_catalog_path',return_value=self.f.database).start()
        patch.object(self.window,'_submit',side_effect=self.submit).start()
        patch.object(self.window,'_error',side_effect=self.errors.append).start()
        patch.object(flow,'bundled_worker_path',return_value=self.root/'unused-worker.py').start()
        self.native=patch.object(flow,'preview_native_body',side_effect=lambda *a,**kw:
            self.f.preview(kw['source_authority'],self.f.proof())).start()
        self.cache_prepare=patch.object(flow,'prepare_native_playback',side_effect=lambda store,preview,**kw:
            self.f.playback(preview.source_authority,self.f.proof(include_cache=True))).start()
        patch('ucc.desktop.registered_native_viewer.MotionCanvas',synthetic_canvas_type()).start()

    def submit(self,kind,operation,**options):
        self.window._work_kind=kind;self.queued.append((operation,options))

    def start(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            self.window.registered_native_action.trigger()

    def finish(self):
        operation,options=self.queued[-1];result=operation();self.window._job_success(result)
        return result,options

    def body(self):self.start();return self.finish()

    def playback(self):
        self.body();self.window.animations.load_native_motion.click();return self.finish()

    def select_inline_source(self):
        pane = self.window.animations
        pane.display_catalog([
            {'asset_id': 'source', 'format': 'fbx', 'clips': ['source#clip-0000'],
             'status': 'METADATA_EXTRACTED'},
            {'asset_id': 'other_source', 'format': 'fbx', 'clips': [], 'status': 'INDEXED'},
        ])
        self.window.tabs.setCurrentWidget(pane)
        pane.catalog.setCurrentCell(0, 0)
        self.assertTrue(pane.preview_clip.isEnabled())
        return pane

    def test_inline_search_excludes_hidden_selection_without_selecting_another_source(self):
        pane = self.select_inline_source()
        pane.search.setText('SOURCE measured')
        self.assertTrue(pane.catalog.isRowHidden(0))
        self.assertIsNone(pane.workspace.selected_asset_id())
        self.assertFalse(pane.preview_clip.isEnabled())
        pane.search.setText('OTHER source')
        self.assertTrue(pane.catalog.isRowHidden(0))
        self.assertFalse(pane.catalog.isRowHidden(1))
        self.assertIsNone(pane.workspace.selected_asset_id())
        pane.catalog.setCurrentCell(1, 0)
        self.assertEqual(pane.catalog_selection_label.text(), 'other_source')
        self.assertFalse(pane.preview_clip.isEnabled())
        pane.search.clear()
        pane.catalog.setCurrentCell(0, 0)
        self.assertTrue(pane.preview_clip.isEnabled())
        self.window.rename('NONSHIPPING unsaved edit')
        self.assertFalse(pane.preview_clip.isEnabled())

    def test_inline_one_click_starts_guarded_playback_in_workspace_and_filter_revokes_it(self):
        pane = self.select_inline_source()
        with patch.object(flow, 'AnimationCatalog', side_effect=AssertionError('GUI SQL forbidden')), \
             patch.object(QMessageBox, 'question', side_effect=AssertionError('Unexpected second confirmation')):
            pane.preview_clip.click()
        self.assertEqual(len(self.queued), 1)
        self.native.assert_not_called()
        self.cache_prepare.assert_not_called()
        self.finish()
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.queued), 1)
        self.native.assert_called_once()
        self.cache_prepare.assert_called_once()
        native_authority = self.native.call_args.kwargs['source_authority']
        self.assertIs(self.cache_prepare.call_args.args[1].source_authority, native_authority)
        self.assertIs(self.native.call_args.kwargs['render_private_frames'], False)
        self.assertIs(self.native.call_args.kwargs['progress'], self.cache_prepare.call_args.kwargs['progress'])
        self.assertTrue(binding.guard_registered_native(self.window))
        viewer = self.window.motion_viewer
        dock = self.window.motion_dock
        self.assertTrue(pane.workspace.isAncestorOf(dock))
        self.assertIs(dock.widget(), viewer)
        self.assertTrue(viewer.clock.playing)
        self.assertTrue(viewer.timer.isActive())
        canvas = viewer.canvas
        pane.search.setText('other_source')
        self.assertIsNone(self.window._registered_native_binding)
        self.assertIsNone(viewer.cache)
        self.assertFalse(viewer.timer.isActive())
        self.assertTrue(canvas.released)
        self.assertFalse(pane.preview_clip.isEnabled())

    def test_inline_click_does_not_replace_revoked_catalog_permission(self):
        pane = self.select_inline_source()
        with AnimationCatalog(self.f.database) as writer:
            revoked = self.f.policy.to_dict()
            revoked['local_preview_allowed'] = False
            writer.db.execute('UPDATE asset_sources SET license_json=?', (json.dumps(revoked),))
            writer.db.commit()
        pane.preview_clip.click()
        operation, _options = self.queued[-1]
        with self.assertRaises(AssetPolicyError):
            operation()
        self.native.assert_not_called()
        self.cache_prepare.assert_not_called()
        self.assertIsNone(self.window._native_review)
        self.assertIsNone(self.window.motion_viewer)

    def test_inline_replays_current_clip_without_a_second_blender_job(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        self.finish()
        viewer = self.window.motion_viewer
        viewer.toggle()
        pane.catalog.setCurrentCell(0, 1)
        pane.preview_clip.click()
        self.assertEqual(len(self.queued), 1)
        self.assertIs(self.window.motion_viewer, viewer)
        self.assertTrue(viewer.clock.playing)

    def test_inline_reuses_protected_session_playback_after_selecting_away_and_back(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        result, _options = self.finish()
        viewer = self.window.motion_viewer
        pane.catalog.setCurrentCell(1, 0)
        self.assertIsNone(viewer.cache)
        self.assertIsNone(self.window._registered_native_binding)
        pane.catalog.setCurrentCell(0, 0)
        pane.preview_clip.click()
        self.assertEqual(len(self.queued), 2)
        self.assertIsNone(self.window._native_playback)
        self.finish()
        self.native.assert_called_once()
        self.cache_prepare.assert_called_once()
        self.assertIs(self.window._native_playback, result.value)
        self.assertTrue(binding.guard_registered_native(self.window, result.value.source_authority))
        self.assertTrue(viewer.clock.playing)

    def local_profile_path(self):
        snapshot = sha256((self.f.folder / 'source_snapshot.json').read_bytes()).hexdigest()
        return catalog_preview_profile_path(self.f.database, self.f.source_sha, snapshot,
                                            Path(self.f.project.master_blend).stem)

    def test_inline_selects_the_local_body_map_that_matches_all_three_input_pins(self):
        pane = self.select_inline_source()
        local = self.local_profile_path()
        local.parent.mkdir()
        local.with_name('a' * 64 + '.json').write_text('{}')
        local.write_text('{}')
        pane.preview_clip.click()
        self.finish()
        self.assertEqual(self.native.call_args.kwargs['mapping_profile'], local)

    def test_inline_does_not_resume_default_session_cache_after_a_local_map_appears(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        self.finish()
        pane.catalog.setCurrentCell(1, 0)
        local = self.local_profile_path()
        local.parent.mkdir()
        local.write_text('{}')
        pane.catalog.setCurrentCell(0, 0)
        pane.preview_clip.click()
        retry, _ = self.queued[-1]
        with self.assertRaisesRegex(ValidationError, 'Saved preview inputs changed'):
            retry()
        self.native.assert_called_once()
        pane.preview_clip.click()
        self.finish()
        self.assertEqual(self.native.call_args.kwargs['mapping_profile'], local)

    def test_inline_session_playback_rejects_changed_source_with_restored_stat_identity(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        result, _options = self.finish()
        pane.catalog.setCurrentCell(1, 0)
        stamp = self.f.source.stat()
        source = self.f.source.read_bytes()
        self.f.source.write_bytes(b'X' + source[1:])
        os.utime(self.f.source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertTrue(result.value.source_authority.identities_current())
        pane.catalog.setCurrentCell(0, 0)
        pane.preview_clip.click()
        self.assertEqual(len(self.queued), 2)
        self.assertIsNone(self.window._native_playback)
        self.assertIsNone(self.window._registered_native_binding)
        operation, _options = self.queued[-1]
        with self.assertRaises(UCCError):
            operation()
        self.native.assert_called_once()
        self.cache_prepare.assert_called_once()

    def test_inline_progress_is_queued_and_ignores_obsolete_or_cancelled_requests(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        previous = self.window._registered_native_pending
        reporter = self.window._registered_native_progress
        reporter.changed.emit(previous.token, 'BUILD_CACHE')
        self.assertIn('Checking source permissions', flow.registered_native_progress_text(self.window))
        with patch.object(type(self.window.jobs), 'busy', new_callable=PropertyMock, return_value=True):
            self.app.processEvents()
        self.assertIn('Preparing frames for playback', pane.preview_status.text())
        self.assertRegex(pane.preview_status.text(), r'\d+:\d{2} elapsed')

        pane.catalog.setCurrentCell(1, 0)
        pane.catalog.setCurrentCell(0, 0)
        pane.preview_clip.click()
        current = self.window._registered_native_pending
        with patch.object(type(self.window.jobs), 'busy', new_callable=PropertyMock, return_value=True):
            self.window._refresh_animation_preview()
            reporter.changed.emit(previous.token, 'VERIFY_SURFACE')
            self.app.processEvents()
        self.assertIn('Checking source permissions', pane.preview_status.text())
        current.cancel.set()
        reporter.changed.emit(current.token, 'CHECK_CACHE')
        self.app.processEvents()
        self.assertEqual(flow.registered_native_progress_text(self.window), 'Cancelling preview…')
        self.assertEqual(reporter.stage, 'SOURCE_AUTHORITY')

    def test_inline_deformation_failure_reports_in_workspace_without_modal(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        self.window.jobs._cancel = self.queued[-1][1]['cancel']
        self.addCleanup(setattr, self.window.jobs, '_cancel', None)
        self.window._job_error('WorkerFailure: MotionQualityError: Extreme local edge strain')
        self.assertEqual(self.errors, [])
        self.assertIn('deformation limits', pane.preview_status.text())
        self.assertIsNone(self.window._native_playback)

    def test_inline_worker_completion_cannot_restore_playback_after_selection_change(self):
        pane = self.select_inline_source()
        pane.preview_clip.click()
        operation, options = self.queued[-1]
        result = operation()
        pane.catalog.setCurrentCell(1, 0)
        self.assertTrue(options['cancel'].is_set())
        self.window._job_success(result)
        self.assertIsNone(self.window.motion_viewer)
        self.assertIsNone(self.window._native_playback)
        self.assertIsNone(self.window._registered_native_binding)

    def test_default_no_and_gui_never_reads_catalog_or_prepares_native(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No) as consent, \
                patch.object(flow,'AnimationCatalog',side_effect=AssertionError('GUI SQL forbidden')):
            self.window.registered_native_action.trigger()
        self.assertEqual(consent.call_args.args[-1],QMessageBox.StandardButton.No)
        self.assertFalse(self.queued);self.native.assert_not_called()
        with patch.object(flow,'AnimationCatalog',side_effect=AssertionError('GUI SQL forbidden')):
            self.start()
        self.assertEqual(len(self.queued),1);self.native.assert_not_called()

    def test_healthy_real_binder_adopts_original_receipts_without_gui_heavy_guard(self):
        self.start();operation,_=self.queued[-1];result=operation()
        self.assertEqual(self.native.call_args.kwargs['timeout_s'],900)
        self.assertTrue(self.native.call_args.kwargs.get('render_private_frames', True))
        value=result.value
        bad=lambda **kw:(_ for _ in ()).throw(AssertionError('GUI heavy guard forbidden'))
        value=replace(value,source_authority=replace(value.source_authority,guard=bad),
                      proof_receipt=replace(value.proof_receipt,guard=bad))
        with patch.object(flow,'AnimationCatalog',side_effect=AssertionError('GUI SQL forbidden')):
            self.window._job_success(replace(result,value=value))
            self.assertTrue(binding.guard_registered_native(self.window))
        self.assertEqual(self.errors,[]);self.assertIs(self.window._native_review,value)
        self.assertTrue(self.window.animations.load_native_motion.isEnabled())

    def test_superseded_token_does_not_clear_new_pending_request(self):
        self.start();old_operation,old_options=self.queued[-1];old=old_operation()
        self.start();new=self.window._registered_native_pending
        self.assertTrue(old_options['cancel'].is_set());self.window._job_success(old)
        self.assertIs(self.window._registered_native_pending,new)
        self.assertIsNone(self.window._native_review)
        self.finish();self.assertIsNotNone(self.window._native_review)

    def test_late_opaque_completion_cannot_fall_into_current_legacy_job_kind(self):
        self.start();operation,_=self.queued[-1];old=operation()
        binding.clear_registered_native(self.window)
        self.window._work_kind='native_body';self.window.log.setPlainText('Unrelated current task')
        with patch('ucc.desktop.native_body.native_result_text',side_effect=AssertionError('Legacy publication forbidden')):
            self.window._job_success(old)
        self.assertEqual(self.window.log.toPlainText(),'Unrelated current task')
        self.assertIsNone(self.window._native_review)

    def test_late_cancel_after_worker_return_blocks_adoption(self):
        self.start();operation,options=self.queued[-1];result=operation()
        options['cancel'].set();self.window._job_success(result)
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._registered_native_binding)

    def test_project_owner_or_selection_change_rejects_pending_result(self):
        self.start();operation,_=self.queued[-1];result=operation()
        self.window.animations.catalog.item(0,0).setText('other')
        self.window._job_success(result);self.assertIsNone(self.window._native_review)
        self.window.animations.catalog.item(0,0).setText('source')
        self.start();operation,_=self.queued[-1];result=operation()
        self.controller.open(self.root/'p')
        self.window._job_success(result);self.assertIsNone(self.window._native_review)

    def test_cache_request_hides_active_authority_and_normal_result_uses_registered_viewer(self):
        self.body();preview=self.window._native_review
        self.window.animations.load_native_motion.click()
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._registered_native_binding)
        self.assertIs(self.window._registered_native_pending.preview,preview)
        self.finish();viewer=self.window.motion_viewer
        self.assertEqual(self.cache_prepare.call_args.kwargs['timeout_s'],1800)
        self.assertIsNotNone(viewer.cache);self.assertEqual(viewer.cache.source_first_frame,1)
        self.assertIn('REGISTERED PRIVATE NATIVE SKIN PLAYBACK',self.window.log.toPlainText())
        self.assertFalse(viewer.try_fit.isEnabled());self.assertFalse(viewer.review_body.isEnabled())

    def test_busy_cache_trigger_preserves_original_pending_job_and_cancel_event(self):
        self.body();self.window.animations.load_native_motion.click()
        pending=self.window._registered_native_pending;count=len(self.queued)
        with patch.object(type(self.window.jobs),'busy',new_callable=PropertyMock,return_value=True):
            flow.start_registered_native_playback(self.window)
        self.assertIs(self.window._registered_native_pending,pending)
        self.assertFalse(pending.cancel.is_set());self.assertEqual(len(self.queued),count)

    def test_loaded_cache_retrigger_preserves_existing_transport_without_new_job(self):
        self.playback();cache=self.window.motion_viewer.cache;loaded=self.window._native_playback
        binding_before=self.window._registered_native_binding;count=len(self.queued)
        self.assertFalse(self.window.animations.load_native_motion.isEnabled())
        flow.start_registered_native_playback(self.window)
        self.assertIs(self.window.motion_viewer.cache,cache);self.assertIs(self.window._native_playback,loaded)
        self.assertIs(self.window._registered_native_binding,binding_before)
        self.assertIsNone(self.window._registered_native_pending);self.assertEqual(len(self.queued),count)

    def test_missing_catalog_namespace_poll_clears_live_cache_and_authority(self):
        self.playback();viewer=self.window.motion_viewer
        Path(str(self.f.database)+'-journal').write_bytes(b'NONSHIPPING namespace fault')
        self.window._registered_native_timer.timeout.emit()
        self.assertIsNone(viewer.cache);self.assertIsNone(self.window._native_review)
        self.assertIsNone(self.window._native_playback);self.assertIsNone(self.window._registered_native_binding)

    def test_dock_close_while_playing_releases_cached_bytes_and_registered_authority(self):
        self.playback();viewer=self.window.motion_viewer;viewer.toggle();canvas=viewer.canvas
        self.window.motion_dock.close()
        self.assertIsNone(viewer.cache);self.assertIsNone(viewer.clock);self.assertTrue(canvas.released)
        self.assertIsNone(canvas.cache);self.assertIsNone(self.window._registered_native_binding)
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._native_playback)
        self.assertFalse(viewer.timer.isActive());viewer.tick();self.assertIsNone(viewer.cache)

    def test_main_window_close_clears_registered_playback_and_queued_callbacks(self):
        self.playback();viewer=self.window.motion_viewer;viewer.toggle()
        self.window.close();viewer.tick()
        self.assertIsNone(viewer.cache);self.assertIsNone(self.window._registered_native_binding)
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._native_playback)

    def test_late_cache_cancel_does_not_restore_hidden_preview(self):
        self.body();self.window.animations.load_native_motion.click()
        operation,options=self.queued[-1];result=operation();options['cancel'].set()
        self.window._job_success(result)
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._native_playback)
        self.assertIsNone(self.window._registered_native_binding)

    def test_old_binding_callbacks_cannot_cancel_new_pending_or_adopted_cache(self):
        self.body();old_watcher=self.window._registered_native_watcher
        old_timer=self.window._registered_native_timer
        self.window.animations.load_native_motion.click();pending=self.window._registered_native_pending
        old_timer.timeout.emit();old_watcher.directoryChanged.emit(str(self.root))
        self.assertIs(self.window._registered_native_pending,pending)
        self.finish();adopted=self.window._registered_native_binding
        old_timer.timeout.emit();old_watcher.directoryChanged.emit(str(self.root))
        self.assertIs(self.window._registered_native_binding,adopted)
        self.assertIsNotNone(self.window.motion_viewer.cache)

    def test_cache_receipt_cannot_drop_previous_original_proof_authority(self):
        self.body();previous=self.window._native_review.proof_receipt
        target=self.f.folder/'target_timeline.json'
        self.assertIn(target,previous.watched_identities)
        def lost_proof(store,preview,**kwargs):
            value=self.f.playback(preview.source_authority,self.f.proof(include_cache=True))
            ids={p:s for p,s in value.proof_receipt.watched_identities.items() if p!=target}
            watches=tuple(p for p in value.proof_receipt.watch_paths if p!=target)
            return replace(value,proof_receipt=replace(value.proof_receipt,
                watched_identities=ids,watch_paths=watches))
        self.cache_prepare.side_effect=lost_proof
        self.window.animations.load_native_motion.click();operation,_=self.queued[-1]
        with self.assertRaisesRegex(ValidationError,'previous|original|cover'):
            operation()

    def test_committed_owned_wal_policy_revocation_clears_playing_cache(self):
        self.playback();viewer=self.window.motion_viewer;viewer.toggle()
        self.assertTrue(viewer.timer.isActive())
        with AnimationCatalog(self.f.database) as writer:
            writer.db.execute('PRAGMA journal_mode=WAL');writer.db.execute('PRAGMA wal_autocheckpoint=0')
            policy=self.f.policy.to_dict();policy['local_preview_allowed']=False
            writer.db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(policy),));writer.db.commit()
            self.window._registered_native_watcher.directoryChanged.emit(str(self.root))
            self.assertIsNone(viewer.cache);self.assertFalse(viewer.timer.isActive())
            self.assertFalse(self.window.animations.load_native_motion.isEnabled())

    def test_original_proof_mutation_between_return_and_adoption_is_not_rebaselined(self):
        self.start();operation,_=self.queued[-1];result=operation()
        (self.f.folder/'target_timeline.json').write_text('changed original proof')
        self.window._job_success(result)
        self.assertIsNone(self.window._native_review);self.assertIsNone(self.window._registered_native_binding)

    def test_root_close_cancels_pending_and_late_completion_does_not_restore_authority(self):
        self.start();operation,options=self.queued[-1];result=operation()
        self.window.close();self.assertTrue(options['cancel'].is_set())
        self.window._job_success(result);self.assertIsNone(self.window._native_review)

    def test_manual_source_route_is_not_silently_registered(self):
        from ucc.desktop.native_body import start_native_playback
        self.window._native_review=self.f.preview(None)
        self.window.animations.local_preview_review.setChecked(False)
        with patch.object(flow,'start_registered_native_playback') as registered:
            start_native_playback(self.window)
        registered.assert_not_called();self.assertFalse(self.queued)

    def test_old_manual_watcher_callbacks_cannot_clear_new_registered_route(self):
        from ucc.desktop.native_playback import publish_playback
        self.window.animations.selected.setText(str(self.f.source))
        self.window._native_review=self.f.preview(None)
        with patch('ucc.desktop.motion_viewer.MotionCanvas',synthetic_canvas_type()):
            publish_playback(self.window,self.f.playback(None))
        old=self.window._motion_watcher
        self.start();pending=self.window._registered_native_pending
        old.blockSignals(False)
        old.fileChanged.emit(str(self.f.source));old.directoryChanged.emit(str(self.root))
        self.assertIs(self.window._registered_native_pending,pending)
        self.finish();adopted=self.window._registered_native_binding
        old.fileChanged.emit(str(self.f.source));old.directoryChanged.emit(str(self.root))
        self.assertIs(self.window._registered_native_binding,adopted)
        self.assertIsNotNone(self.window._native_review)

    def test_retired_viewer_and_dock_callbacks_cannot_clear_replacement(self):
        self.playback();retired=self.window.motion_viewer;retired_dock=self.window.motion_dock
        # Retain retired QObject handles to exercise already-queued callbacks.
        retired.clear();self.window.removeDockWidget(retired_dock);retired_dock.setParent(None)
        self.addCleanup(retired_dock.deleteLater)
        self.window.motion_viewer=None;self.window.motion_dock=None
        flow._publish_registered_playback(self.window,self.window._native_playback)
        current=self.window.motion_viewer;adopted=self.window._registered_native_binding
        self.assertIsNot(current,retired)
        retired.invalidated.emit();retired_dock.close()
        self.assertIs(self.window.motion_viewer,current);self.assertIsNotNone(current.cache)
        self.assertIs(self.window._registered_native_binding,adopted)


if __name__=='__main__':unittest.main()
