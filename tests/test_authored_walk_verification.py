"""Nonshipping metadata and geometry controls for original walk verification."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import UUID

from blender_bridge import walk_authoring_verify as verifier
from blender_bridge.idle_authoring_policy import AuthoredIdleError
from blender_bridge.walk_authoring_phase import sample_walk
from blender_bridge.walk_authoring_verify_scene import check_invariants, contact_gates, measure_contact, wrap_residual
from fixtures.authored_idle_contract import inspection
from ucc.core.target_action_format import canonical_bytes, read_document


class WalkVerification(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        master = b'synthetic verifier master, not a Blender scene'
        master_sha = sha256(master).hexdigest()
        reviewed = inspection(hand=False, expression=False)
        project = replace(reviewed.project, master_blend=f'master/versions/{master_sha}.blend', animations=())
        request = replace(reviewed, project_snapshot_json=canonical_bytes(project.to_dict()),
                          permissions=(replace(reviewed.permissions[0], source_sha256=master_sha),
                                       *reviewed.permissions[1:]))
        self.target = {'project_id': project.project_id}
        self.files = {
            'candidate.blend': master,
            'project.ucc.json': request.project_snapshot_json,
            'idle_inspection_request.json': canonical_bytes(request.to_dict()),
            'idle_anatomical_frame.json': canonical_bytes({'target': self.target}),
            'walk_authoring_request.json': canonical_bytes({'synthetic': 'checked separately by the typed parser'}),
            'original_walk.blend': b'synthetic review input, not a Blender scene',
            'original_walk.fbx': b'synthetic FBX input, not a Blender scene',
        }
        for name, data in self.files.items():
            (self.root / name).write_bytes(data)
        self.job = {
            'operation': verifier.OPERATION, 'input_project': 'candidate.blend', 'job_id': str(UUID(int=919)),
            'options': {opt: sha256(self.files[name]).hexdigest() for name, opt in verifier.INPUT_OPTIONS.items()},
        }
        self.intent = self.enterContext(patch.object(verifier, 'read_walk_intent'))
        self.measure = self.enterContext(patch.object(verifier, 'measure', return_value=(
            {'target': self.target}, object(), object(), object())))
        self.observe = self.enterContext(patch.object(verifier, 'observe_saved'))
        self.observe.return_value.metrics = passing_metrics()
        self.reimport = self.enterContext(patch.object(verifier, '_verify_fbx'))

    def test_checked_inputs_and_independent_output_bindings(self):
        record = {'name': verifier.SNAPSHOT, 'bytes': 123, 'sha256': '7' * 64}
        self.reimport.return_value = {'import_clock': [2, 301, 30]}, record
        result = verifier.verify_source(Mock(), self.root, self.job)
        self.assertEqual(result['status'], verifier.STATUS)
        self.assertEqual(set(result['outputs']), {verifier.REPORT, verifier.SNAPSHOT})
        report = read_document((self.root / verifier.REPORT).read_bytes())
        self.assertEqual(report['source_snapshot'], record)
        self.assertEqual(report['input_sha256'],
                         {name: sha256(data).hexdigest() for name, data in self.files.items()})
        self.assertEqual(report['walk_request_sha256'], self.job['options']['walk_request_sha256'])
        self.assertEqual(len(report['technical_contact_checks']), 9)
        self.assertTrue(all(report['technical_contact_checks'].values()))
        for flag in ('visual_quality_approved', 'usable_action_approved', 'target_registered', 'engine_imported'):
            self.assertIs(report[flag], False)
        self.assertEqual(result['outputs'][verifier.REPORT]['sha256'],
                         sha256((self.root / verifier.REPORT).read_bytes()).hexdigest())
        self.intent.assert_called_once()

    def test_tampered_walk_intent_stops_before_any_blender_call(self):
        (self.root / 'walk_authoring_request.json').write_bytes(b'modified staged input')
        with self.assertRaises(AuthoredIdleError):
            verifier.verify_source(Mock(), self.root, self.job)
        self.measure.assert_not_called()
        self.observe.assert_not_called()
        self.reimport.assert_not_called()

    def test_contact_failure_prevents_positive_report_and_fbx_import(self):
        self.observe.return_value.metrics['minimum']['visible_floor_m'] = -.002
        with self.assertRaisesRegex(AuthoredIdleError, 'contact or knee'):
            verifier.verify_source(Mock(), self.root, self.job)
        self.reimport.assert_not_called()
        self.assertFalse((self.root / verifier.REPORT).exists())

    def test_source_change_after_reopen_prevents_positive_outputs(self):
        def alter(*_):
            (self.root / 'original_walk.fbx').write_bytes(b'modified after review')
            return self.observe.return_value

        self.observe.side_effect = alter
        with self.assertRaisesRegex(AuthoredIdleError, 'changed a bound input'):
            verifier.verify_source(Mock(), self.root, self.job)
        self.reimport.assert_not_called()
        self.assertFalse((self.root / verifier.REPORT).exists())


def passing_metrics():
    return {
        'minimum': {'visible_floor_m': 0., 'weighted_floor_m': 0., 'peak_swing_clearance_m': .05,
                    'knee_flex_deg': 20., 'knee_pole_alignment': 1.},
        'maximum': {'stance_anchor_m': 0., 'stance_drift_m': 0., 'stance_height_m': 0.,
                    'knee_flex_deg': 56., 'adjacent_knee_step_deg': 8.},
    }


class WalkSavedSceneMeasurements(TestCase):
    def test_compensated_stance_and_injected_forefoot_slide(self):
        start = sample_walk(0)
        next_frame = sample_walk(1)
        neutral = [(0., 0., 0.), (.2, 0., .001), (.4, 0., 0.)]
        region = ((0, 1, 2), (0, 1, 2, 3), neutral, ((0,), (1,), (2,)))
        anchors = {}

        def measure(row, defect=False):
            points = [(x + row.left.forward_m, y, z) for x, y, z in neutral]
            points.append((.1, .1, .1))
            if defect:
                x, _, _ = points[2]
                points[2] = (x, .003, -.002)
            return measure_contact(points, region, row.left, row.time_s * .650, (1., 0., 0.), 0., anchors)

        self.assertTrue(all(abs(value) < 1e-12 for value in measure(start).values()))
        changed = measure(next_frame, defect=True)
        self.assertAlmostEqual(changed['fore_drift_m'], .003)
        self.assertEqual(changed['weighted_floor_m'], -.002)
        self.assertEqual(changed['fore_height_m'], .002)
        metrics = passing_metrics()
        metrics['maximum']['stance_drift_m'] = changed['fore_drift_m']
        metrics['minimum']['weighted_floor_m'] = changed['weighted_floor_m']
        self.assertFalse(contact_gates(metrics)['compensated_stance_drift'])
        self.assertFalse(contact_gates(metrics)['weighted_foot_floor'])

    def test_declared_offset_and_unrelated_world_transform(self):
        neutral = {'pose_channels': {}, 'objects': {name: {'world': [0.]*16}
                                                   for name in ('rig', 'skin', 'unrelated')}}
        actual = deepcopy(neutral)
        for name in ('rig', 'skin'):
            actual['objects'][name]['world'][11] = -.045
        check_invariants(deepcopy(actual), deepcopy(neutral), {'rig', 'skin'}, -.045)
        actual['objects']['unrelated']['world'][11] = -.045
        with self.assertRaisesRegex(AuthoredIdleError, 'UNAUTHORIZED_OBJECT_TRANSFORM'):
            check_invariants(actual, neutral, {'rig', 'skin'}, -.045)

    def test_seam_uses_equivalent_nonzero_internal_step(self):
        self.assertEqual(wrap_residual([10., 20.], [12., 24.], [3., 5.], [5., 9.]), 0.)
        self.assertEqual(wrap_residual([10.], [12.], [3.], [6.]), 30.)
