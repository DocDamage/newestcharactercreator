"""Verify shipped machine contracts match representative real model serialization.

JSON Schema is optional in development so the core stays stdlib-only.
"""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ucc.core.models import CharacterProject, PartAsset
from ucc.core.anatomy import get_slot
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.sprites.plan import CameraProfile, build_plan

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


class SchemaTests(unittest.TestCase):
    @staticmethod
    def read_schema(filename):
        return json.loads((ROOT / "docs" / "schemas" / filename).read_text(encoding="utf-8"))

    def test_all_schema_files_load(self):
        files = list((ROOT / "docs" / "schemas").glob("*.schema.json"))
        self.assertEqual(len(files), 6)
        for path in files:
            with self.subTest(path=path.name):
                schema = self.read_schema(path.name)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertFalse(schema["additionalProperties"])

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_schema_draft_and_sample_objects(self):
        p = CharacterProject.new("First")
        slot = get_slot("humanoid.v1", "eye.L")
        a = PartAsset("asset-001", ("humanoid.v1",), "rigid_mesh", "eye.L", slot.socket,
                      "license-001", "library/eye.glb")
        req = JobRequest.new("inspect_environment")
        result = JobResult(req.job_id, req.operation, "ok", {"mpfb": False})
        plan = build_plan({"idle": 3}, CameraProfile(directions=4))
        for filename, obj in [
            ("character-project.v1.schema.json", p.to_dict()),
            ("part-asset.v1.schema.json", a.to_dict()),
            ("worker-job.v1.schema.json", req.as_dict()),
            ("worker-result.v1.schema.json", result.as_dict()),
            ("sprite-plan.v1.schema.json", plan.to_dict()),
        ]:
            with self.subTest(schema=filename):
                schema = self.read_schema(filename)
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(obj)

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_schema_rejects_unknown_project_fields(self):
        data = CharacterProject.new("Test").to_dict()
        data["unknown"] = "unapproved"
        errors = list(Draft202012Validator(self.read_schema("character-project.v1.schema.json")).iter_errors(data))
        self.assertTrue(errors)
