"""Nonshipping matrix fixtures for source-backed wrist preview corrections."""

from copy import deepcopy
import math
import unittest

from ucc.animations import native_math as nm
from ucc.animations.native_preview_adjustments import adjusted_native_preview_source, validate_preview_adjustments
from ucc.animations.wrist_transitions import preview_source_motion, validate_wrist_transitions
from ucc.core.errors import ValidationError


def transform(degrees, xyz):
    radians = math.radians(degrees)
    c, s = math.cos(radians), math.sin(radians)
    x, y, z = xyz
    return [[c, -s, 0., x], [s, c, 0., y], [0., 0., 1., z], [0., 0., 0., 1.]]


def flatten(matrix):
    return [value for row in matrix for value in row]


def synthetic_source(middle=120.):
    frames = []
    for i, degrees in enumerate((0., 0., middle, 90., 90.)):
        forearm = transform(i * 5., (2. + i, 3., 4.))
        wrist = nm.product(forearm, transform(degrees, (0., 2., 0.)))
        finger = nm.product(wrist, transform(25., (0., 1., .5)))
        poses = [forearm, wrist, finger, transform(15., (3., 5., 7.))]
        frames.append({'frame': 65+i, 'armature_world': flatten(transform(0., (i, 0., 0.))),
                       'poses': [flatten(matrix) for matrix in poses], 'pose_sha256': 'synthetic'})
    return {'first_frame': 65, 'frames': frames, 'bones': [
        {'name': 'Forearm', 'parent': None}, {'name': 'Wrist', 'parent': 'Forearm'},
        {'name': 'Finger', 'parent': 'Wrist'}, {'name': 'Other', 'parent': None},
    ]}


def profile():
    return {'landmarks': {'left_hand': {'source': 'Wrist'}},
            'skin_deformation_policy': 'BOUND_CORRECTIVE_SMOOTH_V1',
            'wrist_transitions': {'schema_version': 1, 'windows': [
                {'side': 'left', 'first_frame': 66, 'last_frame': 68},
            ]}}


def local(frame, index, parent):
    return nm.product(nm.inverse(nm.rows(frame['poses'][parent])), nm.rows(frame['poses'][index]))


class WristTransitionTests(unittest.TestCase):
    def test_only_interior_wrist_sample_changes_and_preserves_hand_hierarchy(self):
        source = synthetic_source()
        original = deepcopy(source)
        derived = preview_source_motion(source, profile())
        self.assertEqual(source, original)
        self.assertEqual([row['frame'] for row, result in zip(source['frames'], derived['frames'])
                          if row != result], [67])
        before, after = source['frames'][2], derived['frames'][2]
        self.assertEqual(before['armature_world'], after['armature_world'])
        for index in (0, 3):
            self.assertEqual(before['poses'][index], after['poses'][index])
        self.assertNotEqual(before['pose_sha256'], after['pose_sha256'])
        for expected, actual in zip(flatten(transform(45., (0., 2., 0.))), flatten(local(after, 1, 0))):
            self.assertAlmostEqual(expected, actual, places=12)
        for expected, actual in zip(flatten(local(before, 2, 1)), flatten(local(after, 2, 1))):
            self.assertAlmostEqual(expected, actual, places=12)

    def test_legacy_source_is_returned_and_routine_motion_is_not_edited(self):
        source = synthetic_source(45.)
        self.assertIs(preview_source_motion(source, {}), source)
        with self.assertRaisesRegex(ValidationError, 'measured discontinuity'):
            preview_source_motion(source, profile())

    def test_invalid_windows_and_unreviewed_skin_fail_closed(self):
        source = synthetic_source()
        invalid = profile()
        invalid['wrist_transitions']['windows'][0].update(first_frame=64, last_frame=66)
        with self.assertRaisesRegex(ValidationError, 'outside the measured source clock'):
            preview_source_motion(source, invalid)
        overlap = profile()
        overlap['wrist_transitions']['windows'].append({'side': 'left', 'first_frame': 68, 'last_frame': 70})
        with self.assertRaisesRegex(ValidationError, 'ordered, disjoint'):
            validate_wrist_transitions(overlap)
        bad_skin = profile()
        bad_skin['skin_deformation_policy'] = 'MASTER_MODIFIERS_V1'
        with self.assertRaisesRegex(ValidationError, 'saved-skin'):
            validate_wrist_transitions(bad_skin)

class ForearmRollTests(unittest.TestCase):
    def declaration(self):
        selected = profile()
        selected['landmarks']['left_hand']['target'] = 'wrist.L'
        selected['hand_reference_planes'] = {}
        selected['pairs'] = [
            {'source': 'Forearm', 'source_tip': 'Wrist', 'target_tip': 'wrist.L'},
        ]
        selected['forearm_roll'] = {'schema_version': 1, 'windows': [
            {'side': 'left', 'first_frame': 65, 'angle_tenths': [0, 10, 20, 10, 0]},
        ]}
        return selected

    def test_measured_ray_roll_rotates_only_the_forearm_basis(self):
        source = synthetic_source()
        baseline = deepcopy(source)
        selected = self.declaration()
        del selected['wrist_transitions']
        adjusted = adjusted_native_preview_source(source, selected)
        self.assertEqual(source, baseline)
        for before, after in zip(source['frames'], adjusted['frames']):
            if before['frame'] in (65, 69):
                self.assertIs(before, after)
                continue
            self.assertNotEqual(before['poses'][0], after['poses'][0])
            self.assertEqual(before['poses'][1:], after['poses'][1:])
            self.assertEqual(before['armature_world'], after['armature_world'])
            self.assertEqual([before['poses'][0][i] for i in (3, 7, 11)],
                             [after['poses'][0][i] for i in (3, 7, 11)])
            self.assertEqual(after['pose_sha256'], nm.pose_digest(after['armature_world'], after['poses']))
            for original, revised in zip((local(before, 1, 0)[i][3] for i in range(3)),
                                         (local(after, 1, 0)[i][3] for i in range(3))):
                self.assertAlmostEqual(original, revised, places=12)

    def test_forearm_roll_preserves_the_already_corrected_wrist(self):
        source = synthetic_source()
        selected = self.declaration()
        wrist_only = preview_source_motion(source, selected)
        derived = adjusted_native_preview_source(source, selected)
        self.assertNotEqual(wrist_only['frames'][2]['poses'][0], derived['frames'][2]['poses'][0])
        self.assertEqual(wrist_only['frames'][2]['poses'][1:], derived['frames'][2]['poses'][1:])
        self.assertIs(adjusted_native_preview_source(source, {}), source)

    def test_scope_rejects_unbounded_steps_frames_and_hierarchy(self):
        for angles in ([0, 20, 0], [1, 10, 0], [0, 0, 0], [0, True, 0], [0, 10]*9):
            with self.subTest(angles=angles), self.assertRaises(ValidationError):
                selected = self.declaration()
                selected['forearm_roll']['windows'][0]['angle_tenths'] = angles
                validate_preview_adjustments(selected)
        selected = self.declaration()
        selected['forearm_roll']['windows'][0]['first_frame'] = 64
        with self.assertRaisesRegex(ValidationError, 'outside the measured source clock'):
            adjusted_native_preview_source(synthetic_source(), selected)
        source = synthetic_source()
        source['bones'][1]['parent'] = 'Other'
        with self.assertRaisesRegex(ValidationError, 'direct hand child'):
            adjusted_native_preview_source(source, self.declaration())
