"""Contract tests for the preview-only calibrated opening correction."""
from copy import deepcopy
import unittest

from fixtures.planted_knee import planted_knee_case
from ucc.animations import native_math as nm
from ucc.animations.native_preview_adjustments import adjusted_native_preview_source
from ucc.animations.planted_knee import validate_planted_alignment
from ucc.core.errors import ValidationError


class PlantedKneeTests(unittest.TestCase):
    def test_opening_raises_only_root_and_preserves_all_foot_world_poses(self):
        source,profile = planted_knee_case()
        original = deepcopy(source)
        derived = adjusted_native_preview_source(source,profile)
        self.assertEqual(source,original)
        self.assertIs(derived['frames'][1],source['frames'][1])
        self.assertIs(derived['frames'][2],source['frames'][2])
        before,after = source['frames'][0],derived['frames'][0]
        self.assertGreater(after['armature_world'][11],before['armature_world'][11])
        self.assertEqual(after['armature_world'][:11],before['armature_world'][:11])
        self.assertNotEqual(before['poses'][1],after['poses'][1])
        for index in (2,3,6,7):
            saved = nm.product(nm.rows(before['armature_world']),nm.rows(before['poses'][index]))
            adjusted = nm.product(nm.rows(after['armature_world']),nm.rows(after['poses'][index]))
            for old,new in zip(saved,adjusted):
                for a,b in zip(old,new):
                    self.assertAlmostEqual(a,b,places=12)
        self.assertEqual(after['pose_sha256'],nm.pose_digest(after['armature_world'],after['poses']))

    def test_mismatched_axis_or_window_fails(self):
        source,profile = planted_knee_case()
        with self.assertRaisesRegex(ValidationError,'calibrated target vertical'):
            validate_planted_alignment(profile,[[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])
        profile['planted_knee']['frame_count'] = 2
        with self.assertRaisesRegex(ValidationError,'unneeded'):
            adjusted_native_preview_source(source,profile)
        profile['planted_knee']['frame_count'] = 1
        profile['planted_knee']['source_lift_axis'] = [0.,0.,2.]
        with self.assertRaisesRegex(ValidationError,'unit source lift axis'):
            adjusted_native_preview_source(source,profile)

    def test_wrong_geometry_or_handoff_fails(self):
        source,profile = planted_knee_case()
        source['bones'][1]['parent'] = None
        with self.assertRaisesRegex(ValidationError,'direct hip-knee-foot'):
            adjusted_native_preview_source(source,profile)
        source,profile = planted_knee_case()
        source['frames'][1]['poses'] = deepcopy(source['frames'][0]['poses'])
        with self.assertRaisesRegex(ValidationError,'untouched motion'):
            adjusted_native_preview_source(source,profile)


    def test_flight_window_eases_into_and_out_of_the_deep_knee(self):
        source,profile = planted_knee_case()
        low,high,_ = source['frames']
        source['frames'] = [deepcopy(low if i == 7 else high) for i in range(15)]
        for i,row in enumerate(source['frames']):
            row['frame'] = source['first_frame']+i
        profile['planted_knee'].update(schema_version=2,first_frame=12,frame_count=5)
        adjusted = adjusted_native_preview_source(source,profile)
        changes = []
        for i,(before,after) in enumerate(zip(source['frames'],adjusted['frames'])):
            if before is not after:
                changes.append(i)
                self.assertGreater(after['armature_world'][11],before['armature_world'][11])
                for foot in (2,3,6,7):
                    old = nm.product(nm.rows(before['armature_world']),nm.rows(before['poses'][foot]))
                    new = nm.product(nm.rows(after['armature_world']),nm.rows(after['poses'][foot]))
                    self.assertAlmostEqual(old[2][3],new[2][3],places=12)
        self.assertEqual(changes,list(range(5,10)))
        profile['planted_knee'].update(first_frame=13,frame_count=3)
        with self.assertRaisesRegex(ValidationError,'does not join'):
            adjusted_native_preview_source(source,profile)

    def test_folded_window_preserves_foot_transforms_and_adjacent_samples(self):
        source, profile = planted_knee_case()
        deep, shallow, _ = source['frames']
        middle = deepcopy(deep)
        middle['frame'] = 8
        source['frames'] = [{**shallow, 'frame': 7}, middle, {**shallow, 'frame': 9}]
        profile['planted_knee'] = {'schema_version': 3, 'first_frame': 8, 'frame_count': 1}

        derived = adjusted_native_preview_source(source, profile)
        before, after = middle, derived['frames'][1]
        self.assertIs(derived['frames'][0], source['frames'][0])
        self.assertIs(derived['frames'][2], source['frames'][2])
        self.assertNotEqual(after['armature_world'], before['armature_world'])
        for index in (2, 3, 6, 7):
            old = nm.product(nm.rows(before['armature_world']), nm.rows(before['poses'][index]))
            new = nm.product(nm.rows(after['armature_world']), nm.rows(after['poses'][index]))
            for old_row, new_row in zip(old, new):
                for original, corrected in zip(old_row, new_row):
                    self.assertAlmostEqual(original, corrected, places=12)

        profile['planted_knee']['source_lift_axis'] = [0., 0., 1.]
        with self.assertRaises(ValidationError):
            adjusted_native_preview_source(source, profile)
