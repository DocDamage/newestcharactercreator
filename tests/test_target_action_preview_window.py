"""NONSHIPPING synthetic-cache Qt transport tests; no GPU/app/animation proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.motion_skin_contract import write_cache
from ucc.preview.motion_cache import read_motion_cache
from ucc.core.errors import ProjectStorageError, ValidationError
try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
    from ucc.desktop.target_action_preview import TargetActionViewer, _TargetActionDock
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class TargetPreviewWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Review-window tests require Qt')
        cls.app = QApplication.instance() or QApplication(['target-window-tests'])

    def setUp(self):
        class Canvas(QWidget):
            failed = Signal(str)
            def __init__(self, cache, parent):
                super().__init__(parent)
                self.cache = cache; self.frame = 0; self.submissions = []
                self.released = False; self.camera_resets = 0
                self.loop_sample = self.loop_guard = None
                self.paint_blocked = False
            def update(self):
                if not self.paint_blocked and (self.loop_guard is None or self.loop_guard()):
                    self.submissions.append(self.frame)
            def set_idle_loop_sample(self, sample, guard):
                self.loop_sample = sample
                self.loop_guard = guard
            def clear_idle_loop_sample(self, *, block_paint=False):
                self.loop_sample = self.loop_guard = None
                self.paint_blocked = block_paint
            def release(self):
                self.released = True; self.cache = None
            def reset_view(self):
                self.camera_resets += 1
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        _, report, bindings, timeline = write_cache(root)
        cache = read_motion_cache(root, report, bindings, timeline)
        self.cache = replace(cache, chunks=(cache.chunks[0],)*300,
                             hips=(cache.hips[0],)*300, fps=30., source_first_frame=2)
        self.original = {p.name:sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
        self.addCleanup(patch.stopall)
        patch('ucc.desktop.motion_viewer.MotionCanvas', Canvas).start()
        self.allow = True; self.guards = []
        def guard():
            self.guards.append(True)
            return self.allow
        self.viewer = TargetActionViewer(guard)
        self.addCleanup(self.viewer.deleteLater)
        self.addCleanup(self.viewer.clear)
        self.viewer.show_cache(self.cache)

    def apply(self, first, last):
        self.viewer.target_start.setValue(first); self.viewer.target_end.setValue(last)
        self.viewer.apply_window.click()

    def test_narrow_window_retains_original_cache_absolute_indices_and_labels(self):
        self.apply(75, 150)
        viewer = self.viewer
        self.assertIs(viewer.cache, self.cache)
        self.assertEqual((viewer.clock.count,viewer.clock.fps),(300,30))
        self.assertEqual((viewer.scrub.minimum(),viewer.scrub.maximum()),(74,149))
        self.assertEqual((viewer.clock.frame,viewer.canvas.frame),(74,74))
        self.assertIn('Source frame 76',viewer.position.text())
        self.assertIn('target 75 / 300',viewer.position.text())
        self.assertIn('window elapsed 0.000 s',viewer.position.text())
        self.assertIn('76 samples; sample span 2.500000 s',viewer.window_status.text())
        self.assertIn('coverage 2.533333 s',viewer.window_status.text())
        self.assertFalse(viewer.clock.playing)
        self.assertFalse(viewer.loop.isEnabled())
        after={p.name:sha256(p.read_bytes()).hexdigest() for p in Path(self.temp.name).iterdir() if p.is_file()}
        self.assertEqual(after,self.original)

    def test_invalid_pair_preserves_accepted_clock_bounds_and_play_state_atomically(self):
        self.apply(75,150)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.toggle()
        clock=self.viewer.clock;window=self.viewer.review_window;frame=self.viewer.canvas.frame
        self.apply(200,100)
        self.assertIs(self.viewer.clock,clock)
        self.assertIs(self.viewer.review_window,window)
        self.assertTrue(clock.playing)
        self.assertTrue(self.viewer.timer.isActive())
        self.assertEqual((self.viewer.scrub.minimum(),self.viewer.scrub.maximum()),(74,149))
        self.assertEqual(self.viewer.canvas.frame,frame)
        self.assertIn('not applied',self.viewer.window_status.text())

    def test_end_sample_final_dwell_hold_and_play_restart_selected_start(self):
        self.apply(75,77)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.toggle()
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10+2/30):self.viewer.tick()
        self.assertEqual(self.viewer.canvas.frame,76)
        self.assertTrue(self.viewer.clock.playing)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10+3/30):self.viewer.tick()
        self.assertFalse(self.viewer.clock.playing)
        self.assertFalse(self.viewer.timer.isActive())
        self.assertEqual(self.viewer.canvas.frame,76)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=11):self.viewer.toggle()
        self.assertEqual(self.viewer.canvas.frame,74)

    def test_pause_resume_and_seek_stay_within_absolute_window(self):
        self.apply(75,150)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.toggle()
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10.5):self.viewer.toggle()
        self.assertEqual(self.viewer.clock.frame,89)
        self.assertFalse(self.viewer.clock.playing)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=11):self.viewer.seek(120)
        self.assertEqual(self.viewer.canvas.frame,120)
        frame=self.viewer.clock.frame
        self.viewer.seek(0);self.viewer.seek(150);self.viewer.seek(True)
        self.assertEqual(self.viewer.clock.frame,frame)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=12):self.viewer.toggle()
        self.assertTrue(self.viewer.clock.playing)

    def test_apply_while_playing_and_queued_old_ticks_submit_only_new_window(self):
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.toggle()
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=18):self.viewer.tick()
        self.assertEqual(self.viewer.canvas.frame,240)
        canvas=self.viewer.canvas;canvas.submissions.clear()
        QTimer.singleShot(0,self.viewer.tick)
        self.apply(75,150)
        self.app.processEvents()
        self.assertFalse(self.viewer.clock.playing)
        self.assertFalse(self.viewer.timer.isActive())
        self.assertTrue(canvas.submissions)
        self.assertTrue(all(74<=frame<=149 for frame in canvas.submissions))
        self.assertEqual(canvas.frame,74)

    def test_reviewed_idle_loops_only_after_opt_in(self):
        viewer = self.viewer
        viewer.loop.setChecked(True)
        self.assertFalse(viewer.loop.isChecked())
        viewer.install_idle_loop(lambda: True)
        self.assertTrue(viewer.loop.isEnabled())
        self.assertFalse(viewer.loop.isChecked())
        with patch('ucc.desktop.motion_viewer.time.monotonic', return_value=10):
            viewer.seek(299)
            viewer.loop.setChecked(True)
            viewer.toggle()
        with patch('ucc.desktop.motion_viewer.time.monotonic', return_value=10+1/60):
            viewer.tick()
        sample = viewer.canvas.loop_sample
        self.assertEqual((sample.left_index, sample.right_index), (299, 0))
        self.assertAlmostEqual(sample.alpha, .5)
        self.assertIs(viewer.cache, self.cache)
        self.assertTrue(viewer.clock.playing)
        viewer.loop.setChecked(False)
        self.assertIsNone(viewer.canvas.loop_sample)
        self.assertFalse(viewer.clock.playing)
        self.assertEqual(viewer.clock.frame, 299)

    def test_applying_review_window_removes_idle_authority_and_blend(self):
        viewer = self.viewer
        viewer.install_idle_loop(lambda: True)
        viewer.loop.setChecked(True)
        self.assertIsNotNone(viewer.canvas.loop_sample)
        self.apply(25, 30)
        self.assertIsNone(viewer.canvas.loop_sample)
        self.assertFalse(viewer.loop.isEnabled())
        self.assertFalse(viewer.loop.isChecked())
        self.assertEqual(viewer.canvas.frame, 24)

    def test_visual_decision_action_requires_live_full_loop_authority(self):
        viewer = self.viewer
        recorded = []
        self.assertTrue(viewer.record_idle_decision.isHidden())
        self.assertFalse(viewer.record_idle_decision.isEnabled())
        current = True
        viewer.install_idle_loop(lambda: current, record_decision=lambda: recorded.append(True))
        self.assertFalse(viewer.record_idle_decision.isHidden())
        viewer.record_idle_decision.click()
        self.assertEqual(recorded, [True])
        current = False
        viewer.record_idle_decision.click()
        self.assertEqual(recorded, [True])
        self.apply(25, 30)
        self.assertTrue(viewer.record_idle_decision.isHidden())

    def test_visual_decision_dialog_requires_the_reviewers_own_explicit_input(self):
        from ucc.desktop.authored_idle_visual_workflow import IdleVisualDecisionDialog

        dialog = IdleVisualDecisionDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertIsNone(dialog.decision.currentData())
        self.assertFalse(dialog.attest.isChecked())
        self.assertFalse(dialog.save.isEnabled())
        dialog.decision.setCurrentIndex(dialog.decision.findData('rework'))
        dialog.reviewer.setText('Nonshipping test reviewer')
        dialog.note.setPlainText('Nonshipping test notes about the transition.')
        dialog.accept()
        self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted)
        dialog.attest.setChecked(True)
        self.assertTrue(dialog.save.isEnabled())
        dialog.save.click()
        value = dialog.declaration()
        self.assertEqual(value.decision, 'rework')
        self.assertTrue(value.personally_reviewed)

    def test_visual_decision_workflow_supplies_exact_proof_and_fences_picker_drift(self):
        from ucc.desktop.authored_idle_visual_workflow import (
            IdleVisualDecisionDialog, KIND, start_visual_decision,
        )

        root = Path(self.temp.name).resolve()
        context = SimpleNamespace(store=SimpleNamespace(root=root/'source'), database=root/'catalog.sqlite3')
        proof = root/'idle-proof.json'
        identity = SimpleNamespace(selection=object())
        admitted = SimpleNamespace(review_identity=identity)
        errors = []
        window = SimpleNamespace(jobs=SimpleNamespace(busy=False), _error=errors.append)

        class TestDialog(IdleVisualDecisionDialog):
            def __init__(self, _parent):
                super().__init__()

            def exec(self):
                self.decision.setCurrentIndex(self.decision.findData('approve'))
                self.reviewer.setText('Nonshipping test reviewer')
                self.note.setPlainText('Nonshipping review input.')
                self.attest.setChecked(True)
                self.accept()
                return self.result()

        with patch('ucc.desktop.authored_idle_visual_workflow.IdleVisualDecisionDialog', TestDialog), patch(
                'ucc.desktop.authored_idle_visual_workflow.QFileDialog.getExistingDirectory',
                return_value=str(root)), patch('ucc.desktop.authored_idle_visual_workflow.QInputDialog.getText',
                return_value=('review', True)), patch('ucc.desktop.target_action_workflow._submit') as submit, patch(
                'ucc.jobs.authored_idle_visual_review.publish_authored_idle_visual_decision') as publisher:
            current = iter((True, False))
            start_visual_decision(window, context, proof, admitted, lambda: next(current))
            submit.assert_not_called()
            self.assertIn('changed', errors.pop())
            start_visual_decision(window, context, proof, admitted, lambda: True)
            owner, kind, operation = submit.call_args.args
            self.assertIs(owner, window)
            self.assertEqual(kind, KIND)
            operation(None, lambda _: None)
            self.assertIs(publisher.call_args.args[0], context.store)
            self.assertIs(publisher.call_args.kwargs['expected_identity'], identity)
            self.assertEqual(publisher.call_args.kwargs['proof_file'], proof)
            self.assertEqual(publisher.call_args.kwargs['decision'].decision, 'approve')
            self.assertEqual(publisher.call_args.kwargs['destination'].path, root/'review')

    def test_revoked_loop_suppresses_queued_paint_and_releases_cache(self):
        viewer = self.viewer
        permitted = True
        viewer.install_idle_loop(lambda: permitted)
        viewer.loop.setChecked(True)
        canvas = viewer.canvas
        canvas.submissions.clear()
        permitted = False
        canvas.update()
        viewer.tick()
        self.assertEqual(canvas.submissions, [])
        self.assertTrue(canvas.paint_blocked)
        self.assertTrue(canvas.released)
        self.assertIsNone(viewer.cache)

    def test_watched_file_notification_revokes_even_when_stat_guard_has_not_changed(self):
        viewer = self.viewer
        proof = Path(self.temp.name).resolve()/'loop-proof.json'
        proof.write_text('{}', encoding='utf8')
        viewer.install_idle_loop(lambda: True, (proof,))
        viewer.loop.setChecked(True)
        canvas = viewer.canvas
        canvas.submissions.clear()
        viewer._idle_watcher.fileChanged.emit(str(proof))
        canvas.update()
        self.assertIsNone(viewer.cache)
        self.assertTrue(canvas.released)
        self.assertEqual(canvas.submissions, [])

    def test_main_window_registers_idle_review_in_busy_and_cancel_controls(self):
        from ucc.animations.catalog import AnimationCatalog
        from ucc.desktop.authored_idle_loop_workflow import KIND
        from ucc.desktop.window import MainWindow

        catalog_path = Path(self.temp.name).resolve()/'catalog.db'
        with AnimationCatalog(catalog_path):
            pass
        window = MainWindow(catalog_path=catalog_path)
        self.addCleanup(window.deleteLater)
        window._work_kind = KIND
        window._busy_changed(True)
        self.assertTrue(window.cancel_generation_action.isEnabled())
        self.assertIn('Reviewing the authored idle proof', window.statusBar().currentMessage())
        window._busy_changed(False)
        self.assertFalse(window.cancel_generation_action.isEnabled())

    def test_single_frame_disables_play_and_guarded_go_start_still_works(self):
        self.apply(150,150)
        self.assertEqual((self.viewer.scrub.minimum(),self.viewer.scrub.maximum()),(149,149))
        self.assertFalse(self.viewer.play.isEnabled())
        self.assertTrue(self.viewer.apply_window.isEnabled())
        self.assertTrue(self.viewer.go_start.isEnabled())
        self.assertIn('sample span 0.000000 s',self.viewer.window_status.text())
        self.assertIn('coverage 0.033333 s',self.viewer.window_status.text())
        before=len(self.guards)
        self.viewer.go_start.click();self.viewer.toggle()
        self.assertEqual(len(self.guards),before+2)
        self.assertFalse(self.viewer.clock.playing)
        self.assertEqual(self.viewer.canvas.frame,149)

    def test_go_start_pauses_but_reset_view_only_changes_camera(self):
        self.apply(75,150)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.seek(120)
        self.viewer.reset.click()
        self.assertEqual(self.viewer.clock.frame,120)
        self.assertEqual(self.viewer.canvas.camera_resets,1)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=11):self.viewer.toggle()
        with patch('ucc.desktop.target_action_preview.time.monotonic',return_value=12):self.viewer.go_start.click()
        self.assertEqual(self.viewer.canvas.frame,74)
        self.assertFalse(self.viewer.clock.playing)
        self.assertFalse(self.viewer.guard_timer.isActive())

    def test_guard_denial_on_paused_static_apply_go_play_seek_clears_authority(self):
        for operation in ('apply_review_window','go_to_window_start','toggle','seek'):
            self.allow=True;self.viewer.show_cache(self.cache);self.apply(150,150)
            canvas=self.viewer.canvas;canvas.submissions.clear();self.allow=False
            if operation=='seek':self.viewer.seek(149)
            else:getattr(self.viewer,operation)()
            self.assertEqual(canvas.submissions,[])
            self.assertTrue(canvas.released)
            self.assertIsNone(self.viewer.clock)
            self.assertIsNone(self.viewer.cache)
            self.assertIsNone(self.viewer.review_window)
            self.assertFalse(self.viewer.apply_window.isEnabled())

    def test_clear_fail_and_reopen_reset_full_range_and_stop_queued_ticks(self):
        self.apply(75,150);canvas=self.viewer.canvas;canvas.submissions.clear()
        QTimer.singleShot(0,self.viewer.tick)
        self.viewer._failed('NONSHIPPING synthetic GPU failure')
        self.app.processEvents()
        self.assertEqual(canvas.submissions,[])
        self.assertIsNone(self.viewer.clock);self.assertIsNone(self.viewer.cache)
        self.assertIsNone(self.viewer.review_window)
        self.assertFalse(self.viewer.timer.isActive());self.assertFalse(self.viewer.guard_timer.isActive())
        self.viewer.show_cache(self.cache)
        self.assertEqual((self.viewer.target_start.value(),self.viewer.target_end.value()),(1,300))
        self.assertEqual((self.viewer.scrub.minimum(),self.viewer.scrub.maximum()),(0,299))
        self.assertEqual(self.viewer.canvas.frame,0)

    def test_close_during_playback_drains_ticks_without_submitting(self):
        self.apply(75,150)
        with patch('ucc.desktop.motion_viewer.time.monotonic',return_value=10):self.viewer.toggle()
        canvas=self.viewer.canvas;canvas.submissions.clear()
        QTimer.singleShot(0,self.viewer.tick)
        self.viewer.close();self.app.processEvents()
        self.assertEqual(canvas.submissions,[])
        self.assertTrue(canvas.released)
        self.assertIsNone(self.viewer.clock);self.assertIsNone(self.viewer.review_window)

    def test_dock_and_owner_close_clear_root_prepared_cache_and_watches(self):
        for close_owner in (False,True):
            self.viewer.show_cache(self.cache)
            owner=QMainWindow();self.addCleanup(owner.deleteLater)
            dock=_TargetActionDock('NONSHIPPING preview owner',owner);dock.setWidget(self.viewer)
            owner._target_action_viewer=self.viewer;owner._target_action_dock=dock
            owner._target_action_result=SimpleNamespace(cache=self.cache)
            owner._target_action_identities={'nonshipping':'identity'}
            class Watch:
                def blockSignals(self,_):pass
                def files(self):return ['synthetic-proof']
                def directories(self):return []
                def removePaths(self,paths):self.removed=paths
            owner._target_action_watcher=Watch()
            if close_owner:owner.close()
            else:dock.close()
            self.assertIsNone(owner._target_action_result)
            self.assertEqual(owner._target_action_identities,{})
            self.assertEqual(owner._target_action_watcher.removed,['synthetic-proof'])
            self.assertIsNone(self.viewer.cache)
            dock.setWidget(QWidget());self.viewer.setParent(None)

    def test_wrong_cache_clock_cannot_replace_current_accepted_cache(self):
        old=self.viewer.cache
        for changed in ({'fps':24},{'source_first_frame':1},{'chunks':self.cache.chunks[:-1]}):
            with self.assertRaises(ValidationError):self.viewer.show_cache(replace(self.cache,**changed))
            self.assertIs(self.viewer.cache,old)

    def test_paused_static_apply_and_go_start_use_original_catalog_guard_and_drop_root_cache(self):
        from test_target_action_desktop import TargetActionDesktopTests
        for operation in ('apply_review_window','go_to_window_start'):
            boundary=TargetActionDesktopTests('test_policy_recheck_on_play_seek_and_live_guard_stops_revoked_preview')
            boundary.setUp();self.addCleanup(boundary.doCleanups)
            viewer=boundary.publish()
            viewer.target_start.setValue(150);viewer.target_end.setValue(150);viewer.apply_window.click()
            self.assertFalse(viewer.clock.playing)
            self.assertFalse(viewer.play.isEnabled())
            before=boundary.catalog.call_count
            boundary.catalog.side_effect=ProjectStorageError('NONSHIPPING selected WAL policy revoked')
            getattr(viewer,operation)()
            self.assertGreater(boundary.catalog.call_count,before)
            self.assertIsNone(boundary.window._target_action_result)
            self.assertIsNone(viewer.cache);self.assertIsNone(viewer.clock)
            self.assertIsNone(viewer.review_window)
            self.assertFalse(viewer.apply_window.isEnabled());self.assertFalse(viewer.go_start.isEnabled())
            self.assertTrue(boundary.result.binding_path.is_file())

    def test_dirty_selection_blocks_window_apply_via_existing_context_guard(self):
        from test_target_action_desktop import TargetActionDesktopTests
        boundary=TargetActionDesktopTests('test_dirty_detached_or_other_project_context_clears_transport')
        boundary.setUp();self.addCleanup(boundary.doCleanups)
        viewer=boundary.publish()
        viewer.target_start.setValue(75);viewer.target_end.setValue(150)
        boundary.window.controller.dirty=True
        viewer.apply_window.click()
        self.assertIsNone(boundary.window._target_action_result)
        self.assertIsNone(viewer.cache);self.assertIsNone(viewer.review_window)
        self.assertFalse(viewer.apply_window.isEnabled())


if __name__=='__main__':unittest.main()
