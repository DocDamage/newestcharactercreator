"""Static engine boundaries reject forged approvals and rights; scalar fixtures only."""
from copy import deepcopy
from dataclasses import replace
import unittest

from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import UnrealExportRequest, READINESS_FLAGS, MAX_REQUEST_BYTES
from ucc.export.unreal_blender_recipe import recipe, validate_recipe, validate_job, STAGE, VERIFY, FILES
from ucc.library.provenance import AssetPolicyError
from fixtures.unreal_contract_logic import request


class UnrealContractTests(unittest.TestCase):
    def test_roundtrip_binds_all_selected_tools_and_each_source(self):
        original = request()
        self.assertEqual(UnrealExportRequest.from_bytes(canonical_bytes(original.to_dict())), original)
        for field in ('unreal_executable_sha256', 'unreal_build_version_sha256', 'toolchain_sha256'):
            self.assertNotEqual(replace(original, **{field: '0'*64}).sha256, original.sha256)
        self.assertNotEqual(replace(original, revision=2).sha256, original.sha256)

    def test_readiness_profile_and_bool_number_forgery_reject(self):
        changes = [(key, True) for key in READINESS_FLAGS]
        changes += [('schema_version', True), ('revision', True), ('native_lod', False),
            ('skin_weight_bits', 8), ('engine_version', 'other'), ('profile', 'other'),
            ('animation_clips', True), ('platform', 'LINUX'), ('extra', 1)]
        for key, value in changes:
            raw = request().to_dict(); raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                UnrealExportRequest.from_dict(raw)

    def test_unreal_permission_is_distinct_from_preview_or_non_unreal_rights(self):
        original = request(); permission = original.permissions[0]
        for flags in ({'reviewed': False}, {'can_use_unreal': False, 'can_use_non_unreal': True},
            {'can_use_unreal': False, 'local_preview_allowed': True}, {'no_ai': False},
            {'ai_input_allowed': True}, {'redistribute_source_allowed': True}):
            bad = replace(permission, policy=replace(permission.policy, **flags))
            with self.subTest(flags=flags), self.assertRaises((ValidationError, AssetPolicyError)):
                replace(original, permissions=(bad, *original.permissions[1:]))
        with self.assertRaises(AssetPolicyError):
            replace(original, permissions=(replace(permission, source_only=True), *original.permissions[1:]))
        # A reviewed UE-only right is valid for this target; it never changes
        # NoAI or original-source redistribution restrictions.
        allowed = replace(permission, policy=replace(permission.policy, ue_only=True))
        self.assertIsInstance(replace(original, permissions=(allowed, *original.permissions[1:])), UnrealExportRequest)

    def test_duplicate_rebound_missing_and_unknown_sources_reject(self):
        original = request(); permission = original.permissions[0]
        for changes in ({'permissions': original.permissions[:-1]},
            {'permissions': (permission, permission, *original.permissions[2:])},
            {'source_bindings': (original.source_bindings[0],)*4},
            {'permissions': (replace(permission, source_sha256='0'*64), *original.permissions[1:])},
            {'job_id': original.job_id.upper()}, {'project_id': 'bad\nidentity'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(original, **changes)

    def test_untrusted_json_rejects_duplicates_nonfinite_and_oversize(self):
        for data in (b'{"job_id":"a","job_id":"b"}', b'{"revision":NaN}',
                     b'\xff', b' '*(MAX_REQUEST_BYTES+1)):
            with self.assertRaises(ValidationError): UnrealExportRequest.from_bytes(data)
        raw = request().to_dict(); raw['permissions'][0]['policy']['extra'] = True
        with self.assertRaises(ValidationError): UnrealExportRequest.from_dict(raw)

    def test_recipe_and_verify_job_bind_every_output_without_readiness(self):
        original = request(); spec = SkinMaterialSpec((.4, .3, .2), .6)
        raw = recipe(original, spec)
        self.assertEqual(validate_recipe(raw), (original, spec))
        altered = deepcopy(raw); altered['material_spec']['metallic'] = 1
        with self.assertRaises(ValidationError): validate_recipe(altered)
        options = {'master_sha256': 'a'*64, 'recipe_sha256': 'b'*64}
        validate_job(STAGE, 'candidate.blend', options)
        with self.assertRaises(ValidationError): validate_job(VERIFY, 'candidate.blend', options)
        options.update({name.replace('.', '_')+'_sha256': 'c'*64 for name in FILES})
        validate_job(VERIFY, 'candidate.blend', options)
        with self.assertRaises(ValidationError): validate_job(VERIFY, '../candidate.blend', options)
