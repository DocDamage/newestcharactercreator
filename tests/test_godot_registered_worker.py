"""Synthetic boundary tests; no Blender, source geometry or engine acceptance."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fixtures.godot_native_logic import stage_report
from fixtures.godot_registered_worker_logic import source_functions, material_scene, image
from test_godot_registered_native_recipe import recipe_args
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_native_recipe import (
    INPUTS, POLICY as LEGACY_POLICY, build_native_recipe, validate_native_job,
    validate_native_recipe,
)
from ucc.export.godot_registered_native_recipe import (
    POLICY, build_registered_native_recipe,
)
from ucc.jobs.godot_native_producer import _report
from ucc.jobs.protocol import JobRequest

ROOT = Path(__file__).resolve().parents[1]


def options(operation, binding="a" * 64):
    result = {name: "a" * 64 for name in set(INPUTS.values()) | {"native_recipe_sha256"}}
    if "registered" in operation:
        result["target_action_binding_sha256"] = binding
    if operation.startswith("verify"):
        result["native_stage_sha256"] = "b" * 64
    return result


def legacy_recipe():
    args = recipe_args()
    fields = {"project", "project_file_sha256", "source_bindings", "evidence_bindings",
              "implementation", "permissions", "motion_asset_id", "capability"}
    args = {key: value for key, value in args.items() if key in fields}
    args["project"] = replace(args["project"], animations=())
    return build_native_recipe(**args)


class RegisteredWorkerTests(unittest.TestCase):
    def test_protocol_and_job_schema_reject_operation_and_hash_substitution(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(json.loads(
            (ROOT / "docs/schemas/worker-job.v1.schema.json").read_text()))
        for operation in ("stage_registered_native_godot_runtime",
                          "verify_registered_native_godot_runtime"):
            raw = JobRequest.new(operation, input_project="candidate.blend",
                                 options=options(operation)).as_dict()
            validator.validate(raw)
            mutations = []
            for key in raw["options"]:
                changed = deepcopy(raw); changed["options"].pop(key); mutations.append(changed)
            for key, value in (("target_action_binding_sha256", True), ("extra", "a" * 64)):
                changed = deepcopy(raw); changed["options"][key] = value; mutations.append(changed)
            changed = deepcopy(raw); changed["input_project"] = "foreign.blend"; mutations.append(changed)
            changed = deepcopy(raw); changed["operation"] = operation.replace("registered_", "")
            mutations.append(changed)
            for changed in mutations:
                with self.subTest(operation=operation, changed=changed):
                    with self.assertRaises(ValidationError): JobRequest.from_dict(changed)
                    self.assertTrue(list(validator.iter_errors(changed)))

    def test_result_schema_keeps_v2_policy_explicit_and_errors_available(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(json.loads(
            (ROOT / "docs/schemas/worker-result.v1.schema.json").read_text()))
        for operation, status, digest in (
            ("stage_registered_native_godot_runtime", "REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED", "native_stage_sha256"),
            ("verify_registered_native_godot_runtime", "FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED", "native_verification_sha256"),
        ):
            raw = {"protocol_version": 1, "job_id": "01234567-1234-4567-8901-0123456789ab",
                   "operation": operation, "status": "ok", "error": None,
                   "details": {"policy": POLICY, "status": status, digest: "a" * 64,
                               "frame_count": 300, "engine_import_verified": False}}
            validator.validate(raw)
            for key, value in (("policy", LEGACY_POLICY), ("frame_count", 299),
                               ("engine_import_verified", True), ("extra", True)):
                changed = deepcopy(raw); changed["details"][key] = value
                self.assertTrue(list(validator.iter_errors(changed)))
            raw.update(status="error", error="UNIT_ONLY_FAILURE", details={})
            validator.validate(raw)

    def checked(self, root, recipe, operation):
        read = Mock(return_value=recipe)
        namespace = source_functions(read_json=read, digest=lambda path: "a" * 64,
            INPUTS=INPUTS, validate_native_job=validate_native_job,
            validate_native_recipe=validate_native_recipe)
        selected = options(operation, recipe.get("target_action_binding_sha256", "a" * 64))
        sources, evidence = recipe["source_bindings"], recipe["evidence_bindings"]
        selected.update(master_sha256=sources["master"], source_sha256=sources[recipe["motion_asset_id"]],
            review_sha256=evidence["native_review"], timeline_sha256=evidence["native_timeline"],
            snapshot_sha256=evidence["source_snapshot"], mapping_sha256=evidence["native_mapping"])
        # Synthetic inputs have mocked identities; only actual code lengths are exercised here.
        namespace["digest"] = lambda path: selected[INPUTS[path.name]] if path.name in INPUTS else "a" * 64
        job = dict(operation=operation, input_project="candidate.blend", options=selected)
        return namespace, job, read

    def test_worker_validates_v2_binding_and_actual_code_lengths_before_admission(self):
        recipe = build_registered_native_recipe(**recipe_args())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in INPUTS: (root / name).write_bytes(b"UNIT_ONLY_NOT_NATIVE")
            for name in recipe["implementation"]: (root / name).write_bytes(b"x" * 100)
            namespace, job, _ = self.checked(root, recipe, "stage_registered_native_godot_runtime")
            self.assertEqual(namespace["checked_recipe"](root, job), recipe)
            job["options"]["target_action_binding_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "different target binding"):
                namespace["checked_recipe"](root, job)
            job["options"]["target_action_binding_sha256"] = recipe["target_action_binding_sha256"]
            (root / "runtime_kernel.gd").write_bytes(b"x" * 101)
            with self.assertRaisesRegex(ValueError, "byte length"):
                namespace["checked_recipe"](root, job)

    def test_worker_rejects_coherent_recipe_with_changed_embedded_binding_metadata(self):
        recipe = build_registered_native_recipe(**recipe_args())
        namespace, job, read = self.checked(Path("."), recipe, "stage_registered_native_godot_runtime")
        changed = deepcopy(recipe)
        changed["target_action_binding"]["target"]["revision"] += 1
        read.return_value = changed
        with self.assertRaises(ValidationError):
            namespace["checked_recipe"](Path("."), job)

    def test_v1_does_not_accept_v2_recipe_or_registered_options(self):
        recipe = build_registered_native_recipe(**recipe_args())
        namespace, job, _ = self.checked(Path("."), recipe, "stage_native_godot_runtime")
        with self.assertRaises(ValidationError): namespace["checked_recipe"](Path("."), job)
        namespace, job, _ = self.checked(Path("."), legacy_recipe(), "stage_registered_native_godot_runtime")
        with self.assertRaises(ValidationError): namespace["checked_recipe"](Path("."), job)

    def test_v1_code_length_behavior_is_unchanged(self):
        recipe = legacy_recipe()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in set(INPUTS) | set(recipe["implementation"]):
                (root / name).write_bytes(b"UNIT_ONLY_NOT_NATIVE")
            namespace, job, _ = self.checked(root, recipe, "stage_native_godot_runtime")
            self.assertEqual(namespace["checked_recipe"](root, job), recipe)

    def test_material_drift_rejects_before_reopen_or_character_mutation(self):
        recipe = build_registered_native_recipe(**recipe_args())
        for scene in (material_scene(slots=[object()]), material_scene(libraries=[object()]),
                      material_scene(images=[image(source="FILE")]),
                      material_scene(images=[image(filepath="private.png")]),
                      material_scene(images=[image(packed_file=object())]),
                      material_scene(images=[image(source="GENERATED")])):
            bpy, human = scene
            opened, reopen, state = Mock(), Mock(), Mock()
            bpy.ops = type("Ops", (), {"wm": type("WM", (), {"open_mainfile": opened})()})()
            namespace = source_functions(checked_recipe=lambda *_: recipe, bound_scene=Mock(),
                scene_objects=lambda _: (human, object()), character_state=state,
                reopen_native=reopen, INPUTS=INPUTS)
            namespace["checked_recipe"] = lambda *_: recipe
            with self.subTest(scene=scene), self.assertRaisesRegex(ValueError, "material profile"):
                namespace["admitted_source"](bpy, Path("."), {"options": {"master_sha256": "a" * 64}})
            opened.assert_called_once(); reopen.assert_not_called(); state.assert_not_called()

    def test_material_is_rechecked_after_private_native_reopen(self):
        recipe = build_registered_native_recipe(**recipe_args())
        bpy, human = material_scene()
        bpy.ops = type("Ops", (), {"wm": type("WM", (), {"open_mainfile": Mock()})()})()
        state = Mock(return_value="UNIT_INITIAL_STATE")
        def reopen(*args, **kwargs):
            human.data.materials.append(object())
            return {"frames_verified": 300}
        namespace = source_functions(bound_scene=Mock(), scene_objects=lambda _: (human, object()),
            character_state=state, reopen_native=reopen, INPUTS=INPUTS)
        namespace["checked_recipe"] = lambda *_: recipe
        with self.assertRaisesRegex(ValueError, "material profile"):
            namespace["admitted_source"](bpy, Path("."),
                {"options": {key: "a" * 64 for key in INPUTS.values()}})
        state.assert_called_once()

    def test_material_check_preserves_legacy_and_admits_only_unassigned_v2(self):
        namespace = source_functions()
        check = namespace["require_registered_material_state"]
        bpy, human = material_scene(images=[image()])
        check(bpy, human, build_registered_native_recipe(**recipe_args()))
        bpy, human = material_scene(slots=[object()], libraries=[object()], images=[image(source="FILE")])
        check(bpy, human, {"policy": LEGACY_POLICY})

    def test_report_reader_requires_explicit_v2_policy_without_broadening_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "native_stage.json"
            raw = stage_report("a" * 64); raw["policy"] = POLICY
            path.write_bytes(canonical_bytes(raw)); digest = sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValidationError):
                _report(root, path.name, digest, "a" * 64, raw["status"], lambda: None)
            self.assertEqual(_report(root, path.name, digest, "a" * 64, raw["status"],
                                    lambda: None, expected_policy=POLICY), raw)
            for policy in (LEGACY_POLICY, "UNKNOWN"):
                with self.assertRaises(ValidationError):
                    _report(root, path.name, digest, "a" * 64, raw["status"],
                            lambda: None, expected_policy=policy)
