"""Check local engine and per-source Unreal animation permissions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.jobs.unreal_animation_authorization import POLICY, load_unreal_animation_authorization
from ucc.library.provenance import AssetPolicyError, LicensePolicy


class UnrealAnimationAuthorizationTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve()/'unit-authority.json'
        policy = LicensePolicy('UNIT', 'UNIT_ONLY', 'unit:sender', reviewed=True, no_ai=True,
                               can_use_unreal=True, local_preview_allowed=True)
        selected = RegisteredInputSelection('unit-project', 1, '1'*64, '2'*64, 'unit-clip',
                                            '3'*64, '4'*64, '5'*64)
        self.document = dict(schema_version=1, policy=POLICY, engine='unreal', selection=selected.to_dict(),
            permissions=[EngineInputPermission(role, digest*64, policy, False).to_dict()
                         for role, digest in (('master', '2'), ('expression_library', '6'), ('motion:unit', '7'))],
            purpose='UNIT private test', private_local_execution_confirmed=True)

    def load(self):
        self.path.write_text(json.dumps(self.document), encoding='utf-8')
        return load_unreal_animation_authorization(self.path)

    def test_exact_unreal_scope_preserves_private_use(self):
        result = self.load()
        self.assertEqual(result.selection.clip_id, 'unit-clip')
        self.assertTrue(all(row.policy.can_use_unreal and row.policy.no_ai for row in result.permissions))

    def test_ue_only_input_cannot_enter_blender_preparation(self):
        self.document['permissions'][2]['policy']['ue_only'] = True
        with self.assertRaisesRegex(ValidationError, 'Blender preparation'):
            self.load()

    def test_separate_engine_and_source_only_permissions_are_rejected(self):
        self.document['engine'] = 'unity'
        with self.assertRaises(ValidationError):
            self.load()
        self.document['engine'] = 'unreal'
        self.document['permissions'][2]['source_only'] = True
        with self.assertRaises(AssetPolicyError):
            self.load()
