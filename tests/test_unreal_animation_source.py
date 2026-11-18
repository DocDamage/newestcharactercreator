"""Closed worker tests for the registered Unreal Blender source."""

import json
from pathlib import Path
import unittest

from ucc.core.errors import ValidationError
from ucc.export import unreal_animation_recipe as unreal
from ucc.export import unity_animation_recipe as unity
from ucc.jobs.protocol import JobRequest, JobResult


class RegisteredUnrealAnimationTests(unittest.TestCase):
    def setUp(self):
        self.options = {name: 'a' * 64 for name in (*unreal.INPUT_FILES.values(), 'source_sha256')}
        self.files = {name: 'b' * 64 for name in unreal.OUTPUT_LIMITS}
        self.details = {'policy': unreal.POLICY, 'files': self.files, 'engine_import_verified': False}

    def test_distinct_closed_operations_and_results(self):
        staged = JobRequest.new(unreal.STAGE, input_project='candidate.blend', options=self.options)
        JobResult(staged.job_id, unreal.STAGE, 'ok', self.details)
        with self.assertRaises(ValidationError):
            JobResult(staged.job_id, unreal.STAGE, 'ok', {**self.details, 'policy': unity.POLICY})
        with self.assertRaises(ValidationError):
            JobResult(staged.job_id, unreal.STAGE, 'ok', {**self.details, 'engine_import_verified': True})
        with self.assertRaises(ValidationError):
            JobResult(staged.job_id, unreal.STAGE, 'ok',
                      {**self.details, 'files': {**self.files, unity.WEIGHTS: 'b' * 64}})
        with self.assertRaises(ValidationError):
            JobRequest.new(unreal.VERIFY, input_project='candidate.blend', options=self.options)
        with self.assertRaises(ValidationError):
            JobRequest.new(unreal.STAGE, input_project='review_motion.blend', options=self.options)

    def test_verify_requires_source_seams_and_keeps_engine_readiness_false(self):
        report = unreal.source_report(self.options, self.files)
        self.assertIs(report['blender_fbx_reimport_verified'], False)
        final = unreal.source_report(self.options, self.files, fbx_readback_sha256='c' * 64)
        self.assertEqual(report['fbx_basis_model'], 'UccAnimationBasis')
        self.assertEqual(final['fbx_basis_model'], report['fbx_basis_model'])
        self.assertEqual((final['source_samples'], final['virtual_endpoint'], final['fps']), (300, 301, 30))
        self.assertIs(final['blender_fbx_reimport_verified'], True)
        self.assertIs(final['recomputed_source_references'], True)
        for flag in ('engine_import_verified', 'unreal_playback_verified', 'corrective_runtime_verified'):
            self.assertIs(final[flag], False)
        self.assertEqual(unreal.CORRECTION_INPUTS, unity.CORRECTION_INPUTS)
        self.assertFalse(set(unreal.REFERENCES) & set(unity.REFERENCES))

    def test_schema_matches_closed_runtime_envelopes(self):
        root = Path(__file__).resolve().parents[1] / 'docs/schemas'
        job, result = (json.loads((root / f'worker-{kind}.v1.schema.json').read_bytes())
                       for kind in ('job', 'result'))
        for operation in (unreal.STAGE, unreal.VERIFY):
            options = dict(self.options)
            details = dict(self.details)
            if operation == unreal.VERIFY:
                options.update({unreal.output_option(name): digest for name, digest in self.files.items()})
                details.update(verification_sha256='a' * 64, fbx_readback_sha256='b' * 64)
            request = JobRequest.new(operation, input_project='candidate.blend', options=options)
            JobResult(request.job_id, operation, 'ok', details)
            for schema, name, expected in ((job, 'options', options), (result, 'details', details)):
                sections = [node for node in schema['allOf']
                            if node['if']['properties'].get('operation', {}).get('const') == operation]
                self.assertEqual(len(sections), 1)
                closed = sections[0]['then']['properties'][name]
                self.assertFalse(closed['additionalProperties'])
                self.assertEqual(set(closed['required']), expected.keys())
                self.assertEqual(set(closed['properties']), expected.keys())
                if name == 'details':
                    files = closed['properties']['files']
                    self.assertFalse(files['additionalProperties'])
                    self.assertEqual(set(files['required']), self.files.keys())
