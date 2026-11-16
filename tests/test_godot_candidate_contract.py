"""Contract/permission negatives; no generated model or engine claim."""
from dataclasses import replace
import json
import unittest

from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import (
    FILES, EngineInputPermission, GodotCandidateRequest, canonical_bytes,
)
from ucc.library.provenance import AssetPolicyError, LicensePolicy


class GodotCandidateContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = LicensePolicy('original-unit-test', 'Test logic only', 'unit-test://permission',
                                    reviewed=True, no_ai=True, can_use_non_unreal=True)
        self.permission = EngineInputPermission('master', 'a'*64, self.policy, source_only=False)
        self.request = GodotCandidateRequest('01234567-1234-4567-8901-0123456789ab', 'project', 2,
            'b'*64, 'a'*64, tuple((name, 'c'*64) for name in sorted(FILES)),
            (self.permission,), (('master', 'a'*64),))

    def test_roundtrip_binds_required_import_profile_and_retains_noai(self):
        raw = self.request.to_dict()
        loaded = GodotCandidateRequest.from_bytes(canonical_bytes(raw))
        self.assertEqual(loaded, self.request)
        self.assertEqual(loaded.sha256, self.request.sha256)
        self.assertTrue(raw['permissions'][0]['policy']['no_ai'])
        self.assertFalse(raw['permissions'][0]['policy']['ai_input_allowed'])
        self.assertFalse(raw['source_redistribution_authorized'])
        self.assertFalse(raw['cloud_transmission_authorized'])
        self.assertFalse(raw['engine_import_verified'])
        self.assertFalse(raw['import_profile']['optimizer_enabled'])

    def test_source_only_never_upgraded_even_with_engine_policy(self):
        with self.assertRaisesRegex(AssetPolicyError, 'Source-only'):
            replace(self.request, permissions=(replace(self.permission, source_only=True),))

    def test_preview_only_unreviewed_and_ue_only_policies_reject(self):
        for policy in [replace(self.policy, can_use_non_unreal=False, local_preview_allowed=True),
                       replace(self.policy, reviewed=False), replace(self.policy, ue_only=True)]:
            with self.subTest(policy=policy), self.assertRaises(AssetPolicyError):
                replace(self.request, permissions=(replace(self.permission, policy=policy),))

    def test_permission_coverage_and_source_content_must_be_exact(self):
        changes = [{'permissions': ()}, {'source_bindings': (('master', 'b'*64),)},
                   {'permissions': (self.permission, self.permission)},
                   {'source_bindings': (('master', 'a'*64), ('expression_library', 'd'*64))},
                   {'permissions': (replace(self.permission, source_sha256='d'*64),)}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                replace(self.request, **change)

    def test_profile_revision_and_file_set_cannot_be_downgraded(self):
        for change in [{'fps': 30}, {'fps': True}, {'frame_count': 24}, {'revision': True},
                       {'revision': -1}, {'files': self.request.files[:-1]},
                       {'files': self.request.files+(('../escape', 'a'*64),)},
                       {'job_id': '../../outside'}, {'master_sha256': 'A'*64}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                replace(self.request, **change)

    def test_required_settings_and_false_readiness_flags_reject_tampering(self):
        for field in ['engine_import_verified', 'source_redistribution_authorized',
                      'cloud_transmission_authorized', 'visual_quality_approved', 'import_profile']:
            raw = self.request.to_dict()
            raw[field] = True if field != 'import_profile' else {**raw[field], 'optimizer_enabled': True}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                GodotCandidateRequest.from_dict(raw)

    def test_malformed_duplicate_nonfinite_oversized_and_unknown_json_reject(self):
        raw = self.request.to_dict(); raw['unknown'] = 'field'
        cases = [b'{}', b'\xff', b' '*300000, canonical_bytes(raw),
                 canonical_bytes(self.request.to_dict()).replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                 canonical_bytes(self.request.to_dict()).replace(b'"revision":2', b'"revision":NaN')]
        for data in cases:
            with self.subTest(data=data[:35]), self.assertRaises(ValidationError):
                GodotCandidateRequest.from_bytes(data)

    def test_missing_complete_policy_fields_cannot_use_defaults(self):
        raw = self.request.to_dict(); del raw['permissions'][0]['policy']['no_ai']
        with self.assertRaises(ValidationError):
            GodotCandidateRequest.from_dict(raw)


if __name__ == '__main__':
    unittest.main()
