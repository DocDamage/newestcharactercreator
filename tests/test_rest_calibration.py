"""Pure-math orientation tests. Not evidence of real user animation/Blender."""
from __future__ import annotations

import math
import unittest

from blender_bridge.rest_calibration import (
    RestCalibrationError, Y_UP_TO_Z_UP, Z_UP_IDENTITY,
    axis_rotation, bvh_ordered_rotation, calibrate_rest_frames,
    calibrated_local_delta, determinant, multiply, norm, transform,
    transpose, validate_rotation, project_near_rotation,
)


def max_difference(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(3) for j in range(3))


class RestSpaceMathTests(unittest.TestCase):
    def test_explicit_y_up_conversion_and_proper_rotation(self):
        src = ((0, 1, 0), (1, 0, 0))
        target = ((0, 0, 1), (1, 0, 0))
        result = calibrate_rest_frames(src, target, "Y_UP_TO_Z_UP")
        self.assertLess(max_difference(result.source_axes_to_target, Y_UP_TO_Z_UP), 1e-10)
        self.assertLess(result.max_rest_residual_degrees, 1e-7)
        self.assertEqual(result.landmark_pair, (0, 1))
        self.assertAlmostEqual(determinant(result.source_axes_to_target), 1.0, places=10)
        self.assertFalse(result.bone_roll_independently_verified)

    def test_known_ninety_degree_twist_from_anatomical_landmarks(self):
        # This is not an Euler-angle copy: the shared rest frame is rotated
        # 90 degrees around Z, independently of the destination bone rest roll.
        source = ((0, 1, 0), (0, 0, 1))
        twist = axis_rotation("Zrotation", 90)
        target = tuple(transform(twist, v) for v in source)
        result = calibrate_rest_frames(source, target, "Z_UP_IDENTITY")
        self.assertLess(max_difference(result.source_axes_to_target, twist), 1e-9)
        for initial in source:
            self.assertAlmostEqual(norm(transform(result.source_axes_to_target, initial)),
                                   norm(initial), places=9)

        destination_rest = axis_rotation("Xrotation", 35)
        s0 = Z_UP_IDENTITY
        s1 = axis_rotation("Xrotation", 27)
        got = calibrated_local_delta(
            s0, s1, result.source_axes_to_target, destination_rest,
        )
        conversion = multiply(transpose(destination_rest), twist)
        want = multiply(multiply(conversion, s1), transpose(conversion))
        self.assertLess(max_difference(got, want), 1e-9)
        self.assertGreater(max_difference(got, s1), 1e-3)
        validate_rotation(got)

    def test_actual_ordered_euler_quaternion_conjugation_not_angle_subtraction(self):
        # Nonzero initial XYZ rotations + noncommuting channels must NOT be
        # simplified to Euler angle differences.
        start = bvh_ordered_rotation(
            ("Xrotation", "Yrotation", "Zrotation"), (15.0, 24.0, 33.0)
        )
        current = bvh_ordered_rotation(
            ("Xrotation", "Yrotation", "Zrotation"), (28.0, 16.0, 43.0)
        )
        q = calibrated_local_delta(start, current, Z_UP_IDENTITY, Z_UP_IDENTITY)
        expected = multiply(transpose(start), current)
        naive = bvh_ordered_rotation(
            ("Xrotation", "Yrotation", "Zrotation"), (13.0, -8.0, 10.0)
        )
        self.assertLess(max_difference(q, expected), 1e-10)
        self.assertGreater(max_difference(q, naive), 1e-3)
        validate_rotation(q)
        neutral = calibrated_local_delta(start, start, Z_UP_IDENTITY, Z_UP_IDENTITY)
        self.assertLess(max_difference(neutral, Z_UP_IDENTITY), 1e-10)

    def test_reject_collinear_or_one_direction_bone_roll_guess(self):
        with self.assertRaisesRegex(RestCalibrationError, "At least two"):
            calibrate_rest_frames(((0, 1, 0),), ((0, 0, 1),), "Y_UP_TO_Z_UP")
        with self.assertRaisesRegex(RestCalibrationError, "non-collinear"):
            calibrate_rest_frames(
                ((0, 1, 0), (0, 0.9999, 0.01)),
                ((0, 0, 1), (0, -0.01, 0.9999)),
                "Y_UP_TO_Z_UP",
            )

    def test_reject_mismatched_anatomy_and_mirrored_third_landmark(self):
        with self.assertRaisesRegex(RestCalibrationError, "five degrees"):
            calibrate_rest_frames(
                ((1, 0, 0), (0, 1, 0)),
                ((1, 0, 0), (0.8660254, 0.5, 0)),
                "Z_UP_IDENTITY",
            )
        with self.assertRaisesRegex(RestCalibrationError, "five degrees"):
            calibrate_rest_frames(
                ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
                "Z_UP_IDENTITY",
            )

    def test_bounded_projection_accepts_small_mpfb_rest_noise_only(self):
        slightly_scaled = ((1.000014475, 0, 0),
                           (0, 1.0, 0), (0, 0, 1.0))
        with self.assertRaises(RestCalibrationError):
            validate_rotation(slightly_scaled)
        projected, raw_det, correction = project_near_rotation(slightly_scaled)
        validate_rotation(projected)
        self.assertAlmostEqual(raw_det, 1.000014475, places=8)
        self.assertLess(correction, 0.00002)
        self.assertLess(max_difference(projected, Z_UP_IDENTITY), 1e-9)
        for improper in (
            ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
            ((1.02, 0, 0), (0, 1, 0), (0, 0, 1)),
            ((1, .01, 0), (0, 1, 0), (0, 0, 1)),
        ):
            with self.subTest(matrix=improper), self.assertRaises(RestCalibrationError):
                project_near_rotation(improper)

    def test_reject_scaled_reflected_invalid_rotation_and_unknown_axis(self):
        with self.assertRaisesRegex(RestCalibrationError, "reflected"):
            validate_rotation(((1, 0, 0), (0, 1, 0), (0, 0, -1)))
        with self.assertRaisesRegex(RestCalibrationError, "scaled"):
            validate_rotation(((2, 0, 0), (0, 1, 0), (0, 0, 1)))
        with self.assertRaisesRegex(RestCalibrationError, "explicitly"):
            calibrate_rest_frames(
                ((1, 0, 0), (0, 1, 0)),
                ((1, 0, 0), (0, 1, 0)), "AUTO",
            )
        with self.assertRaisesRegex(RestCalibrationError, "XYZ"):
            bvh_ordered_rotation(
                ("Zrotation", "Xrotation", "Yrotation"), (0, 2, 0),
            )


if __name__ == "__main__":
    unittest.main()
