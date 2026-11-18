"""Pure envelope/schema rejection tests, never native animation evidence."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from uuid import uuid4

from ucc.core.authored_idle_job import OPERATIONS, validate_job
from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


def envelope(operation):
    options = {'request_sha256': 'a' * 64}
    if operation == 'verify_authored_idle_source':
        options.update({name: 'b' * 64 for name in (
            'source_sha256', 'review_sha256', 'recipe_sha256')})
    return dict(protocol_version=1, job_id=str(uuid4()), operation=operation,
                input_project='candidate.blend', options=options)


class AuthoredIdleProtocolTests(unittest.TestCase):
    def test_exact_envelopes_roundtrip(self):
        for operation in OPERATIONS:
            raw = envelope(operation)
            request = JobRequest(**raw)
            self.assertEqual(JobRequest.from_dict(request.as_dict()), request)

    def invalid_envelopes(self):
        for operation in OPERATIONS:
            raw = envelope(operation)
            for field in raw['options']:
                value = deepcopy(raw); del value['options'][field]; yield value
                for bad in (True, None, 123, 'A' * 64, 'a' * 63, '../source'):
                    value = deepcopy(raw); value['options'][field] = bad; yield value
            value = deepcopy(raw); value['options']['source_path'] = 'motion.fbx'; yield value
            for bad in (None, '../candidate.blend', 'original.blend', '/candidate.blend'):
                value = deepcopy(raw); value['input_project'] = bad; yield value

    def test_phase_bindings_and_paths_rejected(self):
        for raw in self.invalid_envelopes():
            with self.subTest(operation=raw['operation'], options=raw['options']):
                with self.assertRaises(ValidationError):
                    JobRequest(**raw)
        with self.assertRaises(ValidationError):
            validate_job('unknown', 'candidate.blend', {'request_sha256': 'a' * 64})

    def test_malformed_operation_has_structured_error(self):
        for operation in ([], {}, None, True, 1):
            with self.subTest(operation=operation):
                with self.assertRaises(ValidationError):
                    validate_job(operation, 'candidate.blend', {'request_sha256': 'a' * 64})
                raw = envelope('inspect_authored_idle_target')
                raw['operation'] = operation
                with self.assertRaises(ValidationError):
                    JobRequest.from_dict(raw)

    @unittest.skipIf(Draft202012Validator is None, 'Optional jsonschema unavailable')
    def test_schema_matches_closed_protocol(self):
        path = Path(__file__).resolve().parents[1] / 'docs/schemas/worker-job.v1.schema.json'
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for operation in OPERATIONS:
            validator.validate(envelope(operation))
        for raw in self.invalid_envelopes():
            self.assertTrue(list(validator.iter_errors(raw)))
