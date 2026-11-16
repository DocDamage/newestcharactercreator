"""Synthetic metadata only; these tests do not prove native/runtime execution."""
from copy import deepcopy
from dataclasses import replace
import unittest

from fixtures.target_action_contract import metadata_pair
from test_expression_contracts import prepared, source_project
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_native_recipe import build_native_recipe, validate_native_recipe, INPUTS
from ucc.export.godot_registered_native_recipe import (
    POLICY, MATERIAL_POLICY, build_registered_native_recipe,
    validate_registered_native_recipe, validate_registered_native_job,
)
from ucc.export.godot_runtime_contract import CODE_FILES, CAPABILITY
from ucc.library.provenance import LicensePolicy, AssetPolicyError


def recipe_args():
    _, original = metadata_pair()
    project = prepared(source_project(hand=True), hand=True)
    project = replace(project, animations=("unselected-original#clip-0000", original.source.clip_id))
    source = replace(original.source, source_sha256="f"*64)
    files = tuple(replace(row, sha256=(original.mapping_sha256 if row.name=="native_mapping.json"
        else source.snapshot_sha256)) if row.name in {"native_mapping.json", "source_snapshot.json"}
        else row for row in original.files)
    binding = replace(original, source=source, files=files, target=replace(original.target,
        project_id=project.project_id, revision=project.revision, project_sha256="1"*64,
        master_sha256="e"*64))
    sources = {"master":"e"*64, "expression_library":"d"*64,
        "part:"+project.parts[0].part_asset_id:"c"*64, "motion:original-diagnostic":"f"*64}
    policy = LicensePolicy("test-only", "Nonshipping test metadata", "unit-test://not-an-asset",
        reviewed=True, no_ai=True, can_use_non_unreal=True)
    return dict(project=project, project_file_sha256="1"*64, source_bindings=sources,
        evidence_bindings={"native_review":binding.file_map["body_first/review_motion.blend"].sha256,
            "native_timeline":binding.file_map["body_first/target_timeline.json"].sha256,
            "source_snapshot":source.snapshot_sha256, "native_mapping":binding.mapping_sha256},
        implementation={name:"a"*64 for name in CODE_FILES},
        permissions=tuple(EngineInputPermission(name,digest,policy,False) for name,digest in sources.items()),
        motion_asset_id="motion:original-diagnostic", capability=CAPABILITY,
        target_action_binding=binding, target_action_binding_sha256=binding.sha256,
        runtime_code_lengths={name:100 for name in CODE_FILES}, runtime_code_provenance_sha256="9"*64)


