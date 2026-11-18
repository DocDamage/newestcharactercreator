"""Synthetic clock controls for full-cache idle interpolation."""

import math
import unittest

from ucc.preview.idle_loop_clock import IdleLoopClock, LoopSample


class IdleLoopClockTests(unittest.TestCase):
    def test_wrap_uses_one_sample_interval_and_no_extra_frame(self):
        clock = IdleLoopClock()
        self.assertEqual(clock.sample, LoopSample(0, 1, 0.))
        clock.play(0.)
        clock.advance(299.5/30)
        self.assertEqual((clock.sample.left_index, clock.sample.right_index), (299, 0))
        self.assertAlmostEqual(clock.sample.alpha, .5)
        clock.advance(10.-1e-11)
        self.assertEqual(clock.frame, 299)
        clock.advance(10.)
        self.assertEqual(clock.sample, LoopSample(0, 1, 0.))
        self.assertTrue(clock.playing)

    def test_pause_holds_fraction_then_resumes_same_interval(self):
        clock = IdleLoopClock()
        clock.seek(299, 10.)
        clock.play(10.)
        clock.pause(10.+.5/30)
        hold = clock.sample
        self.assertEqual((hold.left_index, hold.right_index), (299, 0))
        self.assertAlmostEqual(hold.alpha, .5)
        clock.advance(20.)
        self.assertEqual(clock.sample, hold)
        clock.play(21.)
        clock.advance(21.+.25/30)
        self.assertEqual(clock.frame, 299)
        self.assertAlmostEqual(clock.sample.alpha, .75)
        clock.advance(21.+1./30)
        self.assertEqual(clock.frame, 0)
        self.assertAlmostEqual(clock.sample.alpha, .5)

    def test_seek_and_reset_use_exact_frames(self):
        clock = IdleLoopClock()
        clock.play(1.)
        clock.seek(150, 2.)
        self.assertEqual(clock.sample, LoopSample(150, 151, 0.))
        self.assertTrue(clock.playing)
        clock.reset(3.)
        self.assertEqual(clock.sample, LoopSample(0, 1, 0.))
        self.assertFalse(clock.playing)

    def test_late_callbacks_and_extreme_finite_times_stay_bounded(self):
        clock = IdleLoopClock()
        clock.play(0.)
        clock.advance(10000+4.25/30)
        self.assertEqual(clock.frame, 4)
        self.assertAlmostEqual(clock.sample.alpha, .25, places=8)
        clock = IdleLoopClock()
        clock.play(-1e308)
        clock.advance(1e308)
        self.assertTrue(0 <= clock.frame < 300)
        self.assertTrue(0 <= clock.sample.alpha < 1)

    def test_bad_times_indices_and_sample_pairs_fail_without_advancing(self):
        clock = IdleLoopClock()
        clock.play(100.)
        for now in (True, math.nan, math.inf, -math.inf, 99., 10**1000):
            with self.subTest(now=type(now).__name__), self.assertRaises(ValueError):
                clock.advance(now)
        for index in (True, 300, -1):
            with self.assertRaises(ValueError):
                clock.seek(index, 101.)
        for args in ((299, 1, .5), (0, True, .5), (False, 1, .5), (0, 1, True),
                     (0, 1, math.nan), (0, 1, math.inf), (0, 1, 1.)):
            with self.assertRaises(ValueError):
                LoopSample(*args)
        self.assertEqual(clock.frame, 0)
        self.assertTrue(clock.playing)
