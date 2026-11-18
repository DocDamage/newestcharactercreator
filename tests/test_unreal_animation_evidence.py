"""Analytic controls for the Unreal FBX world basis and centimetre unit scale."""
from struct import pack
from unittest import TestCase

from ucc.core.errors import ValidationError
from ucc.export.unreal_animation_evidence import compare_unreal_animation
from ucc.export.unreal_animation_observation import _check_preview


_REST = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
_SOURCE_POSE = [1, 0, 0, .125, 0, 1, 0, .25, 0, 0, 1, .5, 0, 0, 0, 1]
_UNREAL_POSE = [1, 0, 0, -25, 0, 1, 0, -12.5, 0, 0, 1, 50, 0, 0, 0, 1]


class UnrealAnimationEvidenceTests(TestCase):
    def setUp(self):
        self.inputs = dict(
            source_bind_points_m=[[0, 0, 0], [1, 2, 3]],
            native_bind_points_cm=[[-200, -100, 300], [0, 0, 0], [-200, -100, 300]],
            source_bones=[dict(name='Root', parent=None, world=_REST)],
            native_bones=[dict(name='Root', parent='', rest_world=_REST)],
            source_pose_samples=pack('<16f', *_SOURCE_POSE)*300,
            native_pose_samples=pack('<16f', *_UNREAL_POSE)*300,
            source_raw_samples=pack('<6f', .125, .25, .5, 1.125, 2.25, 3.5)*300,
            native_raw_samples=pack('<9f', -225, -112.5, 350, -25, -12.5, 50, -225, -112.5, 350)*300,
            check=lambda: None,
        )

    def test_reordered_native_vertices_and_centimetre_pose_samples(self):
        evidence = compare_unreal_animation(**self.inputs)
        self.assertEqual(evidence.samples.frames, 300)
        self.assertEqual(evidence.samples.native_vertices, 3)
        self.assertEqual(evidence.samples.maximum_raw_skin_error_m, 0)
        self.assertEqual(evidence.maximum_bind_position_error_m, 0)

    def test_wrong_unit_and_terminal_motion_are_rejected(self):
        self.inputs['native_pose_samples'] = self.inputs['source_pose_samples']
        with self.assertRaisesRegex(ValidationError, 'bone translation'):
            compare_unreal_animation(**self.inputs)
        self.inputs['native_pose_samples'] = pack('<16f', *_UNREAL_POSE)*300
        self.inputs['native_raw_samples'] = self.inputs['native_raw_samples'][:-4] + pack('<f', 351)
        with self.assertRaisesRegex(ValidationError, 'raw skin.*300'):
            compare_unreal_animation(**self.inputs)

    def test_ordinary_preview_must_wrap_with_current_native_pose(self):
        frames = [_REST[:3] + [i*.01] + _REST[4:] for i in range(300)]
        samples = b''.join(pack('<16f', *matrix) for matrix in frames)
        rows = [{'time_seconds': frame/30, 'pose_world': frames[frame].copy()}
                for frame in (298, 299, 0, 1, 2, 3, 4)]
        _check_preview(rows, samples, 1, lambda: None)
        rows[4]['pose_world'][3] += 1
        with self.assertRaisesRegex(ValidationError, 'world-ticked pose'):
            _check_preview(rows, samples, 1, lambda: None)
