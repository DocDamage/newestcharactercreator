"""Pure candidate-contract checks; none establish usable motion or permission."""
import ast
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import unittest

from fixtures.authored_idle_contract import (
    inspection, metadata, request, saved_project, synthetic_mpfb_axes, with_project,
)
from ucc.core.authored_idle import (
    AuthoredIdleInspectionRequest, AuthoredIdleRequest, IdleAuthoringPermission,
    baseline_spec, clock_spec, consumed_sources, periodic_spec, saved_authoring_sources,
)
from ucc.core.errors import ValidationError
from ucc.core.sprite_render import SpritePermission
from ucc.core.target_action_format import CLOCK, canonical_bytes


class AuthoredIdleContractTests(unittest.TestCase):
    def test_anatomical_forward_is_anterior_not_backward_for_public_mpfb_convention(self):
        points = synthetic_mpfb_axes()
        right = tuple(r-l for r,l in zip(points['right_shoulder'], points['left_shoulder']))
        length = math.sqrt(sum(v*v for v in right))
        right = tuple(v/length for v in right)
        up = points['up']
        policy = baseline_spec()['forward_definition']
        operands = {'RIGHT_CROSS_UP': (right, up), 'UP_CROSS_RIGHT': (up, right)}
        a,b = operands[policy]
        forward = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
        self.assertGreater(sum(a*b for a,b in zip(forward, points['anterior'])), .999,
            'Positive elbow/arm forward intent must face MPFB anterior (-Y), not its back (+Y)')

    def test_inspection_roundtrip_needs_no_invented_target_or_anatomical_digest(self):
        candidate = inspection()
        raw = candidate.to_dict()
        self.assertNotIn('target', raw)
        self.assertNotIn('anatomical_frame_sha256', raw)
        self.assertEqual(AuthoredIdleInspectionRequest.from_bytes(canonical_bytes(raw)), candidate)
        self.assertEqual(candidate.sha256, sha256(canonical_bytes(raw)).hexdigest())
        self.assertEqual(candidate.project.animations, ('never-read-synthetic-source#clip-0000',))
        self.assertFalse(any(role.startswith('motion:') for role in raw['consumed_sources']))
        self.assertEqual(raw['inspection_scope'], 'NEUTRAL_REST_ANATOMY_NO_ACTION_EVALUATION_V1')

    def test_phase_boundary_is_closed_and_inspection_cannot_author_or_claim_measurement(self):
        for key in ('target', 'anatomical_frame_sha256', 'baseline', 'periodic_motion'):
            raw = inspection().to_dict(); raw[key] = request().to_dict().get(key, {})
            with self.subTest(key=key), self.assertRaises(ValidationError):
                AuthoredIdleInspectionRequest.from_dict(raw)
        for key in ('measurement_verified', 'authoring_execution_authorized',
                    'animation_sampling_authorized', 'existing_motion_read_authorized',
                    'native_authoring_verified', 'usable_action_approved'):
            raw = inspection().to_dict(); raw[key] = True
            with self.subTest(key=key), self.assertRaises(ValidationError):
                AuthoredIdleInspectionRequest.from_dict(raw)
        with self.assertRaises(ValidationError):
            AuthoredIdleRequest.from_dict(inspection().to_dict())
        with self.assertRaises(ValidationError):
            AuthoredIdleInspectionRequest.from_dict(request().to_dict())

    def test_inspection_and_measured_request_share_exact_source_permissions(self):
        for hand, expression in ((True, True), (False, True), (False, False)):
            first = inspection(hand=hand, expression=expression)
            later = request(hand=hand, expression=expression)
            self.assertEqual(saved_authoring_sources(first.project),
                consumed_sources(later.project, later.target))
            self.assertEqual(first.permissions, later.permissions)
            derived = AuthoredIdleRequest(later.job_id, first.project_snapshot_json,
                later.target, later.anatomical_frame_sha256, first.permissions,
                first.purpose, first.original_procedural_recipe_declared,
                first.private_authored_output_preview_confirmed)
            self.assertEqual(derived.project_snapshot_json, first.project_snapshot_json)
            self.assertEqual(derived.permissions, first.permissions)
            self.assertNotEqual(derived.sha256, first.sha256)

    def test_inspection_requires_every_authoring_source_and_both_explicit_consents(self):
        candidate = inspection()
        first = candidate.permissions[0]
        for permissions in (candidate.permissions[:-1], tuple(reversed(candidate.permissions)),
                (first, first, candidate.permissions[-1]),
                (replace(first, source_sha256='9'*64), *candidate.permissions[1:])):
            with self.subTest(permissions=len(permissions)), self.assertRaises(ValidationError):
                replace(candidate, permissions=permissions)
        for field in ('original_procedural_recipe_declared', 'private_authored_output_preview_confirmed'):
            for value in (False, 1):
                with self.subTest(field=field), self.assertRaises(ValidationError):
                    replace(candidate, **{field:value})
        sprite = SpritePermission(first.asset_id, first.source_sha256,
            'SYNTHETIC_SPRITE_NOT_AUTHORING', True, True)
        with self.assertRaises(ValidationError):
            replace(candidate, permissions=(sprite, *candidate.permissions[1:]))

    def test_inspection_requires_canonical_complete_snapshot_and_exact_derived_source_set(self):
        candidate = inspection()
        with self.assertRaises(ValidationError):
            replace(candidate, project_snapshot_json=candidate.project_snapshot_json+b'\n')
        raw = candidate.to_dict(); raw['project_snapshot_sha256'] = '0'*64
        with self.assertRaises(ValidationError): AuthoredIdleInspectionRequest.from_dict(raw)
        raw = candidate.to_dict(); raw['consumed_sources']['motion:forbidden'] = '0'*64
        with self.assertRaises(ValidationError): AuthoredIdleInspectionRequest.from_dict(raw)
        raw = candidate.to_dict(); raw['policy'] = request().to_dict()['policy']
        with self.assertRaises(ValidationError): AuthoredIdleInspectionRequest.from_dict(raw)
        changed = replace(candidate.project, animations=('second-preserved-reference#clip-0000',))
        changed_request = replace(candidate, project_snapshot_json=canonical_bytes(changed.to_dict()))
        self.assertNotEqual(changed_request.sha256, candidate.sha256)
        self.assertEqual(changed_request.permissions, candidate.permissions)

    def test_source_collection_rejects_unprepared_master_appearance_or_unadmitted_part(self):
        project = saved_project()
        for invalid in (replace(project, master_blend='master/other.blend'),
                        replace(project, master_blend='master/versions/'+'A'*64+'.blend'),
                        replace(project, appearance=(('skin', 'materials/skin.json'),)),
                        replace(project, parts=(replace(project.parts[0], visible=False),))):
            with self.subTest(master=invalid.master_blend), self.assertRaises(ValidationError):
                saved_authoring_sources(invalid)
            with self.assertRaises(ValidationError):
                replace(inspection(), project_snapshot_json=canonical_bytes(invalid.to_dict()))
        ungenerated = replace(saved_project(hand=False, expression=False),
                              master_blend=None, geometry_state='not_generated')
        with self.assertRaises(ValidationError): saved_authoring_sources(ungenerated)

    def test_canonical_roundtrip_and_actual_public_digest(self):
        candidate = request()
        payload = canonical_bytes(candidate.to_dict())
        self.assertEqual(AuthoredIdleRequest.from_bytes(payload), candidate)
        self.assertEqual(candidate.sha256, sha256(payload).hexdigest())
        self.assertNotEqual(candidate.sha256, sha256(payload+b'\n').hexdigest())

    def test_complete_snapshot_keeps_but_never_consumes_motion_references(self):
        candidate = request()
        self.assertEqual(candidate.project.animations, ('never-read-synthetic-source#clip-0000',))
        sources = candidate.to_dict()['consumed_sources']
        self.assertEqual(len(sources), 3)
        self.assertFalse(any(name.startswith('motion:') for name in sources))
        self.assertFalse(candidate.to_dict()['existing_motion_read_authorized'])
        self.assertFalse(candidate.to_dict()['existing_motion_derivation_authorized'])

    def test_permission_set_covers_optional_hand_and_expression_individually(self):
        for hand, expression, count in ((True, True, 3), (False, True, 2), (False, False, 1)):
            with self.subTest(hand=hand, expression=expression):
                candidate = request(hand=hand, expression=expression)
                self.assertEqual(len(candidate.permissions), count)
                self.assertEqual(dict(consumed_sources(candidate.project, candidate.target)),
                    {p.asset_id:p.source_sha256 for p in candidate.permissions})

    def test_missing_duplicate_extra_reordered_and_wrong_source_grants_reject(self):
        candidate = request()
        first = candidate.permissions[0]
        invalid = (candidate.permissions[:-1],
            (first, first, candidate.permissions[-1]),
            candidate.permissions+(replace(first, asset_id='motion:not-an-input'),),
            tuple(reversed(candidate.permissions)),
            (replace(first, source_sha256='9'*64), *candidate.permissions[1:]))
        for permissions in invalid:
            with self.subTest(case=len(permissions)):
                with self.assertRaises(ValidationError):
                    replace(candidate, permissions=permissions)

    def test_sprite_grant_is_not_an_authoring_grant(self):
        candidate = request(hand=False, expression=False)
        permission = candidate.permissions[0]
        sprite = SpritePermission(permission.asset_id, permission.source_sha256,
            'SYNTHETIC_SPRITE_ONLY_NOT_AUTHORING', True, True)
        with self.assertRaises(ValidationError):
            replace(candidate, permissions=(sprite,))

    def test_per_use_confirmation_is_exact_true(self):
        permission = request().permissions[0]
        for value in (False, 1, 'true', None):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    replace(permission, authoring_and_derived_rig_confirmed=value)

    def test_recipe_and_output_declarations_are_separate_required_consents(self):
        candidate = request()
        for field in ('original_procedural_recipe_declared', 'private_authored_output_preview_confirmed'):
            for value in (False, 1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        replace(candidate, **{field:value})

    def test_permissions_have_no_inferred_follow_on_rights(self):
        raw = request().permissions[0].to_dict()
        self.assertTrue(raw['no_ai'])
        self.assertTrue(raw['private_local_only'])
        for field in ('sprite_rights_inferred','engine_rights_inferred','redistribution_rights_inferred'):
            forged = dict(raw, **{field:True})
            with self.subTest(field=field), self.assertRaises(ValidationError):
                IdleAuthoringPermission.from_dict(forged)

    def test_clock_distinguishes_300_sample_cycle_from_299_intervals(self):
        clock = clock_spec()
        self.assertEqual(clock['stored_clock'], dict(CLOCK))
        self.assertEqual(clock['stored_clock']['playback_policy'], 'ONCE_HOLD_LAST')
        self.assertEqual((clock['stored_clock']['source_first_frame'],
                          clock['stored_clock']['source_last_frame']), (2, 301))
        self.assertEqual(clock['sample_span_numerator_s']/clock['sample_span_denominator_s'], 299/30)
        self.assertEqual(clock['nominal_coverage_numerator_s']/clock['nominal_coverage_denominator_s'], 10)
        self.assertFalse(clock['duplicate_terminal_sample'])
        self.assertFalse(clock['virtual_seam_is_stored_sample'])

    def test_synthetic_phase_wrap_matches_value_and_derivative_without_duplicate(self):
        # Scalar sine only, not any rig pose or geometry; tests declared math.
        omega = 2*math.pi/10
        samples = [math.sin(2*math.pi*k/300) for k in range(300)]
        self.assertNotEqual(samples[0], samples[-1])
        self.assertAlmostEqual(math.sin(0), math.sin(2*math.pi), places=14)
        self.assertAlmostEqual(omega*math.cos(0), omega*math.cos(2*math.pi), places=14)
        self.assertEqual(periodic_spec()['cycles_per_period'], 1)
        self.assertEqual(len(samples), 300)

    def test_relaxed_baseline_is_required_not_small_offsets_about_t_pose(self):
        baseline = baseline_spec()
        self.assertEqual(baseline['upper_arm_drop_from_lateral_deg'], 65.0)
        self.assertEqual(baseline['elbow_forward_flex_deg'], 15.0)
        self.assertEqual(baseline['fitting_failure'], 'REJECT_NEVER_FALL_BACK_TO_T_POSE')
        raw = request().to_dict()
        raw['baseline']['upper_arm_drop_from_lateral_deg'] = 0.0
        with self.assertRaises(ValidationError):
            AuthoredIdleRequest.from_dict(raw)

    def test_no_axis_quaternion_pose_or_executable_formula_injection(self):
        for field, extra in (('baseline', {'private_rest_vectors': [1,2,3]}),
                             ('periodic_motion', {'eval': '__import__("os")'}),
                             ('periodic_motion', {'source_clip_sha256': 'a'*64})):
            raw = request().to_dict()
            raw[field].update(extra)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                AuthoredIdleRequest.from_dict(raw)

    def test_loop_retiming_duplicate_endpoint_or_early_readiness_rejects(self):
        mutations = (('clock', 'phase_denominator', 299),
            ('clock', 'duplicate_terminal_sample', True),
            ('clock', 'virtual_seam_is_stored_sample', True),
            ('periodic_motion', 'root_and_lower_chain_offsets', 'SWAY'),
            ('required_quality', 'numeric_report_can_approve_usable_action', True))
        for section, key, value in mutations:
            raw = request().to_dict(); raw[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                AuthoredIdleRequest.from_dict(raw)

    def test_all_approval_flags_stay_false_even_with_all_consents(self):
        raw = request().to_dict()
        for field in ('native_authoring_verified','saved_reopen_verified',
                      'quality_measurements_verified','human_visual_review_approved',
                      'loop_quality_approved','usable_action_approved',
                      'origin_declaration_is_authorship_proof'):
            self.assertIs(raw[field], False)
            forged = deepcopy(raw); forged[field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                AuthoredIdleRequest.from_dict(forged)

    def test_request_rejects_unknown_schema_policy_profile_and_target_changes(self):
        for key, value in (('schema_version', True), ('schema_version', 2),
                           ('policy', 'other'), ('profile', 'HIPS76')):
            raw = request().to_dict(); raw[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                AuthoredIdleRequest.from_dict(raw)
        candidate = request()
        for target in (replace(candidate.target, project_id='other'),
                       replace(candidate.target, revision=8),
                       replace(candidate.target, master_sha256='9'*64),
                       replace(candidate.target, project_sha256='9'*64)):
            with self.subTest(target=target.project_id), self.assertRaises(ValidationError):
                replace(candidate, target=target)

    def test_unknown_field_dropped_reference_or_noncanonical_snapshot_rejects(self):
        raw = request().to_dict(); raw['unchecked_extra'] = True
        with self.assertRaises(ValidationError): AuthoredIdleRequest.from_dict(raw)
        raw = request().to_dict(); raw['project_snapshot']['animations'] = []
        with self.assertRaises(ValidationError): AuthoredIdleRequest.from_dict(raw)
        candidate = request()
        with self.assertRaises(ValidationError):
            replace(candidate, project_snapshot_json=candidate.project_snapshot_json+b'\n')

    def test_empty_invalid_or_replaced_measurement_and_policy_digest_reject(self):
        candidate = request()
        for value in ('', 'A'*64, 'a'*63, None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                replace(candidate, anatomical_frame_sha256=value)
        raw = candidate.to_dict(); raw['anatomical_frame_sha256'] = '2'*64
        changed = AuthoredIdleRequest.from_dict(raw)
        self.assertNotEqual(changed.sha256, candidate.sha256)
        permission = candidate.permissions[0]
        with self.assertRaises(ValidationError): replace(permission, source_policy_sha256='')

    def test_unadmitted_parts_and_saved_appearance_reject(self):
        candidate = request()
        project = replace(candidate.project, parts=(replace(candidate.project.parts[0], visible=False),))
        with self.assertRaises(ValidationError): with_project(candidate, project)
        project = replace(candidate.project, appearance=(('skin', 'materials/skin.json'),))
        with self.assertRaises(ValidationError): with_project(candidate, project)

    def test_duplicate_json_keys_and_nan_reject(self):
        with self.assertRaises(ValidationError):
            AuthoredIdleRequest.from_bytes(b'{"schema_version":1,"schema_version":1}')
        raw = request().to_dict(); raw['baseline']['elbow_forward_flex_deg'] = float('nan')
        with self.assertRaises(ValidationError): AuthoredIdleRequest.from_dict(raw)

    def test_core_draft_imports_only_pure_core_and_stdlib(self):
        import ucc.core.authored_idle as module
        tree = ast.parse(Path(module.__file__).read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(item.name in {'re'} for item in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertTrue(node.level == 1 or node.module in {'dataclasses','hashlib'})
        self.assertNotIn('bpy', module.__dict__)


if __name__ == '__main__':
    unittest.main()
