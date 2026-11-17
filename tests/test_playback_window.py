"""Pure nonshipping transport fixtures; no assets, Qt or engine proof."""
from dataclasses import FrozenInstanceError
import unittest

from ucc.preview.playback_clock import PlaybackClock
from ucc.preview.playback_window import PlaybackWindow, WindowPlaybackClock


class PlaybackWindowTests(unittest.TestCase):
    def test_default_keeps_original_complete_cache_and_source_clock(self):
        window=PlaybackWindow()
        self.assertEqual((window.first_index,window.last_index,window.frame_count,window.fps),
            (0,299,300,30))
        self.assertEqual((window.source_first_frame_selected,window.source_last_frame_selected),(2,301))
        self.assertEqual(window.sample_count,300)
        self.assertEqual(window.sample_span_s,299/30)
        self.assertEqual(window.nominal_coverage_s,10)

    def test_selected_frame_mapping_and_inclusive_span(self):
        window=PlaybackWindow(75,150)
        self.assertEqual((window.first_index,window.last_index),(74,149))
        self.assertEqual((window.source_first_frame_selected,window.source_last_frame_selected),(76,151))
        self.assertEqual(window.sample_count,76)
        self.assertEqual(window.sample_span_s,75/30)
        self.assertEqual(window.nominal_coverage_s,76/30)
        self.assertEqual(window.elapsed_at_index(74),0)
        self.assertEqual(window.elapsed_at_index(149),75/30)

    def test_bounds_exclude_booleans_float_and_reversed_or_outside_pairs(self):
        for first,last in ((True,2),(1,True),(1.,2),(1,2.),(0,1),(1,301),(150,75),(-1,2),
                (1,None),('1',2)):
            with self.subTest(first=first,last=last),self.assertRaises(ValueError):
                PlaybackWindow(first,last)

    def test_immutable_window_and_membership_are_not_clamped(self):
        window=PlaybackWindow(10,20)
        with self.assertRaises(FrozenInstanceError):window.target_first_frame=1
        for frame in (False,True,9.,-1,8,20,299):
            self.assertFalse(window.contains_index(frame))
            with self.assertRaises(ValueError):window.elapsed_at_index(frame)
        self.assertTrue(window.contains_index(9))
        self.assertTrue(window.contains_index(19))

    def test_clock_starts_at_selected_absolute_index_without_a_time_baseline(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150))
        self.assertEqual((clock.frame,clock.count,clock.fps,clock.playing,clock.loop),(74,300,30,False,False))
        clock.play(10)
        self.assertEqual(clock.advance(10.1),77)

    def test_final_sample_dwell_and_indefinite_hold_are_distinct_from_span(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(10)
        self.assertEqual(clock.advance(12.5),149)
        self.assertTrue(clock.playing)
        self.assertEqual(clock.advance(10+76/30),149)
        self.assertFalse(clock.playing)
        self.assertEqual(clock.advance(1000),149)
        self.assertFalse(clock.playing)

    def test_late_timer_uses_elapsed_source_fps_and_never_draws_outside_window(self):
        window=PlaybackWindow(75,150);clock=WindowPlaybackClock(window);clock.play(3)
        observed=[clock.advance(now) for now in (3,3.04,3.73,4.91,9,100)]
        self.assertEqual(observed[:4],[74,75,95,131])
        self.assertEqual(observed[-2:],[149,149])
        self.assertTrue(all(window.contains_index(frame) for frame in observed))
        self.assertFalse(clock.playing)

    def test_pause_resume_preserves_absolute_frame_and_stops_wall_time_progress(self):
        clock=WindowPlaybackClock(PlaybackWindow(40,90));clock.play(10)
        clock.pause(10.5);self.assertEqual(clock.frame,54)
        self.assertFalse(clock.playing)
        self.assertEqual(clock.advance(20),54)
        clock.play(30);self.assertEqual(clock.advance(30.1),57)

    def test_seek_during_play_rebases_clock_inside_window(self):
        clock=WindowPlaybackClock(PlaybackWindow(40,90));clock.play(10)
        clock.seek(60,11);self.assertTrue(clock.playing)
        self.assertEqual(clock.advance(11.1),63)
        clock.seek(89,12)
        self.assertEqual(clock.advance(12+1/30-1e-6),89)
        self.assertTrue(clock.playing)
        self.assertEqual(clock.advance(12+1/30),89)
        self.assertFalse(clock.playing)

    def test_play_from_end_returns_selected_start_not_global_zero(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.seek(149,10);clock.play(11)
        self.assertEqual(clock.frame,74)
        clock.advance(100);self.assertEqual(clock.frame,149)
        clock.play(101);self.assertEqual(clock.frame,74)

    def test_reset_stops_playback_and_goes_to_selected_start(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(1);clock.advance(2)
        clock.reset(3)
        self.assertEqual(clock.frame,74);self.assertFalse(clock.playing)
        self.assertEqual(clock.advance(99),74)

    def test_single_sample_window_is_static_and_never_starts(self):
        for frame in (1,150,300):
            window=PlaybackWindow(frame,frame);clock=WindowPlaybackClock(window)
            self.assertTrue(window.is_static);self.assertEqual(window.sample_span_s,0)
            self.assertEqual(window.nominal_coverage_s,1/30)
            clock.play(10);self.assertFalse(clock.playing)
            self.assertEqual(clock.advance(1000),frame-1)
            clock.reset(1001);self.assertEqual(clock.frame,frame-1)

    def test_seek_rejects_outside_without_mutating_play_state(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(10)
        for index in (True,74.,73,150,0,299):
            before=(clock.frame,clock.playing)
            with self.subTest(index=index),self.assertRaises(ValueError):clock.seek(index,11)
            self.assertEqual((clock.frame,clock.playing),before)
        self.assertEqual(clock.advance(10.1),77)

    def test_nonfinite_boolean_and_unrepresentable_times_reject_atomically(self):
        bad=(True,None,'10',float('nan'),float('inf'),-float('inf'),2**10000)
        for method in ('seek','play','advance','pause','reset'):
            for value in bad:
                clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(10)
                with self.subTest(method=method,kind=type(value).__name__),self.assertRaises(ValueError):
                    getattr(clock,method)(100,value) if method=='seek' else getattr(clock,method)(value)
                self.assertEqual((clock.frame,clock.playing),(74,True))

    def test_backwards_time_rejects_without_changing_position_or_origin(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(10);clock.advance(11)
        for method in ('seek','play','advance','pause','reset'):
            with self.subTest(method=method),self.assertRaises(ValueError):
                getattr(clock,method)(100,10.9) if method=='seek' else getattr(clock,method)(10.9)
            self.assertEqual((clock.frame,clock.playing),(104,True))
        self.assertEqual(clock.advance(11.1),107)

    def test_huge_finite_late_time_cannot_overflow_or_wrap(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(-1e308)
        self.assertEqual(clock.advance(1e308),149)
        self.assertFalse(clock.playing)

    def test_repeated_play_while_running_does_not_postpone_end(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150));clock.play(10)
        clock.play(11);self.assertEqual(clock.frame,104)
        clock.advance(10+76/30);self.assertEqual(clock.frame,149);self.assertFalse(clock.playing)

    def test_frame_bounds_and_loop_cannot_be_bypassed_by_public_assignment(self):
        clock=WindowPlaybackClock(PlaybackWindow(75,150))
        with self.assertRaises(AttributeError):clock.frame=0
        with self.assertRaises(AttributeError):clock.window=PlaybackWindow()
        with self.assertRaises(ValueError):clock.loop=True
        with self.assertRaises(ValueError):clock.playing=True
        clock.play(10);clock.playing=False;clock.loop=False
        self.assertFalse(clock.playing)

    def test_typed_window_required_and_legacy_clock_defaults_remain_unchanged(self):
        for value in ((75,150),{'target_first_frame':75},None):
            with self.assertRaises(ValueError):WindowPlaybackClock(value)
        legacy=PlaybackClock(300,30)
        self.assertTrue(legacy.loop);legacy.play(10);self.assertEqual(legacy.advance(20.1),3)


if __name__=='__main__':
    unittest.main()
