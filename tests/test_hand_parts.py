"""Closed-contract tests only; fixtures here do not prove real hand geometry."""
from copy import deepcopy
from dataclasses import replace
import unittest

from ucc.core.errors import CompatibilityError, ValidationError
from ucc.core.hand_parts import (
    build_hand_library_recipe, validate_hand_library_recipe, build_hand_manifest,
    validate_hand_manifest, canonical_digest, ensure_source_intent, hand_asset_id,
    hand_selection,
)
from ucc.core.models import CharacterProject, PartInstance


class HandContractTests(unittest.TestCase):
    def setUp(self):
        self.project = replace(CharacterProject.new('Contract fixture, no geometry'),
                               master_blend='master/versions/'+('a'*64)+'.blend',
                               geometry_state='generated_unverified')
        self.recipe = build_hand_library_recipe(self.project, 'a'*64)
        self.manifest = build_hand_manifest(self.recipe, {
            'shorter': {'sha256': 'b'*64, 'observation_sha256': 'c'*64},
            'longer': {'sha256': 'd'*64, 'observation_sha256': 'e'*64}})

    def test_canonical_closed_roundtrip_retains_rights(self):
        self.assertEqual(validate_hand_library_recipe(self.recipe), self.recipe)
        self.assertEqual(validate_hand_manifest(self.manifest), self.manifest)
        self.assertEqual(ensure_source_intent(self.project, self.recipe), self.recipe)
        self.assertTrue(self.manifest['rights']['no_ai'])
        self.assertFalse(self.manifest['rights']['engine_export_authorized'])
        self.assertFalse(self.manifest['rights']['source_redistribution_authorized'])

    def test_saved_selection_uses_manifest_identity_and_has_no_geometry_claim(self):
        digest = canonical_digest(self.manifest)
        self.assertEqual(hand_selection(self.project, digest), 'neutral')
        for variant in ('shorter', 'longer'):
            selected = replace(self.project, parts=(PartInstance('part-1', hand_asset_id(digest, variant), 'hand.L'),))
            self.assertEqual(hand_selection(selected, digest), variant)
            self.assertEqual(selected.parts[0].status, 'proposed')
            with self.assertRaises(CompatibilityError):
                hand_selection(selected, 'f'*64)
        hidden = replace(selected, parts=(replace(selected.parts[0], visible=False),))
        with self.assertRaises(CompatibilityError):
            hand_selection(hidden, digest)

    def test_recipe_rejects_missing_extra_or_rebound_fields(self):
        mutations = [
            lambda r:r.update(schema_version=True), lambda r:r.update(strength=True),
            lambda r:r.update(strength=.5), lambda r:r.update(slot='hand.R'),
            lambda r:r.update(root_bone='hand.L'), lambda r:r.update(extra='ignored'),
            lambda r:r.pop('source'), lambda r:r['bindings'].update(base_sha256='f'*64),
            lambda r:r['bindings'].update(master_sha256='../candidate'),
            lambda r:r['variants'][0].update(asset_file='../private.blend'),
            lambda r:r['variants'].reverse(), lambda r:r['source'].update(body_parameters=[]),
            lambda r:r['source']['body_parameters'].update(unsupported=.5),
            lambda r:r['source']['facial_parameters'].update(unknown=.5),
        ]
        for mutate in mutations:
            value=deepcopy(self.recipe);mutate(value)
            with self.subTest(recipe=value), self.assertRaises(ValidationError):
                validate_hand_library_recipe(value)

    def test_numeric_and_source_boundaries(self):
        for invalid in (True, float('nan'), float('inf'), -1., 10**400):
            value=deepcopy(self.recipe);value['source']['body_parameters']['weight']=invalid
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                validate_hand_library_recipe(value)
        with self.assertRaises(CompatibilityError):
            ensure_source_intent(replace(self.project, parameters=(('height', .4), ('muscle', .5), ('weight', .5))), self.recipe)
        with self.assertRaises(CompatibilityError):
            ensure_source_intent(replace(self.project, schema_version=2, facial_parameters=(('nose_width', .7),)), self.recipe)
        with self.assertRaises(CompatibilityError):
            ensure_source_intent(replace(self.project, project_id='another-project'), self.recipe)
        for project in (CharacterProject.new('No source'),
                        replace(self.project, parts=(PartInstance('p', 'a', 'hand.L'),)),
                        replace(self.project, animations=('unverified-action',))):
            with self.assertRaises(CompatibilityError):
                build_hand_library_recipe(project, 'a'*64)

    def test_manifest_cannot_grant_permissions_or_change_observation_shape(self):
        mutations = [lambda r:r['rights'].update(no_ai=False),
                     lambda r:r['rights'].update(ai_input_allowed=True),
                     lambda r:r['rights'].update(engine_export_authorized=True),
                     lambda r:r['rights'].update(source_redistribution_authorized=True),
                     lambda r:r['rights'].update(local_project_preview=1),
                     lambda r:r['assets']['shorter'].pop('observation_sha256'),
                     lambda r:r['assets']['shorter'].update(extra='ignored'),
                     lambda r:r['assets'].update(unverified={'sha256':'f'*64}),
                     lambda r:r.update(schema_version=True)]
        for mutate in mutations:
            value=deepcopy(self.manifest);mutate(value)
            with self.subTest(manifest=value), self.assertRaises(ValidationError):
                validate_hand_manifest(value)
        for digest in (None, 'A'*64, 'a'*63, '../part'):
            with self.assertRaises(ValidationError):
                hand_asset_id(digest, 'shorter')
        for variant in (None, True, 'neutral', 'right', []):
            with self.assertRaises(ValidationError):
                hand_asset_id('a'*64, variant)

    def test_independent_worker_policy_agrees_and_rejects_rebinding(self):
        from blender_bridge.hand_policy import validate_recipe, validate_manifest
        self.assertEqual(validate_recipe(self.recipe), self.recipe)
        self.assertEqual(validate_manifest(self.manifest), self.manifest)
        for field, value in [('strength', .5), ('schema_version', True), ('slot', 'hand.R')]:
            raw=deepcopy(self.recipe);raw[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_recipe(raw)
        for value in (True, float('nan'), float('inf'), 10**400):
            raw=deepcopy(self.recipe);raw['source']['body_parameters']['height']=value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_recipe(raw)
        raw=deepcopy(self.manifest);raw['rights']['no_ai']=False
        with self.assertRaises(ValueError):
            validate_manifest(raw)

    def test_worker_protocol_rejects_partial_substituted_or_redirected_inputs(self):
        from ucc.core.hand_parts import TARGETS, METADATA_SHA256
        from ucc.jobs.protocol import JobRequest
        for operation in ('build_mpfb_hand_assets', 'verify_mpfb_hand_assets'):
            options = {'master_sha256': 'a'*64, 'recipe_sha256': 'b'*64,
                       'metadata_sha256': METADATA_SHA256,
                       **{t.variant+'_target_sha256': t.sha256 for t in TARGETS}}
            if operation.startswith('verify'):
                options.update(shorter_asset_sha256='c'*64, longer_asset_sha256='d'*64,
                               assets_report_sha256='e'*64)
            self.assertEqual(JobRequest.new(operation, input_project='candidate.blend', options=options).options, options)
            for field in options:
                broken=dict(options);del broken[field]
                with self.subTest(operation=operation, missing=field), self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=broken)
            for broken in (dict(options, extra='f'*64), dict(options, metadata_sha256='f'*64),
                           dict(options, shorter_target_sha256='f'*64), dict(options, recipe_sha256=True)):
                with self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=broken)
            with self.assertRaises(ValidationError):
                JobRequest.new(operation, input_project='other.blend', options=options)

    def test_saved_hand_acceptance_keeps_master_and_parts_in_one_history_step(self):
        from ucc.core.commands import CharacterSession
        identity=canonical_digest(self.manifest);session=CharacterSession(self.project)
        part=PartInstance('part-1',hand_asset_id(identity,'shorter'),'hand.L')
        saved=replace(self.project,parts=(part,),revision=self.project.revision+1,
                      master_blend='master/versions/'+('f'*64)+'.blend')
        session.accept_saved_part_master(saved,manifest_sha256=identity)
        self.assertEqual(session.project,saved)
        previous=session.undo()
        self.assertEqual(previous.parts,())
        self.assertEqual(previous.master_blend,self.project.master_blend)
        restored=session.redo()
        self.assertEqual(restored.parts,saved.parts)
        self.assertEqual(restored.master_blend,saved.master_blend)
        self.assertGreater(restored.revision,saved.revision)
        self.assertFalse(session.can_redo)

    def test_saved_hand_acceptance_rejects_unrelated_intent_and_false_status(self):
        from ucc.core.commands import CharacterSession
        identity=canonical_digest(self.manifest)
        part=PartInstance('part-1',hand_asset_id(identity,'shorter'),'hand.L')
        saved=replace(self.project,parts=(part,),revision=self.project.revision+1,
                      master_blend='master/versions/'+('f'*64)+'.blend')
        for changed in (replace(saved,name='unrelated edit'),replace(saved,revision=saved.revision+1),
                        replace(saved,parts=()),replace(saved,geometry_state='validated',
                        parts=(replace(part,status='geometry_validated'),))):
            session=CharacterSession(self.project)
            with self.subTest(changed=changed),self.assertRaises(ValidationError):
                session.accept_saved_part_master(changed,manifest_sha256=identity)
            self.assertEqual(session.project,self.project)
            self.assertFalse(session.can_undo)


if __name__ == '__main__':
    unittest.main()
