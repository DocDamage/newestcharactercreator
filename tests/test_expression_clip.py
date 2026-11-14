"""Closed facial clip and independent scalar-math tests; no geometry claims."""
from copy import deepcopy
from pathlib import Path
import unittest

from ucc.core.errors import ValidationError
from ucc.core.expression_clip import build_expression_clip, validate_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import TARGETS
from ucc.jobs.protocol import JobRequest
from ucc.preview.expression_cache import validate_clip_report, read_expression_cache
from blender_bridge.expression_clip_policy import recipe
from blender_bridge.expression_clip_action import linear_weight
from test_expression_contracts import source_project, prepared


class ExpressionClipTests(unittest.TestCase):
    def clip(self):
        return build_expression_clip(prepared(source_project(face=True)), 'e'*64)

    def test_closed_core_and_independent_bridge_recipes_agree(self):
        raw = self.clip()
        self.assertEqual(validate_expression_clip(raw), recipe(raw, 'e'*64))
        with self.assertRaises(ValueError): recipe(raw, 'f'*64)
        for bad in (None, True, '', '../master'):
            with self.assertRaises(ValidationError): build_expression_clip(prepared(source_project()), bad)

    def test_actual_complete_project_snapshot_is_bound(self):
        project = prepared(source_project(face=True))
        raw = build_expression_clip(project, 'e'*64)
        self.assertEqual(raw['source']['project_snapshot_sha256'], canonical_digest(project.to_dict()))
        self.assertEqual(raw['source']['revision'], project.revision)
        self.assertEqual(raw['source']['library_sha256'], project.expression.library_sha256)

    def test_both_validators_reject_scope_timing_identity_and_strength_substitutions(self):
        changes = [lambda r: r.update(schema_version=True), lambda r: r.update(extra=True),
                   lambda r: r['source'].update(revision=True), lambda r: r['source'].pop('project_snapshot_sha256'),
                   lambda r: r['source'].update(library_sha256='../library'),
                   lambda r: r['parameters'].update(mouth_open=.501), lambda r: r['parameters'].update(mouth_open=True),
                   lambda r: r['parameters'].update(mouth_open=float('nan')),
                   lambda r: r['timeline'].update(fps=30), lambda r: r['timeline'].update(last_frame=24),
                   lambda r: r['timeline'].update(keyframes=[1, 12, 25]),
                   lambda r: r['timeline'].update(interpolation='BEZIER'),
                   lambda r: r['targets'][0].update(file='../elsewhere'), lambda r: r['targets'].pop()]
        for i, edit in enumerate(changes):
            raw = self.clip(); edit(raw)
            with self.subTest(case=i):
                with self.assertRaises(ValidationError): validate_expression_clip(raw)
                with self.assertRaises(ValueError): recipe(raw, 'e'*64)

    def test_clip_requests_are_closed_and_pin_every_target(self):
        for op in ('stage_mpfb_expression_clip', 'verify_mpfb_expression_clip'):
            options = {'master_sha256': 'a'*64, 'clip_sha256': 'b'*64,
                       **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
            if op.startswith('verify'):
                options.update({k: 'c'*64 for k in ('motion_sha256', 'motion_report_sha256', 'cache_sha256', 'cache_manifest_sha256')})
            JobRequest.new(op, input_project='candidate.blend', options=options)
            for field in options:
                broken = dict(options); del broken[field]
                with self.assertRaises(ValidationError): JobRequest.new(op, input_project='candidate.blend', options=broken)
            for broken in (dict(options, extra='a'*64), dict(options, eye_left_closure_african_sha256='a'*64)):
                with self.assertRaises(ValidationError): JobRequest.new(op, input_project='candidate.blend', options=broken)

    def test_independent_float32_math_matches_observed_scalar_blender_samples(self):
        # Scalar-only Blender 5.3 experiment, not a mesh or facial acceptance fixture.
        peak = .0990000069141388
        observed = {2: .008250000886619091, 7: .0495000034570694, 12: .09075000882148743,
                    13: .0990000069141388, 14: .09075000882148743,
                    19: .0495000034570694, 24: .008249998092651367}
        for frame, value in observed.items(): self.assertEqual(linear_weight(peak, frame), value)
        self.assertEqual(linear_weight(peak, 1), 0.); self.assertEqual(linear_weight(peak, 25), 0.)
        self.assertNotEqual(linear_weight(peak, 2), linear_weight(peak, 24))

    def test_cache_cannot_be_read_without_complete_independent_proof(self):
        with self.assertRaises(ValidationError):
            read_expression_cache(Path('must-not-be-read'), {}, {}, {})

    def test_report_requires_all_frames_exact_endpoints_and_false_approval_flags(self):
        # Hash-only protocol fixture; it does not represent a real character.
        from ucc.core.expression_clip import CLIP_POLICY
        bindings = {'master_sha256': 'a'*64, 'clip_sha256': 'b'*64, 'motion_sha256': 'c'*64}
        row = {k: 'd'*64 for k in ('full_sha256', 'visible_sha256', 'fixed_state_sha256',
            'local_vertices_sha256', 'triangles_sha256', 'skin_sha256', 'raw_sha256')}
        rows = [dict(row, frame=i, maximum_displacement=0., moved_vertices_over_1um=0) for i in range(1, 26)]
        report = {'schema_version': 1, 'policy': CLIP_POLICY, **bindings, 'neutral_state_sha256': 'e'*64,
            'world_matrix': [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.], 'hip_world': [0.,0.,0.],
            'frame_count': 25, 'fps': 24, 'keyframes': [1,13,25], 'frames': rows,
            'exact_neutral_endpoints': True, 'visual_quality_approved': False, 'engine_import_verified': False}
        self.assertEqual(validate_clip_report(report, bindings), report)
        pose_triangles = deepcopy(report); pose_triangles['frames'][12]['triangles_sha256'] = 'e'*64
        pose_triangles['frames'][-1].update(triangles_sha256='e'*64, raw_sha256='e'*64)
        self.assertEqual(validate_clip_report(pose_triangles, bindings), pose_triangles)
        for edit in (lambda r:r['frames'].pop(), lambda r:r.update(frame_count=True),
                lambda r:r.update(keyframes=[True,13,25]), lambda r:r.update(engine_import_verified=True),
                lambda r:r['frames'][12].update(maximum_displacement=.03001),
                lambda r:r['frames'][12].update(fixed_state_sha256='e'*64),
                lambda r:r['frames'][-1].update(full_sha256='e'*64),
                lambda r:r['frames'][1].update(frame=True), lambda r:r.update(extra=True)):
            broken = deepcopy(report); edit(broken)
            with self.assertRaises(ValidationError): validate_clip_report(broken, bindings)

    def test_shipped_clip_job_and_recipe_schemas_match_the_closed_contract(self):
        import json
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema not installed')
        root = Path(__file__).resolve().parents[1]/'docs/schemas'
        schema = lambda name: json.loads((root/name).read_text())
        validator = Draft202012Validator(schema('expression-clip.v1.schema.json'))
        raw = self.clip(); validator.validate(raw)
        for field in raw:
            broken = deepcopy(raw); del broken[field]
            self.assertTrue(list(validator.iter_errors(broken)))
        validator = Draft202012Validator(schema('worker-job.v1.schema.json'))
        for op in ('stage_mpfb_expression_clip', 'verify_mpfb_expression_clip'):
            options = {'master_sha256': 'a'*64, 'clip_sha256': 'b'*64,
                       **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
            if op.startswith('verify'):
                options.update({k: 'c'*64 for k in ('motion_sha256', 'motion_report_sha256', 'cache_sha256', 'cache_manifest_sha256')})
            job = JobRequest.new(op, input_project='candidate.blend', options=options); validator.validate(job.as_dict())
            for field in options:
                broken = job.as_dict(); broken['options'] = dict(options); del broken['options'][field]
                self.assertTrue(list(validator.iter_errors(broken)))
