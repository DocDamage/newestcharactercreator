"""Closed engine-specific authorization tests using invented metadata."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.jobs.unity_animation_authorization import POLICY, load_unity_animation_authorization
from ucc.library.provenance import AssetPolicyError, LicensePolicy


class UnityAnimationAuthorizationTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve()/'authority.json'
        policy = LicensePolicy('UNIT', 'UNIT_ONLY', 'unit:sender', reviewed=True, no_ai=True,
                               can_use_non_unreal=True, local_preview_allowed=True)
        selection = RegisteredInputSelection('unit-project', 1, '1'*64, '2'*64, 'unit-clip',
                                             '3'*64, '4'*64, '5'*64)
        rows = [EngineInputPermission(role, digest*64, policy, False).to_dict() for role, digest in
                [('master', '2'), ('expression_library', '6'), ('motion:unit', '7')]]
        self.document = dict(schema_version=1, policy=POLICY, engine='unity',
            selection=selection.to_dict(), permissions=rows, purpose='UNIT private test',
            private_local_execution_confirmed=True)

    def load(self):
        self.path.write_text(json.dumps(self.document), encoding='utf-8')
        return load_unity_animation_authorization(self.path)

    def test_exact_unity_selection_is_accepted(self):
        result = self.load()
        self.assertEqual(result.selection.binding_sha256, '3'*64)
        self.assertEqual(tuple(row.asset_id for row in result.permissions),
                         ('master', 'expression_library', 'motion:unit'))

    def test_godot_scope_is_rejected_even_with_cross_engine_policy_flags(self):
        self.document['engine'] = 'godot'
        with self.assertRaises(ValidationError):
            self.load()

    def test_missing_local_confirmation_is_rejected(self):
        self.document.pop('private_local_execution_confirmed')
        with self.assertRaises(ValidationError):
            self.load()

    def test_duplicate_or_source_only_permissions_reject(self):
        self.document['permissions'][1]['source_only'] = True
        with self.assertRaises(AssetPolicyError):
            self.load()
        self.document['permissions'][1] = self.document['permissions'][0]
        with self.assertRaises(ValidationError):
            self.load()

    def test_source_redistribution_permission_is_outside_private_scope(self):
        self.document['permissions'][0]['policy']['redistribute_source_allowed'] = True
        with self.assertRaises(ValidationError):
            self.load()
