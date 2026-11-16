"""Rehashed forged layer/base reports must fail independent core validation."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.symmetric_evidence_contract import write_evidence
from ucc.jobs.native_fit_evidence import validate_fitted_data
from ucc.core.errors import ValidationError


class SymmetricEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.policy, self.options, self.baseline, self.profile, self.rest, self.data, self.document, self.base = write_evidence(self.root)

    def read(self):
        return validate_fitted_data(self.data, self.options, self.baseline, self.profile, self.policy, self.rest)

    def test_complete_math_and_base_evidence_do_not_invent_clearance(self):
        plan, surface, angular = self.read()
        self.assertEqual(sum(plan.active_frames), 13)
        self.assertEqual(surface.status, 'UNAVAILABLE')
        self.assertEqual(angular['frames'], 21); self.assertEqual(angular['tracked_joints'], 8)

    def test_rehashed_saved_pose_cannot_change_shoulder_root_or_retained_base(self):
        for frame, bone in ((14, 'clavL'), (14, 'handR'), (14, 'root'), (3, 'handR')):
            saved = deepcopy(self.data)
            i = [p['target'] for p in self.profile['pairs']].index(bone)
            self.data['frames'][frame-1]['target_global_poses'][i][3] += .001
            with self.subTest(frame=frame, bone=bone), self.assertRaises(ValidationError): self.read()
            self.data = saved

    def test_rehashed_base_pose_forgery_cannot_authorize_new_layer(self):
        self.base['frames'][2]['target_global_poses'][0][3] += .001
        payload = json.dumps(self.base).encode(); (self.root/'base_fitted_timeline.json').write_bytes(payload)
        digest = sha256(payload).hexdigest()
        self.options['base_fit_report_sha256'] = digest; self.data['bindings'] = dict(self.options)
        self.data['surface_review']['bindings'] = dict(self.options)
        self.document['bindings']['base_fit_report_sha256'] = digest
        self.policy.write_text(json.dumps(self.document)); self.options['fit_sha256'] = sha256(self.policy.read_bytes()).hexdigest()
        self.data['bindings'] = dict(self.options); self.data['surface_review']['bindings'] = dict(self.options)
        with self.assertRaisesRegex(ValidationError, 'pose|trajectory|fitting'): self.read()

    def test_changed_base_policy_and_incomplete_or_fabricated_angular_metrics_reject(self):
        original = deepcopy(self.data)
        for fault in ('metric', 'coverage', 'rest', 'approval'):
            self.data = deepcopy(original)
            if fault == 'metric': self.data['angular_correction_metrics']['max_acceleration_degrees_s2'] = 0.
            if fault == 'coverage': self.data['frames'].pop()
            if fault == 'rest': self.data['target_rest_frames']['helperL']['matrix'][3] += .01
            if fault == 'approval': self.data['contact_quality_verified'] = True
            with self.subTest(fault=fault), self.assertRaises(ValidationError): self.read()
        self.data = original; (self.root/'base_contact_fit.json').write_text('{}')
        with self.assertRaises(ValidationError): self.read()


if __name__ == '__main__': unittest.main()
