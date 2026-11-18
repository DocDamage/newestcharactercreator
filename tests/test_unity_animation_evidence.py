"""Synthetic numeric controls for original-source animation comparison."""
from struct import pack
from unittest import TestCase

from ucc.core.errors import ValidationError
from ucc.export.unity_animation_evidence import compare_unity_animation
from ucc.jobs.unity_corrected_animation_verification import _check_rows


_REST = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
_SOURCE_POSE = [0, -1, 0, .125, 1, 0, 0, .25, 0, 0, 1, .5, 0, 0, 0, 1]
_NATIVE_REST = [0, 0, 1, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 0, 1]
# The conjugated source rotation is a quarter-turn around Unity's Y axis.
_NATIVE_POSE = [1, 0, 0, -.125, 0, 1, 0, .5, 0, 0, 1, -.25, 0, 0, 0, 1]


class UnityAnimationEvidenceTests(TestCase):
    def setUp(self):
        self.inputs = dict(
            source_bones=[dict(name='Root', parent=None, world=_REST)],
            native_bones=[dict(name='Root', parent='', rest_world=_NATIVE_REST)],
            source_vertex_count=2, native_to_source=[1, 0, 1],
            source_pose_samples=pack('<16f', *_SOURCE_POSE)*300,
            native_pose_samples=pack('<16f', *_NATIVE_POSE)*300,
            source_raw_samples=pack('<6f', .125, .25, .5, 1, 2, 3)*300,
            native_raw_samples=pack('<9f', -1, 3, -2, -.125, .5, -.25, -1, 3, -2)*300,
            check=lambda: None,
        )

    def test_rest_basis_change_and_duplicate_render_vertices(self):
        result = compare_unity_animation(**self.inputs)
        self.assertEqual((result.frames, result.source_vertices, result.native_vertices, result.bones), (300, 2, 3, 1))
        self.assertEqual(result.maximum_bone_axis_error_deg, 0)

    def test_terminal_frame_skin_mismatch_rejects(self):
        self.inputs['native_raw_samples'] = self.inputs['native_raw_samples'][:-4] + pack('<f', -1)
        with self.assertRaisesRegex(ValidationError, 'raw skin differs.*300'):
            compare_unity_animation(**self.inputs)

    def test_basis_mutation_rejects(self):
        position = _NATIVE_POSE.copy()
        position[0] = position[10] = -1
        self.inputs['native_pose_samples'] = pack('<16f', *position)*300
        with self.assertRaisesRegex(ValidationError, 'orientation'):
            compare_unity_animation(**self.inputs)

    def test_fresh_correction_rejects_previous_draw_from_same_camera(self):
        stride = 24
        rows = [dict(sample=i, engine_frame=i + 30, camera_id=51, completed_frame=i + 30,
                     completed_camera=51, offset=i*stride) for i in range(300)]
        _check_rows(rows, stride)
        rows[-1]['completed_frame'] -= 1
        with self.assertRaisesRegex(ValidationError, 'stale.*300'):
            _check_rows(rows, stride)
