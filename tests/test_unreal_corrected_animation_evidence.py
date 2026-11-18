"""Synthetic float32 streams test numeric admission without running Unreal."""

from math import cos, radians, sin
from struct import pack, pack_into
import unittest
from unittest.mock import Mock, patch

from ucc.core.errors import ValidationError
from ucc.export import unreal_corrected_animation_evidence as evidence


class UnrealCorrectedAnimationEvidenceTests(unittest.TestCase):
    def setUp(self):
        profile = patch.object(evidence, 'SOURCE_VERTICES', 3)
        profile.start()
        self.addCleanup(profile.stop)
        # The fourth Unreal render vertex is a seam duplicate of Blender vertex 2.
        self.mapping = (2, 0, 1, 2)
        self.positions = pack('<18f', 1, 2, 3, 0, 0, 0, 4, 5, 6, 7, 8, 9, 0, 0, 0, 0, 0, 0) * 150
        self.normals = pack('<18f', 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1) * 150
        self.native = pack(
            '<48f',
            -500, -400, 600, 0, 0, 1, -200, -100, 300, 0, -1, 0,
            0, 0, 0, -1, 0, 0, -500, -400, 600, 0, 0, 1,
            0, 0, 0, 0, 0, 1, -800, -700, 900, 0, -1, 0,
            0, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 1,
        ) * 150
        self.check = Mock()

    def compare(self, **changes):
        values = dict(source_positions=self.positions, source_normals=self.normals,
                      native_samples=self.native, native_to_source=self.mapping, check=self.check)
        return evidence.compare_unreal_corrected_animation(**(values | changes))

    def last_native(self, component, *values):
        data = bytearray(self.native)
        pack_into(f'<{len(values)}f', data, len(data) - 24 + component*4, *values)
        return bytes(data)

    def test_unreal_cm_and_reflected_normal_mapping_match_all_300_samples(self):
        observed = self.compare()
        self.assertEqual((observed.frames, observed.source_vertices, observed.native_vertices,
                          observed.compared_vertices), (300, 3, 4, 1200))
        self.assertEqual(observed.maximum_position_error_m, 0.0)
        self.assertEqual(observed.maximum_normal_angle_deg, 0.0)
        self.assertEqual(self.check.call_count, 301)

    def test_last_seam_duplicate_is_checked_at_the_pointwise_10_micrometre_limit(self):
        result = self.compare(native_samples=self.last_native(0, 0.00099))
        self.assertAlmostEqual(result.maximum_position_error_m, 9.9e-6)
        with self.assertRaisesRegex(ValidationError, 'position.*frame 300, vertex 3'):
            self.compare(native_samples=self.last_native(0, 0.00101))

    def test_last_seam_duplicate_is_checked_at_the_pointwise_0_1_degree_limit(self):
        angle = radians(0.099)
        result = self.compare(native_samples=self.last_native(3, sin(angle), 0, cos(angle)))
        self.assertAlmostEqual(result.maximum_normal_angle_deg, 0.099, places=5)
        angle = radians(0.101)
        with self.assertRaisesRegex(ValidationError, 'normal differs.*frame 300, vertex 3'):
            self.compare(native_samples=self.last_native(3, sin(angle), 0, cos(angle)))

    def test_nonfinite_positions_and_nonunit_or_nonfinite_normals_fail_closed(self):
        for data, message in (
            (self.last_native(0, float('inf')), 'corrected position'),
            (self.last_native(3, 0, 0, 0), 'nonunit corrected normal'),
            (self.last_native(3, float('nan'), 0, 1), 'nonunit corrected normal'),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValidationError, message):
                self.compare(native_samples=data)
        for name, raw in (('source_positions', self.positions), ('source_normals', self.normals)):
            changed = bytearray(raw)
            pack_into('<f', changed, 0, float('nan'))
            with self.subTest(source=name), self.assertRaises(ValidationError):
                self.compare(**{name: bytes(changed)})

    def test_frame_byte_counts_and_map_must_be_closed(self):
        for changed in (
            dict(source_positions=self.positions[:-12]),
            dict(source_normals=self.normals + b'\0'),
            dict(native_samples=self.native[:-96]),
            dict(native_samples=self.native + b'\0'),
            dict(native_to_source=[0, 0, 1, 1]),
            dict(native_to_source=[2, False, 1, 2]),
            dict(native_to_source=[2, 0, -1, 2]),
        ):
            with self.subTest(changed=tuple(changed)), self.assertRaises(ValidationError):
                self.compare(**changed)
        with patch.object(evidence, 'MAX_NATIVE_VERTICES', 3), self.assertRaises(ValidationError):
            self.compare()
