"""Qt transport behavior with isolated original synthetic cache, no GPU claim."""
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures.motion_skin_contract import write_cache
from ucc.preview.motion_cache import read_motion_cache

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QApplication,QWidget
    from ucc.desktop.motion_viewer import MotionViewer
except ImportError:
    QApplication=None


@unittest.skipIf(QApplication is None and os.environ.get("UCC_REQUIRE_QT")!="1","Optional PySide6 not installed")
class MotionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError("Motion Qt cases require PySide6")
        cls.app=QApplication.instance() or QApplication(["motion-transport-tests"])

    def setUp(self):
        class Canvas(QWidget):
            failed=Signal(str)
            def __init__(self,cache,parent):super().__init__(parent);self.frame=0;self.released=False;self.reset=False
            def release(self):self.released=True
            def reset_view(self):self.reset=True
        self.mock=patch("ucc.desktop.motion_viewer.MotionCanvas",Canvas);self.mock.start();self.addCleanup(self.mock.stop)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);folder=Path(temp.name)
        _,report,bindings,timeline=write_cache(folder);self.cache=read_motion_cache(folder,report,bindings,timeline)
        self.viewer=MotionViewer();self.addCleanup(self.viewer.clear);self.addCleanup(self.viewer.deleteLater)

    def test_real_controls_play_scrub_pause_loop_and_clear(self):
        v=self.viewer;self.assertFalse(v.play.isEnabled());v.show_cache(self.cache)
        self.assertTrue(v.play.isEnabled());self.assertEqual(v.scrub.maximum(),2)
        self.assertIn("Source frame 7",v.position.text())
        with patch("ucc.desktop.motion_viewer.time.monotonic",return_value=10.):v.play.click()
        self.assertTrue(v.timer.isActive());self.assertEqual(v.play.text(),"Pause")
        with patch("ucc.desktop.motion_viewer.time.monotonic",return_value=10.04):v.tick()
        self.assertEqual(v.canvas.frame,1)
        with patch("ucc.desktop.motion_viewer.time.monotonic",return_value=10.05):v.scrub.setValue(2)
        self.assertIn("Source frame 9",v.position.text())
        v.loop.setChecked(False);self.assertFalse(v.clock.loop)
        with patch("ucc.desktop.motion_viewer.time.monotonic",return_value=10.1):v.tick()
        self.assertFalse(v.clock.playing);self.assertFalse(v.timer.isActive())
        v.reset.click();self.assertTrue(v.canvas.reset)
        canvas=v.canvas;v.clear();self.assertTrue(canvas.released);self.assertIsNone(v.cache);self.assertFalse(v.play.isEnabled())

    def test_gpu_error_stops_transport_and_has_blender_fallback(self):
        v=self.viewer;v.show_cache(self.cache);v.play.click();v.canvas.failed.emit("Missing test context")
        self.assertFalse(v.timer.isActive());self.assertFalse(v.play.isEnabled());self.assertFalse(v.clock.playing)
        self.assertIn("private Blender",v.status.text());self.assertIn("OpenGL 3.3",v.status.text())

    def test_cached_bytes_and_timer_replaced_on_second_clip(self):
        v=self.viewer;v.show_cache(self.cache);v.play.click();canvas=v.canvas
        v.show_cache(self.cache);self.assertTrue(canvas.released);self.assertFalse(v.clock.playing);self.assertFalse(v.timer.isActive())
        self.assertEqual(v.scrub.value(),0)
