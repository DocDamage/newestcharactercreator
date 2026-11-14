"""Pinned admission and independent policy parity; no deformation claims."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from blender_bridge.expression_policy import check_inputs, recipe
from ucc.core.errors import ValidationError
from ucc.core.expressions import TARGETS
from ucc.core.expression_recipe import build_expression_recipe, validate_expression_recipe
from ucc.jobs.protocol import JobRequest


class ExpressionPolicyTests(unittest.TestCase):
    def test_shipped_schemas_match_closed_worker_contract(self):
        import json
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema not installed')
        root = Path(__file__).resolve().parents[1]/'docs/schemas'
        schema = lambda name: json.loads((root/name).read_text())
        raw = build_expression_recipe('a'*64)
        validator = Draft202012Validator(schema('expression-preparation.v1.schema.json'))
        validator.validate(raw)
        for field in raw:
            broken = deepcopy(raw); del broken[field]
            self.assertTrue(list(validator.iter_errors(broken)))
        job_validator = Draft202012Validator(schema('worker-job.v1.schema.json'))
        result_validator = Draft202012Validator(schema('worker-result.v1.schema.json'))
        from ucc.jobs.protocol import JobResult
        for operation in ('stage_mpfb_expression_keys', 'verify_mpfb_expression_keys', 'inspect_mpfb_expression_keys'):
            options = {'master_sha256': 'a'*64, 'recipe_sha256': 'b'*64,
                       **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
            if operation.startswith('verify'):
                options.update(prepared_sha256='c'*64, report_sha256='d'*64)
            job = JobRequest.new(operation, input_project='candidate.blend', options=options)
            job_validator.validate(job.as_dict())
            result_validator.validate(JobResult(job.job_id, job.operation, 'ok', {}).as_dict())
            for field in options:
                broken = job.as_dict(); broken['options'] = dict(options); del broken['options'][field]
                self.assertTrue(list(job_validator.iter_errors(broken)))
            broken = job.as_dict(); broken['options'] = dict(options, extra='a'*64)
            self.assertTrue(list(job_validator.iter_errors(broken)))

    def test_independent_neutral_recipe_matches(self):
        raw = build_expression_recipe('a'*64)
        self.assertEqual(recipe(raw, 'a'*64), validate_expression_recipe(raw))
        with self.assertRaises(ValueError):
            recipe(raw, 'b'*64)

    def test_both_reject_substitutions_and_open_fields(self):
        changes = [lambda r: r.update(schema_version=True), lambda r: r.update(neutral=1),
                   lambda r: r.update(neutral=False), lambda r: r.update(extra=True),
                   lambda r: r['bindings'].pop('base_sha256'),
                   lambda r: r['bindings'].update(rig_sha256='b'*64),
                   lambda r: r['targets'][0].update(key='Basis'),
                   lambda r: r['targets'][0].update(file='../escape.gz'),
                   lambda r: r['targets'][0].update(sha256='b'*64),
                   lambda r: r['targets'][0].update(strength=.5),
                   lambda r: r['targets'].reverse(), lambda r: r['targets'].pop()]
        for i, change in enumerate(changes):
            raw = build_expression_recipe('a'*64); change(raw)
            with self.subTest(case=i):
                with self.assertRaises(ValueError): recipe(raw, 'a'*64)
                with self.assertRaises(ValidationError): validate_expression_recipe(raw)

    def test_requests_require_all_hashes_and_fixed_source(self):
        for operation in ('stage_mpfb_expression_keys', 'verify_mpfb_expression_keys', 'inspect_mpfb_expression_keys'):
            options = {'master_sha256': 'a'*64, 'recipe_sha256': 'b'*64,
                       **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
            if operation.startswith('verify'):
                options.update(prepared_sha256='c'*64, report_sha256='d'*64)
            JobRequest.new(operation, input_project='candidate.blend', options=options)
            for field in options:
                broken = deepcopy(options); del broken[field]
                with self.subTest(operation=operation, field=field), self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=broken)
            for broken in (dict(options, extra='b'*64), dict(options, eye_left_closure_african_sha256='b'*64)):
                with self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=broken)
            with self.assertRaises(ValidationError):
                JobRequest.new(operation, input_project='../other.blend', options=options)

    def test_bridge_requires_bindings_before_reading_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for options in ({}, [], {'master_sha256': 'a'*64}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    check_inputs(Path(folder), options)
