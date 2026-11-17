"""Real offscreen Qt transport over nonshipping analytical segment fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from fixtures.source_skeleton_contract import analytical_source_snapshot
from ucc.animations.source_skeleton import build_source_skeleton_cache

try:
    from PySide6.QtCore import QEventLoop, QTimer, Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.source_skeleton_viewer import SourceSkeletonViewer
except ImportError as error:
    QApplication = None
    QT_IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 absent')
class SourceSkeletonQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError(QT_IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['source-skeleton-test'])

    def setUp(self):
        data = analytical_source_snapshot()
        payload = json.dumps(data).encode()
        self.cache = build_source_skeleton_cache(payload,source_sha256=data['source_sha256'],
                                                 snapshot_sha256=sha256(payload).hexdigest())
        self.allowed = True
        self.viewer = SourceSkeletonViewer(lambda:self.allowed)
        self.addCleanup(self.viewer.deleteLater)
        self.addCleanup(self.viewer.close)
        self.viewer.show_cache(self.cache)

    def click_play(self, now):
        with patch('ucc.desktop.source_skeleton_viewer.time.monotonic',return_value=now):
            QTest.mouseClick(self.viewer.play,Qt.MouseButton.LeftButton)

    def tick(self, now):
        with patch('ucc.desktop.source_skeleton_viewer.time.monotonic',return_value=now):
            self.viewer.tick()

    def drain(self, operation):
        loop = QEventLoop()
        def invoke():
            try:operation()
            finally:loop.quit()
        QTimer.singleShot(0,invoke)
        loop.exec()

    def assert_cleared(self):
        self.assertIsNone(self.viewer.cache)
        self.assertIsNone(self.viewer.clock)
        self.assertIsNone(self.viewer.canvas.cache)
        self.assertEqual(self.viewer.canvas.segments,b'')
        self.assertFalse(self.viewer.timer.isActive())
        self.assertFalse(self.viewer.guard_timer.isActive())
        for control in (self.viewer.play,self.viewer.start,self.viewer.slider):
            self.assertFalse(control.isEnabled())

    def test_initial_complete_source_labels_and_exact_packed_canvas_segments(self):
        self.assertIs(self.viewer.cache,self.cache)
        self.assertEqual((self.viewer.slider.minimum(),self.viewer.slider.maximum()),(0,3))
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(0))
        self.assertIn('Source frame 11 of 11-14',self.viewer.status.text())
        self.assertIn('Sample span 0.100000 s; nominal coverage 0.133333 s',self.viewer.status.text())
        self.assertFalse(self.viewer.clock.loop)
        self.assertTrue(self.viewer.guard_timer.isActive())

    def test_canvas_real_paint_path_accepts_analytical_line_bytes_without_gpu(self):
        self.viewer.show()
        self.app.processEvents()
        with patch.object(self.viewer.canvas,'paintEvent',wraps=self.viewer.canvas.paintEvent) as paint:
            self.viewer.canvas.repaint()
            self.app.processEvents()
            self.assertGreater(paint.call_count,0)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(0))

    def test_revocation_before_actual_paint_blocks_endpoint_lines_and_clears_authority(self):
        self.viewer.show()
        self.app.processEvents()
        signal = QSignalSpy(self.viewer.invalidated)
        lines = []
        class ObservedPainter(QPainter):
            def drawLine(self,*args):
                lines.append(args)
                return super().drawLine(*args)
        self.allowed = False
        with patch('ucc.desktop.source_skeleton_viewer.QPainter',ObservedPainter):
            self.viewer.canvas.repaint()
            self.app.processEvents()
        self.assertEqual(lines,[])
        self.assertEqual(signal.count(),1)
        self.assert_cleared()

    def test_authorized_paint_submits_two_real_views_of_every_segment(self):
        self.viewer.show()
        self.app.processEvents()
        lines = []
        class ObservedPainter(QPainter):
            def drawLine(self,*args):
                lines.append(args)
                return super().drawLine(*args)
        with patch('ucc.desktop.source_skeleton_viewer.QPainter',ObservedPainter):
            self.viewer.canvas.repaint()
        self.assertEqual(len(lines),2*self.cache.bone_count)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(0))

    def test_play_pause_resume_preserves_source_frame_and_hands_through_each_sample(self):
        self.click_play(10.)
        self.assertTrue(self.viewer.clock.playing)
        self.assertEqual(self.viewer.play.text(),'Pause')
        self.tick(10.+1/30)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(1))
        self.click_play(10.+1/30)
        self.assertFalse(self.viewer.clock.playing)
        self.assertFalse(self.viewer.timer.isActive())
        self.tick(19.)
        self.assertEqual(self.viewer.clock.frame,1)
        self.click_play(20.)
        self.tick(20.+1/30)
        self.assertEqual(self.viewer.clock.frame,2)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(2))
        self.assertIn('Source frame 13',self.viewer.status.text())

    def test_final_sample_dwell_then_indefinite_hold_and_replay_from_source_start(self):
        self.click_play(10.)
        self.tick(10.+3/30)
        self.assertEqual(self.viewer.clock.frame,3)
        self.assertTrue(self.viewer.clock.playing)
        self.tick(10.+4/30)
        self.assertFalse(self.viewer.clock.playing)
        self.assertFalse(self.viewer.timer.isActive())
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(3))
        self.tick(1000.)
        self.assertEqual(self.viewer.clock.frame,3)
        self.click_play(2000.)
        self.assertEqual(self.viewer.clock.frame,0)
        self.assertTrue(self.viewer.clock.playing)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(0))

    def test_late_timer_clamps_to_final_frame_without_wrap(self):
        self.click_play(10.)
        with patch.object(self.viewer.canvas,'present',wraps=self.viewer.canvas.present) as present:
            self.tick(100.)
            self.assertEqual(present.call_args.args,(self.cache,3))
        self.assertEqual(self.viewer.clock.frame,3)
        self.assertFalse(self.viewer.clock.playing)

    def test_normal_slider_and_start_button_keep_absolute_source_mapping(self):
        with patch('ucc.desktop.source_skeleton_viewer.time.monotonic',return_value=10.):
            self.viewer.slider.setValue(2)
        self.assertEqual(self.viewer.clock.frame,2)
        self.assertIn('Source frame 13',self.viewer.status.text())
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(2))
        with patch('ucc.desktop.source_skeleton_viewer.time.monotonic',return_value=11.):
            QTest.mouseClick(self.viewer.start,Qt.MouseButton.LeftButton)
        self.assertEqual(self.viewer.clock.frame,0)
        self.assertFalse(self.viewer.clock.playing)

    def test_seek_while_playing_rebases_timer_within_complete_source(self):
        self.click_play(10.)
        with patch('ucc.desktop.source_skeleton_viewer.time.monotonic',return_value=20.):
            self.viewer.slider.setValue(2)
        self.assertTrue(self.viewer.clock.playing)
        self.assertEqual(self.viewer.canvas.segments,self.cache.frame(2))
        self.tick(20.+1/30)
        self.assertEqual(self.viewer.clock.frame,3)
        self.assertTrue(self.viewer.clock.playing)
        self.tick(20.+2/30)
        self.assertEqual(self.viewer.clock.frame,3)
        self.assertFalse(self.viewer.clock.playing)

    def test_invalid_seek_does_not_replace_previous_valid_segments(self):
        previous = self.viewer.canvas.segments
        for index in (-1,4,True,1.5):
            with self.subTest(index=index),self.assertRaises(ValueError):self.viewer.seek(index)
        self.assertEqual(self.viewer.canvas.segments,previous)
        self.assertEqual(self.viewer.clock.frame,0)

    def test_clear_stops_both_timers_and_queued_ticks_cannot_revive_cache(self):
        self.click_play(10.)
        self.viewer.clear()
        self.drain(lambda:(self.viewer.tick(),self.viewer.seek(2),self.viewer.toggle_play()))
        self.assert_cleared()
        self.assertEqual(self.viewer.status.text(),'No source skeleton loaded')

    def test_denied_guard_clears_paused_preview_and_emits_once(self):
        signal = QSignalSpy(self.viewer.invalidated)
        self.allowed = False
        self.assertFalse(self.viewer._authorized())
        self.assert_cleared()
        self.assertEqual(signal.count(),1)
        self.viewer.tick()
        self.assertEqual(signal.count(),1)

    def test_guard_revocation_during_play_never_submits_another_frame(self):
        self.click_play(10.)
        self.allowed = False
        with patch.object(self.viewer.canvas,'present',wraps=self.viewer.canvas.present) as present:
            self.tick(10.+1/30)
            present.assert_not_called()
        self.assert_cleared()

    def test_guard_exception_fails_closed(self):
        def changed():raise RuntimeError('Synthetic authority changed')
        self.viewer.guard = changed
        self.viewer.seek(2)
        self.assert_cleared()

    def test_adoption_with_denied_guard_never_displays_new_cache(self):
        self.allowed = False
        with patch.object(self.viewer.canvas,'present',wraps=self.viewer.canvas.present) as present:
            self.viewer.show_cache(self.cache)
            present.assert_not_called()
        self.assert_cleared()

    def test_real_close_clears_authority_before_queued_callback_drain(self):
        self.viewer.show()
        self.click_play(10.)
        signal = QSignalSpy(self.viewer.invalidated)
        self.viewer.close()
        self.assertEqual(signal.count(),1)
        self.drain(self.viewer.tick)
        self.assertFalse(self.viewer.isVisible())
        self.assert_cleared()

    def test_cache_replacement_discards_old_clock_and_keeps_new_origin(self):
        self.click_play(10.)
        old_clock = self.viewer.clock
        data = analytical_source_snapshot(first=1,count=180)
        payload = json.dumps(data).encode()
        newer = build_source_skeleton_cache(payload,source_sha256=data['source_sha256'],
                                            snapshot_sha256=sha256(payload).hexdigest())
        self.viewer.show_cache(newer)
        self.drain(self.viewer.tick)
        self.assertIsNot(self.viewer.clock,old_clock)
        self.assertFalse(self.viewer.clock.playing)
        self.assertEqual(self.viewer.clock.frame,0)
        self.assertEqual(self.viewer.slider.maximum(),179)
        self.assertIn('Source frame 1 of 1-180',self.viewer.status.text())
        self.assertEqual(self.viewer.canvas.segments,newer.frame(0))


if __name__=='__main__':unittest.main()
