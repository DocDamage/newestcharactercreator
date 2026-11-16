"""Synthetic contract guards only; no Blender, geometry or licensing proof."""
from copy import deepcopy
from dataclasses import replace
import unittest

from blender_bridge.godot_policy import checked_recipe
from ucc.core.errors import ValidationError
from ucc.core.expression_clip import build_expression_clip
from ucc.core.expressions import TARGETS
from ucc.export.godot_blender_recipe import build_recipe, validate_recipe, OUTPUTS
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.jobs.protocol import JobRequest
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from test_expression_contracts import source_project, prepared


class GodotBlenderRecipeTests(unittest.TestCase):
    def setUp(self):
        self.project = prepared(source_project(hand=True), hand=True)
        self.clip = build_expression_clip(self.project, 'e'*64)
        self.sources = {'master': 'e'*64, 'expression_library': 'd'*64, 'motion:unit': 'f'*64,
                        'part:'+self.project.parts[0].part_asset_id: 'c'*64}
        self.policy = LicensePolicy('unit-only', 'Contract test only', 'unit-test://no-model',
                                   reviewed=True, no_ai=True, can_use_non_unreal=True)
        self.permissions = tuple(EngineInputPermission(name, sha, self.policy, source_only=False)
                                 for name, sha in self.sources.items())
        self.raw = self.build()
        self.options = {'master_sha256': 'e'*64, 'target_motion_sha256': 'f'*64,
            'export_recipe_sha256': 'a'*64, 'clip_sha256': self.raw['expression_clip_sha256'],
            **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}

    def build(self, **changes):
        kwargs = dict(project=self.project, project_file_sha256='b'*64, master_sha256='e'*64,
            motion_asset_id='motion:unit', source_bindings=self.sources, permissions=self.permissions, clip=self.clip)
        return build_recipe(**{**kwargs, **changes})

    def test_independent_recipe_validators_agree(self):
        self.assertEqual(validate_recipe(self.raw, self.project, self.clip), self.raw)
        self.assertEqual(checked_recipe(self.raw, self.clip, self.options), self.raw)

    def test_closed_recipe_rejects_source_role_timeline_rights_and_identity_changes(self):
        edits = [lambda r:r.update(extra=True), lambda r:r.update(schema_version=True),
            lambda r:r.update(engine_import_verified=True), lambda r:r.update(cloud_transmission_authorized=True),
            lambda r:r.update(source_role='ALL_SOURCE_GEOMETRY'), lambda r:r['timeline'].update(fps=30),
            lambda r:r['project'].update(revision=True), lambda r:r['source_bindings'].update(master='a'*64),
            lambda r:r['permissions'][0].update(source_only=True), lambda r:r['permissions'][0]['policy'].update(ue_only=True)]
        for edit in edits:
            raw = deepcopy(self.raw); edit(raw)
            with self.subTest(edit=edit):
                with self.assertRaises((ValidationError, AssetPolicyError)): validate_recipe(raw, self.project, self.clip)
                with self.assertRaises(ValueError): checked_recipe(raw, self.clip, self.options)

    def test_source_only_and_permission_coverage_cannot_be_upgraded(self):
        for permissions in (self.permissions[:-1], self.permissions+(self.permissions[0],),
                (replace(self.permissions[0], source_only=True),)+self.permissions[1:],
                (replace(self.permissions[0], source_sha256='a'*64),)+self.permissions[1:]):
            with self.assertRaises((ValidationError, AssetPolicyError)): self.build(permissions=permissions)
        with self.assertRaises(ValidationError):
            self.build(project=replace(self.project, parts=(replace(self.project.parts[0], visible=False),)))

    def test_every_job_binding_is_required_and_pinned(self):
        for operation in ('stage_mpfb_godot_candidate', 'verify_mpfb_godot_candidate'):
            options = dict(self.options)
            if operation.startswith('verify'): options.update({field:'c'*64 for field in OUTPUTS.values()})
            JobRequest.new(operation, input_project='candidate.blend', options=options)
            for name in options:
                broken = dict(options); broken.pop(name)
                with self.assertRaises(ValidationError): JobRequest.new(operation, input_project='candidate.blend', options=broken)
            with self.assertRaises(ValidationError): JobRequest.new(operation, input_project='../master.blend', options=options)

    def test_published_job_schema_matches_both_new_closed_requests(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        for operation in ('stage_mpfb_godot_candidate', 'verify_mpfb_godot_candidate'):
            options = dict(self.options)
            if operation.startswith('verify'): options.update({field:'c'*64 for field in OUTPUTS.values()})
            raw = JobRequest.new(operation, input_project='candidate.blend', options=options).as_dict()
            validator.validate(raw)
            for field in options:
                broken = deepcopy(raw); broken['options'].pop(field)
                self.assertTrue(list(validator.iter_errors(broken)))


if __name__ == '__main__': unittest.main()
