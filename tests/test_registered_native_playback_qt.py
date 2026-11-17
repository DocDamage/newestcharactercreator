"""NONSHIPPING registered transport/paint boundary tests; no GPU acceptance."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

from fixtures.motion_skin_contract import write_cache
from fixtures.registered_native_ui_contract import synthetic_canvas_type
from ucc.preview.motion_cache import read_motion_cache
try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.registered_native_viewer import RegisteredNativeViewer
    from ucc.desktop.motion_viewer import MotionCanvas
except ImportError as error:
    QApplication=None;QT_IMPORT_ERROR=str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional Qt unavailable')
class RegisteredNativePlaybackQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError(QT_IMPORT_ERROR)
        cls.app=QApplication.instance() or QApplication(['registered-playback-boundaries'])

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name).resolve();_,report,bindings,timeline=write_cache(root)
        self.cache=replace(read_motion_cache(root,report,bindings,timeline),source_first_frame=1)
        self.addCleanup(patch.stopall)
        patch('ucc.desktop.registered_native_viewer.MotionCanvas',synthetic_canvas_type()).start()
        self.allowed=True;self.viewer=RegisteredNativeViewer(lambda:self.allowed)
        self.addCleanup(self.viewer.deleteLater);self.addCleanup(self.viewer.clear)
        self.viewer.show_cache(self.cache)

    def test_registered_transport_uses_source_origin_and_keeps_fit_actions_disabled(self):
        self.viewer.seek(1);self.assertIn('Source frame 2',self.viewer.position.text())
        self.assertEqual(self.viewer.canvas.frame,1)
        self.assertFalse(self.viewer.try_fit.isEnabled());self.assertFalse(self.viewer.review_body.isEnabled())

    def test_static_revocation_prevents_seek_and_canvas_reuse(self):
        canvas=self.viewer.canvas;self.allowed=False
        self.viewer.seek(1)
        self.assertIsNone(self.viewer.cache);self.assertIsNone(self.viewer.clock)
        self.assertTrue(canvas.released);self.assertIsNone(canvas.cache)
        self.assertFalse(canvas._paint_guard())
        self.viewer.seek(0);self.viewer.tick();self.assertIsNone(self.viewer.canvas)

    def test_playing_revocation_stops_timer_before_queued_tick(self):
        self.viewer.toggle();canvas=self.viewer.canvas
        self.assertTrue(self.viewer.timer.isActive());before=len(canvas.submissions)
        self.allowed=False;self.viewer.tick()
        self.assertFalse(self.viewer.timer.isActive());self.assertIsNone(self.viewer.cache)
        self.viewer.tick();self.assertEqual(len(canvas.submissions),before)

    def test_authority_poll_clears_paused_cache_without_any_transport_action(self):
        self.allowed=False;self.viewer.authority_timer.timeout.emit()
        self.assertIsNone(self.viewer.cache);self.assertFalse(self.viewer.authority_timer.isActive())

    def test_actual_motion_canvas_checks_guard_before_original_renderer_draw(self):
        # Actual paintGL boundary with a renderer spy: no context or GPU claim.
        canvas=MotionCanvas(self.cache,paint_guard=lambda:False)
        self.addCleanup(canvas.deleteLater)
        renderer=SimpleNamespace(draw=Mock());canvas.renderer=renderer
        canvas.paintGL();renderer.draw.assert_not_called()
        self.assertTrue(canvas.error);canvas.renderer=None

    def test_gpu_boundary_failure_clears_registered_cache_and_emits_invalidation(self):
        invalid=[];self.viewer.invalidated.connect(lambda:invalid.append(True))
        canvas=self.viewer.canvas;canvas.failed.emit('Synthetic renderer boundary failure')
        self.assertEqual(invalid,[True]);self.assertIsNone(self.viewer.cache)
        self.assertIsNone(self.viewer.canvas);self.assertTrue(canvas.released)

    def test_clear_retains_no_cache_reference_in_late_canvas_callback(self):
        canvas=self.viewer.canvas;self.viewer.clear()
        self.assertIsNone(canvas.cache);self.assertFalse(canvas._paint_guard())
        self.viewer.timer.timeout.emit();self.assertIsNone(self.viewer.clock)

    def test_old_canvas_failure_cannot_clear_a_new_adopted_cache(self):
        old=self.viewer.canvas;self.viewer.show_cache(self.cache);current=self.viewer.canvas
        self.assertIsNot(old,current)
        old.failed.emit('Synthetic old queued renderer failure')
        self.assertIs(self.viewer.canvas,current);self.assertIs(self.viewer.cache,self.cache)
        current.failed.emit('Synthetic current renderer failure')
        self.assertIsNone(self.viewer.cache)


if __name__=='__main__':unittest.main()
