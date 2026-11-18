"""NONSHIPPING metadata only; never Action, renderer, rights or native evidence."""
from copy import deepcopy
from dataclasses import replace
from uuid import UUID
import unittest

from fixtures.target_action_contract import metadata_pair
from fixtures.sprite_render_logic import request as neutral_request
from ucc.core.body_sprites import BodySpriteRequest, BodySpriteWindow, body_sprite_sources
from ucc.core.errors import ValidationError
from ucc.core.expressions import ExpressionState
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.sprite_render import SpritePermission, SpriteSettings, SpriteRenderRequest
from ucc.core.target_action_format import canonical_bytes
from ucc.core.body_sprites import validate_recipe, validate_job, worker_bindings, POLICY, STAGE, VERIFY


from fixtures.body_sprite_contract import request

class BodySpriteContractTests(unittest.TestCase):
    def test_recipe_binds_two_new_actual_intake_identities_and_all_seven_worker_hashes(self):
        original = request()
        admission = {'source_sha256':original.target_binding.source.source_sha256,
                     'snapshot_sha256':original.target_binding.source.snapshot_sha256,
                     'worker_job_ids':[str(UUID(int=1001)),str(UUID(int=1002))],
                     'worker_records':[{'request_sha256':'a'*64,'result_sha256':'b'*64},
                                       {'request_sha256':'c'*64,'result_sha256':'d'*64}],
                     'original_motion_provenance':{'policy':'PINNED_ORIGINAL_MOTION_DECLARATION_V1',
                         'record_sha256':'e'*64,'record_policy_sha256':'f'*64,
                         'record_format':'LEGACY_NATIVE_SOURCE_REVIEW_V1','record_status':'MPFB_NATIVE_RUNTIME_SOURCE_V1',
                         'original_script_exit_success':None,
                         'catalog_policy_sha256':original.target_binding.source.catalog_policy_sha256,
                         'motion_role':'motion:unit-original','source_sha256':original.target_binding.source.source_sha256,
                         'snapshot_sha256':original.target_binding.source.snapshot_sha256,
                         'record_source_uri':'ucc-original-diagnostic://unit/original',
                         'catalog_source_uri':'ucc-original-diagnostic://unit/original','uri_aliases':[],
                         'origin_declaration_only':True,'sprite_rights_inferred':False}}
        recipe = {'schema_version':1,'policy':POLICY,'request':original.to_dict(),'source_admission':admission}
        self.assertEqual(validate_recipe(recipe),recipe)
        for fault in ('missing_admission','old_worker','same_record','shifted_snapshot'):
            changed = deepcopy(recipe)
            if fault == 'missing_admission': changed.pop('source_admission')
            elif fault == 'old_worker': changed['source_admission']['worker_job_ids'][0] = original.target_binding.producer.body_reopen_job_id
            elif fault == 'same_record': changed['source_admission']['worker_records'][1] = changed['source_admission']['worker_records'][0]
            else: changed['source_admission']['snapshot_sha256'] = 'e'*64
            with self.subTest(fault=fault), self.assertRaises(ValidationError): validate_recipe(changed)
        options = worker_bindings(original,'a'*64); self.assertEqual(len(options),7)
        validate_job(STAGE,'candidate.blend',options)
        validate_job(VERIFY,'candidate.blend',options|{'scene_sha256':'b'*64,'stage_sha256':'c'*64})
        for changed in (options|{'path':'elsewhere'}, {k:v for k,v in options.items() if k!='snapshot_sha256'}):
            with self.assertRaises(ValidationError): validate_job(STAGE,'candidate.blend',changed)
        with self.assertRaises(ValidationError): validate_job(VERIFY,'candidate.blend',options)

    def test_closed_roundtrip_preserves_complete_project_and_full_action_binding(self):
        original = request(); raw = original.to_dict(); before = deepcopy(raw)
        loaded = BodySpriteRequest.from_bytes(canonical_bytes(raw))
        self.assertEqual(loaded, original)
        self.assertEqual(loaded.project.animations, ('unit-asset#clip-0000', 'other-source#clip-0000'))
        self.assertEqual(loaded.project.parts, original.project.parts)
        self.assertEqual(loaded.project.expression, original.project.expression)
        self.assertEqual(loaded.target_binding, original.target_binding)
        self.assertEqual(raw, before)
        self.assertEqual(raw['full_clock']['source_first_frame'], 2)
        self.assertEqual(raw['full_clock']['target_last_frame'], 300)

    def test_request_retains_only_immutable_snapshot_bytes(self):
        original = request(); raw = original.to_dict(); loaded = BodySpriteRequest.from_dict(raw)
        digest = loaded.sha256
        raw['project_snapshot']['animations'].clear()
        raw['project_snapshot']['expression']['parameters']['mouth_open'] = 0
        self.assertEqual(loaded.sha256, digest)
        self.assertEqual(len(loaded.project.animations), 2)
        with self.assertRaises(ValidationError):
            replace(original, project_snapshot_json=original.project.to_dict())

    def test_absolute_selected_window_keeps_exact_source_offset_and_sample_timing(self):
        for first, last in ((1, 1), (1, 32), (149, 152), (269, 300), (300, 300)):
            window = BodySpriteWindow(first, last); raw = window.to_dict()
            self.assertEqual(window.target_frames, tuple(range(first, last+1)))
            self.assertEqual(window.source_frames, tuple(range(first+1, last+2)))
            self.assertEqual(raw['sample_span_s'], (last-first)/30)
            self.assertEqual(raw['nominal_coverage_s'], (last-first+1)/30)
            self.assertEqual(BodySpriteWindow.from_dict(raw), window)

    def test_window_rejects_outside_sparse_reversed_noninteger_or_excessive_samples(self):
        for first, last in ((0, 1), (1, 301), (9, 8), (1, 33), (True, 2), (1, 2.0)):
            with self.subTest(bounds=(first, last)), self.assertRaises(ValidationError):
                BodySpriteWindow(first, last)
        raw = BodySpriteWindow(1, 3).to_dict(); raw['target_frames'] = [1, 3]
        with self.assertRaises(ValidationError): BodySpriteWindow.from_dict(raw)

    def test_selected_clock_fields_cannot_be_independently_retimed(self):
        original = BodySpriteWindow(299, 300)
        for key, value in (('source_first_frame', 299), ('source_last_frame', 300),
                           ('fps_numerator', 24), ('fps_denominator', 2),
                           ('sample_count', 1), ('sample_span_s', 1.), ('nominal_coverage_s', 0.)):
            raw = original.to_dict(); raw[key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError): BodySpriteWindow.from_dict(raw)

    def test_camera_and_frame_budget_derive_exact_image_count(self):
        maximum = request(window=BodySpriteWindow(269, 300), settings=SpriteSettings(256, 8, -45, 15))
        self.assertEqual(maximum.image_count, 256)
        self.assertEqual(maximum.settings.angles(), (315, 0, 45, 90, 135, 180, 225, 270))
        one = request(window=BodySpriteWindow(300, 300)); self.assertEqual(one.image_count, 4)
        self.assertEqual(one.to_dict()['window']['sample_span_s'], 0.)

    def test_each_rendered_source_needs_its_own_exact_sprite_permission(self):
        original = request(); names = set(dict(original.source_bindings))
        self.assertEqual(names, {'master', 'expression_library', 'motion:unit-asset#clip-0000',
                               'part:ucc-hand-v1-'+'d'*64+'-shorter'})
        for index in range(len(original.permissions)):
            with self.subTest(missing=original.permissions[index].asset_id), self.assertRaises(ValidationError):
                replace(original, permissions=original.permissions[:index]+original.permissions[index+1:])
        with self.assertRaises(ValidationError):
            replace(original, permissions=(original.permissions[0],)*len(original.permissions))
        changed = replace(original.permissions[0], source_sha256='e'*64)
        with self.assertRaises(ValidationError): replace(original, permissions=(changed, *original.permissions[1:]))

    def test_original_authored_declaration_alone_never_grants_sprite_rights(self):
        original = request()
        with self.assertRaises(ValidationError): replace(original, permissions=())
        for value in (False, 1, 'original'):
            with self.subTest(declaration=value), self.assertRaises(ValidationError):
                replace(original, original_authored_motion_confirmed=value)
        raw = original.to_dict(); raw['permissions'][0] = {
            'asset_id': original.permissions[0].asset_id, 'source_sha256': original.permissions[0].source_sha256,
            'reviewed': True, 'engine_export_allowed': True, 'local_preview_allowed': True}
        with self.assertRaises(ValidationError): BodySpriteRequest.from_dict(raw)

    def test_NoAI_private_source_and_redistribution_restrictions_stay_required(self):
        original = request()
        for key, value in (('reviewed', False), ('private_sprite_render_allowed', False),
                           ('no_ai', False), ('ue_only', True), ('redistribute_source_allowed', True)):
            raw = original.to_dict(); raw['permissions'][0][key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError): BodySpriteRequest.from_dict(raw)

    def test_temporary_matte_is_request_bound_and_does_not_adopt_a_saved_material(self):
        original = request(); changed = replace(original, temporary_matte=SkinMaterialSpec((.2, .4, .6), 1.))
        self.assertNotEqual(original.sha256, changed.sha256)
        self.assertEqual(original.project_snapshot_json, changed.project_snapshot_json)
        self.assertEqual(original.target_binding, changed.target_binding)
        self.assertFalse(changed.to_dict()['project_publication_authorized'])
        with self.assertRaises(ValidationError): replace(original, temporary_matte=SkinMaterialSpec((.2, .4, .6), .5))
        project = replace(original.project, appearance=(('ucc.body_material.v1', 'e'*64),))
        with self.assertRaises(ValidationError): replace(original, project_snapshot_json=canonical_bytes(project.to_dict()))

    def test_stale_project_master_expression_or_selected_reference_rejects(self):
        original = request()
        projects = (replace(original.project, revision=5),
                    replace(original.project, master_blend='master/versions/'+'f'*64+'.blend'),
                    replace(original.project, animations=('other-source#clip-0000',)),
                    replace(original.project, schema_version=2, expression=None))
        for project in projects:
            with self.subTest(project=project.to_dict()), self.assertRaises(ValidationError):
                replace(original, project_snapshot_json=canonical_bytes(project.to_dict()))
        expression = replace(original.project.expression, library_sha256='e'*64)
        project = replace(original.project, expression=expression)
        with self.assertRaises(ValidationError): replace(original, project_snapshot_json=canonical_bytes(project.to_dict()))

    def test_without_hand_is_supported_but_wrong_or_missing_hand_review_is_not(self):
        self.assertEqual(len(request(hand=False).permissions), 3)
        original = request(); part = original.project.parts[0]
        for changed in (replace(part, visible=False), replace(part, part_asset_id='unregistered-hand')):
            project = replace(original.project, parts=(changed,))
            with self.assertRaises(ValidationError): replace(original, project_snapshot_json=canonical_bytes(project.to_dict()))

    def test_closed_fields_hashes_flags_and_full_clock_reject_tampering(self):
        original = request()
        changes = {'schema_version': True, 'policy': 'neutral', 'project_snapshot_sha256': 'e'*64,
                   'target_binding_sha256': 'e'*64, 'image_count': 1, 'temporary_matte_sha256': 'e'*64,
                   'temporary_material_policy': 'SAVE_TO_MASTER', 'extra': 'path',
                   'private_sample_only': 1, 'source_material_slots_must_be_empty': False,
                   'project_publication_authorized': True, 'animation_clip_delivery_authorized': True,
                   'visual_quality_approved': True, 'source_redistribution_authorized': True,
                   'ai_input_authorized': True, 'sprite_redistribution_authorized': True}
        for key, value in changes.items():
            raw = original.to_dict(); raw[key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError): BodySpriteRequest.from_dict(raw)
        raw = original.to_dict(); raw['full_clock']['source_first_frame'] = 1
        with self.assertRaises(ValidationError): BodySpriteRequest.from_dict(raw)

    def test_request_hash_binds_window_camera_purpose_and_all_saved_intent(self):
        original = request()
        changed = (replace(original, window=BodySpriteWindow(150, 152)),
                   replace(original, settings=SpriteSettings(256, 8)),
                   replace(original, purpose='UNIT_ONLY second private sample'))
        self.assertTrue(all(value.sha256 != original.sha256 for value in changed))
        raw = original.to_dict(); raw['project_snapshot']['animations'].pop()
        with self.assertRaises(ValidationError): BodySpriteRequest.from_dict(raw)

    def test_existing_neutral_contract_and_body_contract_are_not_interchangeable(self):
        with self.assertRaises(ValidationError): SpriteRenderRequest.from_dict(request().to_dict())
        with self.assertRaises(ValidationError): BodySpriteRequest.from_dict(neutral_request().to_dict())

    def test_noncanonical_duplicate_oversized_and_nonfinite_bytes_reject(self):
        payload = canonical_bytes(request().to_dict())
        for invalid in (payload+b'\n', payload.replace(b'{', b'{"policy":"extra",', 1),
                        b'{}'*(256*1024), payload.replace(b'0.56', b'NaN', 1)):
            with self.subTest(bytes=len(invalid)), self.assertRaises(ValidationError):
                BodySpriteRequest.from_bytes(invalid)


if __name__ == '__main__': unittest.main()
