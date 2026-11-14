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
        self.assertEqual(len(files), 14)
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
    def test_native_fbx_request_schema_requires_only_sha_and_no_master(self):
        request=JobRequest.new("inspect_fbx_animation",options={"source_sha256":"a"*64}).as_dict()
        validator=Draft202012Validator(self.read_schema("worker-job.v1.schema.json"))
        validator.validate(request)
        request["input_project"]="master.blend"
        self.assertTrue(list(validator.iter_errors(request)))
        request["input_project"]=None
        request["options"]["arbitrary_path"]="../../source.fbx"
        self.assertTrue(list(validator.iter_errors(request)))

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_native_body_profile_and_bound_worker_schema(self):
        from fixtures.native_body_contract import contract
        _,_,_,profile,bindings=contract()
        Draft202012Validator(self.read_schema("native-body-map.v1.schema.json")).validate(profile)
        from fixtures.native_palm_contract import palm_contract
        palm=palm_contract()[0]
        validator=Draft202012Validator(self.read_schema("native-body-map.v1.schema.json"))
        validator.validate(palm)
        del palm["hand_reference_planes"]
        self.assertTrue(list(validator.iter_errors(palm)))
        request=JobRequest.new("verify_native_fbx_body",input_project="candidate.blend",
                               options={**bindings,"render_private_frames":True}).as_dict()
        validator=Draft202012Validator(self.read_schema("worker-job.v1.schema.json"))
        validator.validate(request)
        request["options"]["render_private_frames"]=1
        self.assertTrue(list(validator.iter_errors(request)))
        request["options"]["render_private_frames"]=False
        request["input_project"]="authoritative.blend"
        self.assertTrue(list(validator.iter_errors(request)))

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_surface_verifier_requires_its_seventh_hash_and_fixed_stage_name(self):
        hashes={k:'a'*64 for k in ('source_sha256','snapshot_sha256','mapping_sha256','master_sha256','review_sha256','timeline_sha256','surface_review_sha256')}
        request=JobRequest.new('verify_native_surface_review',input_project='candidate.blend',options=hashes).as_dict()
        validator=Draft202012Validator(self.read_schema('worker-job.v1.schema.json'));validator.validate(request)
        request['options']['surface_review_sha256']=True
        self.assertTrue(list(validator.iter_errors(request)))
        request['options']['surface_review_sha256']='a'*64;request['input_project']='authoritative.blend'
        self.assertTrue(list(validator.iter_errors(request)))

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_surface_review_schema_closes_unavailable_partial_annotations(self):
        import tempfile
        from fixtures.surface_cache_contract import write_surface_cache
        with tempfile.TemporaryDirectory() as folder:
            surface=write_surface_cache(Path(folder))[5]
        validator=Draft202012Validator(self.read_schema('motion-surface-review.v1.schema.json'));validator.validate(surface)
        surface['status']='UNAVAILABLE';surface['reason']='WEIGHTED_REGIONS_UNAVAILABLE'
        self.assertTrue(list(validator.iter_errors(surface)))
        for row in surface['frames']:row['left']=row['right']=None
        validator.validate(surface)

    @unittest.skipIf(Draft202012Validator is None, "Install jsonschema to validate v1 contracts")
    def test_schema_rejects_unknown_project_fields(self):
        data = CharacterProject.new("Test").to_dict()
        data["unknown"] = "unapproved"
        errors = list(Draft202012Validator(self.read_schema("character-project.v1.schema.json")).iter_errors(data))
        self.assertTrue(errors)

    @unittest.skipIf(Draft202012Validator is None, "Optional JSON Schema validator unavailable")
    def test_source_rest_and_reviewed_worker_contracts(self):
        from test_source_rest_intake import profile, PAIRS
        data = profile()
        schema = self.read_schema("source-rest-frames.v1.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(data)
        data["provenance"]["method"] = "bad\ncontrol"
        self.assertTrue(list(validator.iter_errors(data)))
        request = JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend",
            options={"axis_profile": "Y_UP_TO_Z_UP", "reviewed_mapping": PAIRS,
                     "source_rest_profile_sha256": "a" * 64}).as_dict()
        validator = Draft202012Validator(self.read_schema("worker-job.v1.schema.json"))
        validator.validate(request)
        request["options"].update(source_frame_conversion="BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1", render_private_frames=True)
        validator.validate(request)
        del request["options"]["source_rest_profile_sha256"]
        self.assertTrue(list(validator.iter_errors(request)))
        request["options"]["source_rest_profile_sha256"] = "a"*64
        del request["options"]["source_frame_conversion"]
        self.assertTrue(list(validator.iter_errors(request)))
        request["options"]["source_frame_conversion"] = "BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1"
        result = JobResult(request["job_id"], request["operation"], "ok",
                           {"source_rest_frame_intake": None}).as_dict()
        Draft202012Validator(self.read_schema("worker-result.v1.schema.json")).validate(result)
        request["options"]["profile_path"] = "unapproved/path"
        self.assertTrue(list(validator.iter_errors(request)))