class RegisteredNativeRecipeTests(unittest.TestCase):
    def build(self, **changes):
        return build_registered_native_recipe(**(recipe_args() | changes))

    def test_roundtrip_preserves_full_project_binding_and_private_denials(self):
        args=recipe_args(); raw=build_registered_native_recipe(**args)
        self.assertEqual(raw, validate_registered_native_recipe(raw))
        self.assertEqual(raw["schema_version"],2); self.assertEqual(raw["policy"],POLICY)
        self.assertEqual(raw["project_snapshot"],args["project"].to_dict())
        self.assertEqual(raw["project_snapshot"]["animations"],list(args["project"].animations))
        self.assertEqual(raw["target_action_binding"],args["target_action_binding"].to_dict())
        self.assertEqual(raw["material_policy"],MATERIAL_POLICY)
        for key in ("runtime_code_provenance_verified","private_runtime_delivery_authorized",
                    "engine_import_verified","runtime_execution_verified","visual_quality_approved",
                    "distribution_license_review_complete","source_redistribution_authorized",
                    "cloud_transmission_authorized"):
            self.assertIs(raw[key],False)

    def test_foreign_current_selection_project_and_source_reject(self):
        args=recipe_args()
        changes=[dict(target_action_binding_sha256="0"*64),dict(project_file_sha256="0"*64),
            dict(project=replace(args["project"],animations=())),
            dict(project=replace(args["project"],revision=args["project"].revision+1)),
            dict(target_action_binding=args["target_action_binding"].to_dict()),
            dict(source_bindings=args["source_bindings"] | {args["motion_asset_id"]:"0"*64})]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValidationError):self.build(**change)

    def test_fixed_native_evidence_cannot_be_replaced_by_second_or_arbitrary_proofs(self):
        for name in ("native_review","native_timeline","source_snapshot","native_mapping"):
            args=recipe_args(); args["evidence_bindings"][name]="0"*64
            with self.subTest(name=name),self.assertRaises(ValidationError):build_registered_native_recipe(**args)
        args=recipe_args(); args["evidence_bindings"]["extra"]="a"*64
        with self.assertRaises(ValidationError):build_registered_native_recipe(**args)

    def test_exact_per_use_permissions_and_private_restrictions(self):
        args=recipe_args(); permissions=args["permissions"]
        variants=[permissions[:-1],permissions+(permissions[0],),
            (replace(permissions[0],source_only=True),)+permissions[1:],
            (replace(permissions[0],source_sha256="0"*64),)+permissions[1:]]
        for field,value in (("reviewed",False),("ue_only",True),("can_use_non_unreal",False),
                ("ai_input_allowed",True),("redistribute_source_allowed",True)):
            variants.append(tuple(replace(p,policy=replace(p.policy,**{field:value})) for p in permissions))
        variants.append(tuple(replace(p,policy=replace(p.policy,no_ai=False))
            if p.asset_id=="expression_library" else p for p in permissions))
        for selected in variants:
            with self.subTest(selected=selected),self.assertRaises((ValidationError,AssetPolicyError)):
                build_registered_native_recipe(**(args | {"permissions":selected}))

    def test_runtime_lengths_and_provenance_are_exact_bounded_identities(self):
        args=recipe_args()
        variants=[dict(runtime_code_lengths={}),dict(runtime_code_lengths=args["runtime_code_lengths"] | {"extra":1}),
            dict(runtime_code_provenance_sha256="A"*64)]
        for size in (True,0,-1,1.5,256*1024+1):
            variants.append(dict(runtime_code_lengths=args["runtime_code_lengths"] | {"runtime_kernel.gd":size}))
        for change in variants:
            with self.subTest(change=change),self.assertRaises(ValidationError):self.build(**change)

    def test_unassigned_material_and_prepared_specimen_reject_substitution(self):
        args=recipe_args()
        for changes in (dict(material_policy="SUBSTITUTE_CLAY"),
                dict(project=replace(args["project"],appearance=(("skin","arbitrary"),))),
                dict(capability="gl_compatibility")):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.build(**changes)

    def test_corrupted_typed_project_cannot_substitute_a_non_mpfb_provider(self):
        args=recipe_args()
        # Deliberately bypass the model constructor to test this boundary's
        # independent finite provider check, not ordinary model validation.
        object.__setattr__(args["project"],"base_provider","NONSHIPPING_FOREIGN_PROVIDER")
        with self.assertRaisesRegex(ValidationError,"prepared unassigned-material profile"):
            build_registered_native_recipe(**args)

    def test_closed_reader_rejects_partial_unknown_and_approval_drift(self):
        mutations=[lambda r:r.update(extra=True),lambda r:r.pop("runtime_code_lengths"),
            lambda r:r.update(schema_version=True),lambda r:r.update(schema_version=1),
            lambda r:r.update(engine_import_verified=True),lambda r:r.update(runtime_code_provenance_verified=True),
            lambda r:r["timeline"].update(fps=24),lambda r:r["target_action_binding"]["producer"].update(cache_job_id="bad"),
            lambda r:r.update(project_snapshot_sha256="0"*64)]
        for mutate in mutations:
            raw=deepcopy(self.build()); mutate(raw)
            with self.subTest(raw=raw),self.assertRaises(ValidationError):validate_registered_native_recipe(raw)

    def test_stage_verify_have_distinct_closed_options_and_binding_identity(self):
        options={name:"a"*64 for name in set(INPUTS.values())|{"native_recipe_sha256","target_action_binding_sha256"}}
        validate_registered_native_job("stage_registered_native_godot_runtime","candidate.blend",options)
        validate_registered_native_job("verify_registered_native_godot_runtime","candidate.blend",options|{"native_stage_sha256":"b"*64})
        for operation,values in (("verify_registered_native_godot_runtime",options),
                ("stage_registered_native_godot_runtime",options|{"native_stage_sha256":"b"*64}),
                ("stage_native_godot_runtime",options),
                ("stage_registered_native_godot_runtime",options|{"target_action_binding_sha256":True})):
            with self.subTest(operation=operation,values=values),self.assertRaises(ValidationError):
                validate_registered_native_job(operation,"candidate.blend",values)

    def test_legacy_recipe_still_rejects_references_and_v2(self):
        args=recipe_args(); legacy={k:v for k,v in args.items() if k not in {
            "target_action_binding","target_action_binding_sha256","runtime_code_lengths","runtime_code_provenance_sha256"}}
        with self.assertRaises(ValidationError):build_native_recipe(**legacy)
        with self.assertRaises(ValidationError):validate_native_recipe(self.build())

    def test_coherently_rehashed_part_permission_cannot_override_registered_asset_identity(self):
        args=recipe_args(); name="part:"+args["project"].parts[0].part_asset_id
        args["source_bindings"][name]="0"*64
        args["permissions"]=tuple(replace(p,source_sha256="0"*64) if p.asset_id==name
            else p for p in args["permissions"])
        with self.assertRaises(ValidationError):build_registered_native_recipe(**args)
