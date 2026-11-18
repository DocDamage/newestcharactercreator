"""Synthetic binary samples exercise the independent corrected evidence checks."""

from math import cos, radians, sin
from struct import pack, pack_into
import unittest
from unittest.mock import Mock, patch

from ucc.core.errors import ValidationError
from ucc.export import unity_corrected_animation_evidence as evidence


class UnityCorrectedAnimationEvidenceTests(unittest.TestCase):
    def setUp(self):
        profile = patch.multiple(evidence, SOURCE_FRAMES=2, SOURCE_VERTICES=3)
        profile.start()
        self.addCleanup(profile.stop)
        # Blender source order 0,1,2. Unity's imported seam repeats source 2.
        self.mapping = [2, 0, 1, 2]
        self.positions = pack('<18f', 1, 2, 3, 0, 0, 0, 4, 5, 6, 7, 8, 9, 0, 0, 0, 0, 0, 0)
        self.normals = pack('<18f', 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1)
        self.native = pack(
            '<48f',
            -4, 6, -5, 0, 1, 0, -1, 3, -2, -1, 0, 0, 0, 0, 0, 0, 0, -1, -4, 6, -5, 0, 1, 0,
            0, 0, 0, 0, 1, 0, -7, 9, -8, -1, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0,
        )
        self.check = Mock()

    def compare(self, **changes):
        data = dict(source_positions=self.positions, source_normals=self.normals,
                    native_samples=self.native, native_to_source=self.mapping, check=self.check)
        return evidence.compare_unity_corrected_animation(**(data | changes))

    def last_native(self, component, *values):
        data = bytearray(self.native)
        pack_into(f'<{len(values)}f', data, len(data) - 24 + component*4, *values)
        return bytes(data)

    def test_reflected_xyz_and_normals_match_every_remapped_seam_vertex(self):
        observed = self.compare()
        self.assertEqual((observed.frames, observed.source_vertices, observed.native_vertices,
                          observed.compared_vertices), (2, 3, 4, 8))
        self.assertEqual(observed.maximum_position_error_m, 0)
        self.assertEqual(observed.maximum_normal_angle_deg, 0)
        self.assertEqual(self.check.call_count, 3)

    def test_residuals_inside_limits_pass_and_late_seam_position_over_10um_fails(self):
        position = self.last_native(0, 9e-6)
        result = self.compare(native_samples=position)
        self.assertAlmostEqual(result.maximum_position_error_m, 9e-6)
        with self.assertRaisesRegex(ValidationError, 'position.*frame 2, vertex 3'):
            self.compare(native_samples=self.last_native(0, 1.01e-5))

    def test_corrected_normal_angle_uses_pointwise_0_1_degree_limit(self):
        angle = radians(0.099)
        result = self.compare(native_samples=self.last_native(3, sin(angle), cos(angle), 0))
        self.assertAlmostEqual(result.maximum_normal_angle_deg, 0.099, places=5)
        angle = radians(0.101)
        with self.assertRaisesRegex(ValidationError, 'normal differs.*frame 2, vertex 3'):
            self.compare(native_samples=self.last_native(3, sin(angle), cos(angle), 0))

    def test_nonfinite_positions_and_nonunit_or_nonfinite_normals_are_rejected(self):
        for bad, error in (
            (self.last_native(0, float('nan')), 'corrected position'),
            (self.last_native(3, 0, 0, 0), 'nonunit corrected normal'),
            (self.last_native(3, float('inf'), 1, 0), 'nonunit corrected normal'),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValidationError, error):
                self.compare(native_samples=bad)
        for name in ('source_positions', 'source_normals'):
            sample = bytearray(getattr(self, 'positions' if name == 'source_positions' else 'normals'))
            pack_into('<f', sample, 0, float('nan'))
            with self.subTest(source=name), self.assertRaises(ValidationError):
                self.compare(**{name: bytes(sample)})

    def test_incomplete_trailing_or_noncorresponding_input_is_rejected(self):
        for changes in (
            dict(source_positions=self.positions[:-4]),
            dict(source_normals=self.normals + b'\0'),
            dict(native_samples=self.native[:-24]),
            dict(native_samples=self.native + b'\0'),
            dict(native_to_source=[0, 0, 1, 1]),
            dict(native_to_source=[2, False, 1, 2]),
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValidationError):
                self.compare(**changes)
