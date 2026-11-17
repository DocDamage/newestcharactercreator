"""Nonshipping synthetic position fixtures; no real clip, engine or quality proof."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import math
import struct
import unittest

from ucc.core.errors import ValidationError
from ucc.animations.target_action_diagnostic import (
    APPROVAL_FLAGS, DiagnosticSamples, JointPositionEndpoints,
    TargetActionDiagnosticSelection, measure_target_action_diagnostic,
)

IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
STILL = ((0.0, 0.0, 0.0),)*300


def selection():
    return TargetActionDiagnosticSelection('unit:nonshipping-project', 1,
        'a'*64, 'b'*64, 'unit:nonshipping-clip#clip-0000', 'c'*64, 'd'*64, 'e'*64)


def vertices(*rows):
    return b''.join(struct.pack('<fff', *row) for row in rows)


def samples(**kwargs):
    value = DiagnosticSamples(vertices((0, 0, 0), (1, 0, 0)),
        vertices((0, 0, 0), (1, 0, 0)), IDENTITY, STILL, STILL,
        cache_sha256='f'*64, timeline_sha256='1'*64)
    return replace(value, **kwargs)


def measure(value=None, **kwargs):
    return measure_target_action_diagnostic(selection(), value or samples(), **kwargs)


class PositionDiagnosticTests(unittest.TestCase):
    def test_clock_distinguishes_sample_span_from_nominal_duration(self):
        clock = measure().clock
        self.assertEqual((clock.source_first_frame, clock.source_last_frame), (2, 301))
        self.assertEqual((clock.target_first_frame, clock.target_last_frame), (1, 300))
        self.assertEqual((clock.frame_count, clock.fps, clock.playback_policy),
            (300, 30.0, 'ONCE_HOLD_LAST'))
        self.assertEqual(clock.elapsed_span_s, 299/30)
        self.assertEqual(clock.nominal_duration_s, 10)
        self.assertNotEqual(clock.elapsed_span_s, clock.nominal_duration_s)

    def test_root_head_and_source_hip_are_different_measured_trajectories(self):
        hips = tuple((i/299*3, 0.0, 0.0) for i in range(300))
        report = measure(samples(root_world_heads=((7.0, 4.0, 2.0),)*300,
            hip_midpoints_world=hips))
        self.assertEqual(report.root_world_head.net_displacement_m, (0, 0, 0))
        self.assertEqual(report.root_world_head.path_length_m, 0)
        self.assertEqual(report.source_hip_midpoint.net_displacement_m, (3, 0, 0))
        self.assertAlmostEqual(report.source_hip_midpoint.path_length_m, 3)
        self.assertAlmostEqual(report.source_hip_midpoint.mean_speed_m_s, 3/(299/30))

    def test_trajectory_return_to_start_does_not_hide_travel_or_max_speed(self):
        points = tuple((float(i % 2), 0.0, 0.0) for i in range(299)) + ((0.0, 0.0, 0.0),)
        root = measure(samples(root_world_heads=points)).root_world_head
        self.assertEqual(root.net_distance_m, 0)
        self.assertEqual(root.path_length_m, 298)
        self.assertEqual(root.max_step_m, 1)
        self.assertEqual(root.max_speed_m_s, 30)
        self.assertAlmostEqual(root.mean_speed_m_s, 298/(299/30))

    def test_rigid_translation_removed_only_by_source_hip_translation(self):
        hips = tuple((i/299*2, 0.0, 0.0) for i in range(300))
        report = measure(samples(last_vertices=vertices((2, 0, 0), (3, 0, 0)),
            hip_midpoints_world=hips))
        self.assertEqual(report.endpoint_mesh.raw_rms_m, 2)
        self.assertEqual(report.endpoint_mesh.raw_max_m, 2)
        self.assertEqual(report.endpoint_mesh.hip_translation_only_rms_m, 0)
        self.assertEqual(report.endpoint_mesh.hip_translation_only_max_m, 0)
        self.assertEqual(report.root_world_head.net_distance_m, 0)

    def test_endpoint_rms_averages_euclidean_vertex_distances_not_components(self):
        report = measure(samples(last_vertices=vertices((0, 0, 0), (3, 0, 0))))
        self.assertAlmostEqual(report.endpoint_mesh.raw_rms_m, math.sqrt(2))
        self.assertEqual(report.endpoint_mesh.raw_max_m, 2)

    def test_world_transform_scale_and_axes_apply_before_hip_compensation(self):
        matrix = (0, -2, 0, 10, 2, 0, 0, 20, 0, 0, 2, 30, 0, 0, 0, 1)
        report = measure(samples(first_vertices=vertices((0, 0, 0)),
            last_vertices=vertices((1, 0, 0)), world_matrix=matrix,
            hip_midpoints_world=tuple((0.0, i/299*2, 0.0) for i in range(300))))
        self.assertEqual(report.endpoint_mesh.raw_rms_m, 2)
        self.assertEqual(report.endpoint_mesh.hip_translation_only_rms_m, 0)

    def test_rotation_and_pose_differences_are_not_aligned_away_or_approved(self):
        report = measure(samples(first_vertices=vertices((1, 0, 0)),
            last_vertices=vertices((0, 1, 0))))
        self.assertAlmostEqual(report.endpoint_mesh.raw_rms_m, math.sqrt(2))
        self.assertEqual(report.endpoint_mesh.raw_rms_m,
            report.endpoint_mesh.hip_translation_only_rms_m)
        data = report.to_dict()
        self.assertTrue(data['diagnostic_only'])
        self.assertFalse(data['automatic_threshold_pass'])
        self.assertTrue(all(data[name] is False for name in APPROVAL_FLAGS))

    def test_optional_explicit_joint_endpoints_are_position_only(self):
        row = JointPositionEndpoints('explicit-mapped-foot', (0.0, 0.0, 0.0), (0.0, 3.0, 4.0))
        report = measure(samples(mapped_joint_endpoints=(row,)))
        self.assertEqual(report.mapped_joint_gaps[0].raw_distance_m, 5)
        self.assertEqual(report.mapped_joint_gaps[0].hip_translation_only_distance_m, 5)
        self.assertTrue(report.to_dict()['mapped_joint_position_endpoints_available'])
        self.assertFalse(measure().to_dict()['mapped_joint_position_endpoints_available'])

    def test_explicit_joint_names_must_be_bounded_distinct_and_typed(self):
        row = JointPositionEndpoints('mapped', (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        for rows in ([row], (row, replace(row, name='MAPPED')), (row,)*65,
                (replace(row, name=''),), (replace(row, name='bad\nname'),),
                (replace(row, first_world=[0, 0, 0]),)):
            with self.subTest(rows=str(type(rows))), self.assertRaises(ValidationError):
                measure(samples(mapped_joint_endpoints=rows))

    def test_nonfinite_and_oversized_trajectory_values_reject(self):
        for value in (float('nan'), float('inf'), -float('inf'), 10001, 2**10000, True):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValidationError):
                measure(samples(root_world_heads=((value, 0.0, 0.0),)+STILL[1:]))

    def test_nonfinite_endpoint_vertices_reject(self):
        for value in (float('nan'), float('inf'), -float('inf'), 10001.0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                measure(samples(first_vertices=vertices((value, 0, 0)),
                    last_vertices=vertices((0, 0, 0))))

    def test_malformed_or_oversized_endpoint_buffers_reject(self):
        for value in (b'', b'bad', bytearray(24), b'\0'*(100001*12), b'\0'*12):
            with self.subTest(length=len(value)), self.assertRaises(ValidationError):
                measure(samples(first_vertices=value))

    def test_world_matrix_ownership_convention_and_transform_validity(self):
        for matrix in (list(IDENTITY), IDENTITY[:-1],
                (-1, *IDENTITY[1:]), (0, *IDENTITY[1:]),
                (1, 1, *IDENTITY[2:]), (*IDENTITY[:15], 2),
                (float('nan'), *IDENTITY[1:]), (True, *IDENTITY[1:])):
            with self.subTest(matrix=str(matrix)[:30]), self.assertRaises(ValidationError):
                measure(samples(world_matrix=matrix))

    def test_clock_policy_and_complete_immutable_sample_coverage_reject_drift(self):
        changes = ({'fps': True}, {'fps': float('nan')}, {'fps': 2**10000}, {'fps': 29.97},
            {'source_first_frame': True}, {'source_first_frame': 1}, {'target_first_frame': 2},
            {'root_motion_policy': 'ARMATURE_ORIGIN_DISPLACEMENT_V1'},
            {'root_world_heads': STILL[:-1]}, {'hip_midpoints_world': list(STILL)},
            {'root_world_heads': ((0.0, 0.0),)+STILL[1:]})
        for change in changes:
            with self.subTest(fields=tuple(change)), self.assertRaises(ValidationError):
                measure(samples(**change))

    def test_cancellation_propagates_at_entry_and_during_bounded_mesh_loop(self):
        class CallerCancelled(Exception):
            pass
        for stop in (1, 650):
            called = 0
            def check():
                nonlocal called
                called += 1
                if called == stop:
                    raise CallerCancelled('synthetic cancellation')
            with self.subTest(stop=stop), self.assertRaises(CallerCancelled):
                measure(samples(first_vertices=vertices(*([(0, 0, 0)]*10000)),
                    last_vertices=vertices(*([(1, 0, 0)]*10000))), cancel_check=check)
            self.assertEqual(called, stop)

    def test_selection_is_closed_engine_neutral_and_revision_is_not_boolean(self):
        value = selection().to_dict()
        self.assertEqual(TargetActionDiagnosticSelection.from_dict(value), selection())
        self.assertEqual(selection().loader_args()['expected_clip_id'], selection().clip_id)
        for changed in ({**value, 'revision': True}, {**value, 'binding_sha256': 'bad'},
                {**value, 'engine': 'not permitted'}):
            with self.assertRaises(ValidationError):
                TargetActionDiagnosticSelection.from_dict(changed)
        with self.assertRaises(ValidationError):
            measure_target_action_diagnostic(value, samples())

    def test_report_is_immutable_scalar_aggregate_with_bound_proof_hashes(self):
        value = samples()
        report = measure(value)
        with self.assertRaises(FrozenInstanceError):
            report.root_world_head.path_length_m = 999
        data = report.to_dict()
        self.assertEqual(data['root_motion_policy'], 'SOURCE_HIP_MIDPOINT_V1')
        self.assertEqual(data['proof_hashes']['cache_sha256'], 'f'*64)
        self.assertEqual(data['proof_hashes']['timeline_sha256'], '1'*64)
        self.assertEqual(data['proof_hashes']['first_endpoint_vertices_sha256'],
            sha256(value.first_vertices).hexdigest())
        encoded = json.dumps(data, allow_nan=False)
        self.assertLess(len(encoded), 5000)
        self.assertNotIn('root_world_heads', encoded)
        self.assertNotIn('first_vertices', encoded)
        self.assertNotIn('world_matrix', encoded)

    def test_proof_hash_identity_is_strict(self):
        for key in ('cache_sha256', 'timeline_sha256'):
            with self.assertRaises(ValidationError):
                samples(**{key: 'not-a-verified-document-hash'})


if __name__ == '__main__':
    unittest.main()
