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

    def test_surface_navigation_pauses_wraps_preserves_focus_and_clears(self):
        from dataclasses import replace
        from ucc.preview.surface_review import SurfaceReview
        review=SurfaceReview('CHECKED','',((1,2),(),(3,4)),((1,0),(0,0),(0,2)),('a'*64,)*3)
        v=self.viewer;v.show_cache(replace(self.cache,surface_review=review))
        self.assertTrue(v.next_flagged.isEnabled());self.assertIn('2 flagged frames',v.surface_status.text())
        self.assertTrue(v.try_fit.isEnabled());v.set_fit_busy(True);self.assertFalse(v.try_fit.isEnabled())
        v.set_fit_busy(False);self.assertTrue(v.try_fit.isEnabled())
        v.play.click();v.next_flagged.click()
        self.assertFalse(v.clock.playing);self.assertEqual(v.clock.frame,2);self.assertTrue(v.focus.isChecked())
        v.highlight.setChecked(False)
        self.assertFalse(v.canvas.highlight_intersections);self.assertTrue(v.canvas.focus_intersections)
        v.scrub.setValue(1);v.max_pairs.click();self.assertEqual(v.clock.frame,2)
        v.next_flagged.click();self.assertEqual(v.clock.frame,0)
        v.reset.click();self.assertFalse(v.focus.isChecked())
        v.clear();self.assertFalse(v.next_flagged.isEnabled());self.assertFalse(v.highlight.isEnabled())

    def test_unavailable_surface_review_cannot_enable_success_or_navigation(self):
        from dataclasses import replace
        from ucc.preview.surface_review import SurfaceReview
        review=SurfaceReview('UNAVAILABLE','WEIGHTED_REGIONS_UNAVAILABLE',((),)*3,((0,0),)*3,('a'*64,)*3)
        v=self.viewer;v.show_cache(replace(self.cache,surface_review=review))
        self.assertFalse(v.next_flagged.isEnabled());self.assertFalse(v.highlight.isEnabled());self.assertFalse(v.max_pairs.isEnabled())
        self.assertIn('unavailable',v.surface_status.text())

    def test_comparison_switch_preserves_frame_clock_and_camera_and_clears_both(self):
        from dataclasses import replace
        from ucc.preview.surface_review import SurfaceReview
        original=replace(self.cache,surface_review=SurfaceReview('CHECKED','',((1,),(),()),((1,0),(0,0),(0,0)),('a'*64,)*3))
        fitted=replace(self.cache,surface_review=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,('a'*64,)*3))
        v=self.viewer;v.show_comparison(original,fitted);v.seek(1);clock=v.clock
        self.assertFalse(v.try_fit.isEnabled())
        v.canvas.yaw=1.;v.canvas.pitch=.4;v.canvas.zoom=2.;v.canvas.pan=(.1,.2)
        v.play.click();v.variant.setCurrentIndex(1)
        self.assertIs(v.cache,fitted);self.assertIs(v.canvas.cache,fitted);self.assertIs(v.clock,clock)
        self.assertEqual(v.clock.frame,1);self.assertTrue(v.clock.playing);self.assertTrue(v.timer.isActive())
        self.assertEqual((v.canvas.yaw,v.canvas.pitch,v.canvas.zoom,v.canvas.pan),(1.,.4,2.,(.1,.2)))
        self.assertFalse(v.next_flagged.isEnabled());self.assertIn('0 flagged frames',v.surface_status.text())
        v.variant.setCurrentIndex(0);self.assertIs(v.cache,original);self.assertTrue(v.next_flagged.isEnabled())
        v.clear();self.assertIsNone(v.comparison);self.assertTrue(v.variant.isHidden());self.assertFalse(v.timer.isActive())

    def test_comparison_rejects_incompatible_complete_clips_without_replacing_current(self):
        from dataclasses import replace
        from ucc.core.errors import ValidationError
        v=self.viewer;v.show_cache(self.cache)
        for changes in ({'fps':60.},{'source_first_frame':1},{'hips':((0,0,2),)*3},{'vertex_count':121},{'world_matrix':(0.,)*16}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):v.show_comparison(self.cache,replace(self.cache,**changes))
            self.assertIs(v.cache,self.cache);self.assertIsNone(v.comparison)

    def test_body_and_arm_inspections_switch_on_same_clock_frame_and_camera(self):
        from dataclasses import replace
        from ucc.preview.surface_review import SurfaceReview
        from ucc.preview.body_contacts import POLICY
        arm=SurfaceReview('CHECKED','',((1,),(),()),((1,0),(0,0),(0,0)),('a'*64,)*3)
        body=SurfaceReview('CHECKED','',((),(3,),()),((0,0),(2,0),(0,0)),('a'*64,)*3,POLICY)
        fitted_body=replace(body,pairs=((0,0),(1,0),(0,0)))
        base=replace(self.cache,surface_review=arm);v=self.viewer;v.show_comparison(base,base);v.seek(1)
        clock=v.clock;v.canvas.yaw=1.;v.canvas.zoom=2.;v.show_body_contacts(body,fitted_body)
        self.assertIs(v.clock,clock);self.assertEqual(v.clock.frame,1);self.assertEqual((v.canvas.yaw,v.canvas.zoom),(1.,2.))
        self.assertEqual(v.cache.surface_review.policy,POLICY);self.assertIn('Hand/body',v.surface_status.text())
        self.assertFalse(v.try_fit.isEnabled());self.assertFalse(v.review_body.isEnabled())
        v.variant.setCurrentIndex(1);self.assertEqual(v.cache.surface_review.pairs[1],(1,0))
        v.inspection.setCurrentIndex(0);self.assertIs(v.cache.surface_review,arm);self.assertIn('opposite-arm',v.surface_status.text())
        v.clear();self.assertIsNone(v._body_caches);self.assertTrue(v.inspection.isHidden())

    def test_body_review_cannot_revive_failed_gpu_and_rejects_wrong_topology(self):
        from dataclasses import replace
        from ucc.preview.surface_review import SurfaceReview
        from ucc.preview.body_contacts import POLICY
        from ucc.core.errors import ValidationError
        arm=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,('a'*64,)*3)
        body=replace(arm,policy=POLICY);v=self.viewer;v.show_cache(replace(self.cache,surface_review=arm))
        with self.assertRaises(ValidationError):v.show_body_contacts(replace(body,triangle_hashes=('b'*64,)*3))
        v.canvas.failed.emit('test GPU failure');v.show_body_contacts(body);v.set_fit_busy(False)
        self.assertFalse(v.play.isEnabled());self.assertFalse(v.inspection.isEnabled());self.assertFalse(v.review_body.isEnabled())
