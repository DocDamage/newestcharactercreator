"""Original weight/mask boundaries and independent closed V2 skin evidence."""
from copy import deepcopy
import struct
import unittest
from unittest.mock import patch
from fixtures.native_region_mask import scene
from blender_bridge import native_region_mask as m
from ucc.animations.native_skin_policy import BOUND_V1, REGIONAL_V2
from ucc.animations.native_profile import validate_native_profile
from blender_bridge.native_inputs import validate_profile as worker_profile
from ucc.jobs.native_evidence import validate_native_timeline
from ucc.jobs.native_skin_evidence import validate_reopen_report
from ucc.jobs.native_regional_skin_evidence import MODIFIERS, MASK_NAME, SOURCE_GROUPS
from ucc.core.errors import ValidationError
from test_native_corrective import corrective_contract
from test_native_strain_reference import v2_contract


def regional_contract():
    data, report, source, profile, bindings = corrective_contract()
    neutral = v2_contract()[0]
    for key in ("mesh_strain_reference", "motion_quality_schema_version", "first_pose_edge_strain",
                "mesh_edge_strain", "first_pose_relative_frames"):
        data[key] = deepcopy(neutral[key])
    for row, bind in zip(data["full_timeline_frames"], data["bind_relative_frames"]):
        for key in ("min_edge_length_ratio", "max_edge_stretch_ratio"):
            row[key] = bind[key]
    profile["mesh_strain_reference"] = "TRUE_NEUTRAL_BIND_V2"
    profile["skin_deformation_policy"] = data["skin_deformation_policy"] = REGIONAL_V2
    proof = data["skin_deformation"]
    del proof["modifier"]
    proof.update(schema_version=2, policy=REGIONAL_V2, review_modifier_count=3,
                 modifiers=deepcopy(list(MODIFIERS)), source_vertex_groups_sha256="f"*64,
                 region_mask={"name": MASK_NAME, "formula": "MIN_ONE_SUM_ORIGINAL_DEFORM_WEIGHTS_V1",
                              "source_groups": SOURCE_GROUPS[:], "source_mesh_vertices": 1200,
                              "weighted_vertices": 700, "weights_sha256": "e"*64})
    return data, report, source, profile, bindings


class RegionalEvidenceTests(unittest.TestCase):
    def test_explicit_v2_and_unchanged_v1_contracts_pass(self):
        for args in (regional_contract(), corrective_contract()):
            self.assertIs(validate_native_timeline(*args), args[0])
        data, _, _, profile, _ = regional_contract()
        validate_native_profile(profile, "a"*64, "b"*64, "c"*64)
        worker_profile(profile, "a"*64, "b"*64, "c"*64)
        self.assertEqual(data["skin_deformation"]["source_modifier_count"], 1)

    def test_regional_profile_requires_actual_neutral_reference(self):
        for value in (None, "FIRST_POSE_AND_NEUTRAL_V1"):
            profile = regional_contract()[3]
            if value is None:
                del profile["mesh_strain_reference"]
            else:
                profile["mesh_strain_reference"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_native_profile(profile, "a"*64, "b"*64, "c"*64)
            with self.assertRaises(ValueError):
                worker_profile(profile, "a"*64, "b"*64, "c"*64)

    def test_order_binding_settings_mask_identity_and_versions_are_closed(self):
        for fault in ("order", "missing", "extra", "bound", "factor", "group", "iterations_bool",
                      "mask_hash", "source_hash", "formula", "source_groups", "weighted_bool",
                      "source_count", "mask_vertices", "schema", "v1_profile", "v1_proof"):
            args = deepcopy(regional_contract())
            proof = args[0]["skin_deformation"]
            if fault == "order": proof["modifiers"].reverse()
            if fault == "missing": proof["modifiers"].pop()
            if fault == "extra": proof["modifiers"].append(deepcopy(proof["modifiers"][0]))
            if fault == "bound": proof["modifiers"][1]["is_bound"] = False
            if fault == "factor": proof["modifiers"][1]["factor"] = .5
            if fault == "group": proof["modifiers"][1]["vertex_group"] = "spine05"
            if fault == "iterations_bool": proof["modifiers"][1]["iterations"] = True
            if fault == "mask_hash": proof["region_mask"]["weights_sha256"] = "bad"
            if fault == "source_hash": proof["source_vertex_groups_sha256"] = "bad"
            if fault == "formula": proof["region_mask"]["formula"] = "MAX_WEIGHTS"
            if fault == "source_groups": proof["region_mask"]["source_groups"].reverse()
            if fault == "weighted_bool": proof["region_mask"]["weighted_vertices"] = True
            if fault == "source_count": proof["review_modifier_count"] = 2
            if fault == "mask_vertices": proof["region_mask"]["source_mesh_vertices"] = 999
            if fault == "schema": proof["schema_version"] = 1
            if fault == "v1_profile": args[3]["skin_deformation_policy"] = BOUND_V1
            if fault == "v1_proof": proof["policy"] = BOUND_V1
            with self.subTest(fault=fault), self.assertRaises(ValidationError):
                validate_native_timeline(*args)

    def test_v2_preserves_original_strain_neutral_and_raw_correction_caps(self):
        for fault in ("stretch", "collapse", "correction", "neutral", "missing_raw"):
            args = deepcopy(regional_contract())
            if fault == "stretch": args[0]["master_relative_frames"][2]["max_edge_stretch_ratio"] = 4.001
            if fault == "collapse": args[0]["master_relative_frames"][2]["min_edge_length_ratio"] = .049
            if fault == "correction": args[0]["full_timeline_frames"][2]["skin_correction"]["max_correction_local"] = .061
            if fault == "neutral": args[0]["skin_deformation"]["max_neutral_displacement_local"] = 1.001e-6
            if fault == "missing_raw": del args[0]["full_timeline_frames"][2]["skin_correction"]
            with self.subTest(fault=fault), self.assertRaises(ValidationError):
                validate_native_timeline(*args)

    def test_family_default_stays_v1_and_regional_hand_map_is_explicit(self):
        from test_native_hands import NativeHandMappingTests
        from ucc.animations.native_family import measured_body_profile
        source, fingerprint = NativeHandMappingTests().source()
        with patch("ucc.animations.native_family.HIPS_OBJECT_TOPOLOGY", fingerprint):
            old = measured_body_profile(source, "a"*64, "b"*64, "c"*64, include_hands=True)
            new = measured_body_profile(source, "a"*64, "b"*64, "c"*64, include_hands=True, skin_policy=REGIONAL_V2)
            self.assertEqual(old["skin_deformation_policy"], BOUND_V1)
            self.assertEqual(new["skin_deformation_policy"], REGIONAL_V2)
            self.assertEqual(new["pairs"], old["pairs"])
            worker_profile(new, "a"*64, "b"*64, "c"*64)
            for value in (True, None, "AUTO", [REGIONAL_V2]):
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    measured_body_profile(source, "a"*64, "b"*64, "c"*64, skin_policy=value)

    def test_reopening_policy_must_match_its_versioned_timeline(self):
        data = regional_contract()[0]
        bindings = {"source_sha256": "a"*64}
        report = {"status": "REAL_NATIVE_BODY_REVIEW_REOPENED", "bindings": bindings,
                  "frames_verified": 5, "uncorrected_skin_frames_verified": 5,
                  "master_strain_frames_verified": 5, "hip_frames_verified": 0,
                  "skin_deformation_policy": REGIONAL_V2, "original_master_unchanged": True,
                  "review_unchanged": True, "retargeting_verified": False,
                  "animation_visual_quality_verified": False, "engine_import_verified": False,
                  "mesh_strain_reference": "TRUE_NEUTRAL_BIND_V2", "first_pose_observation_frames_verified": 5}
        validate_reopen_report(report, bindings, data)
        with self.assertRaises(ValidationError):
            validate_reopen_report({**report, "skin_deformation_policy": BOUND_V1}, bindings, data)
        del data["skin_deformation_policy"]
        with self.assertRaises(ValidationError):
            validate_reopen_report(report, bindings, data)

    def test_api_rejects_unknown_policy_or_explicit_map_override_before_intake(self):
        from pathlib import Path
        from types import SimpleNamespace
        from ucc.jobs.native_body import preview_native_body
        kwargs = dict(source_fbx=Path("unit-unused.fbx"), blender_exe=Path("unit-unused.exe"),
                      worker_script=Path("unit-unused.py"), permission=SimpleNamespace(allow=lambda _: (True, "")),
                      expected_project_id="unit", expected_revision=0, expected_master_blend="master/unit.blend")
        for value in (True, "", [], "AUTO"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                preview_native_body(None, skin_policy=value, **kwargs)
        with self.assertRaises(ValidationError):
            preview_native_body(None, skin_policy=REGIONAL_V2, mapping_profile=Path("unit-explicit.json"), **kwargs)
class RegionalMaskTests(unittest.TestCase):
 def test_derived_mask_preserves_all_original_binary_weights_and_clamps(self):
  h,r=scene();before=m.source_group_signature(h);g,proof=m.create_mask(h,r)
  self.assertEqual(proof['weighted_vertices'],20);self.assertEqual(h.data.vertices[1].groups[-1].weight,1.)
  self.assertIs(m.verify_mask(h,r,proof,before),g)
  h.vertex_groups.remove(g);self.assertEqual(m.source_group_signature(h),before)
 def test_coherently_rehashed_one_ulp_mask_mutation_rejects_formula(self):
  h,r=scene();before=m.source_group_signature(h);g,proof=m.create_mask(h,r)
  row=h.data.vertices[0].groups[-1];bits=struct.unpack('<I',struct.pack('<f',row.weight))[0];row.weight=struct.unpack('<f',struct.pack('<I',bits+1))[0]
  forged=m.mask_signature(h,g)
  with self.assertRaisesRegex(ValueError,'formula'):m.verify_mask(h,r,forged,before)
 def test_original_nonbone_weight_mutation_is_not_ignored(self):
  h,r=scene();before=m.source_group_signature(h);g,proof=m.create_mask(h,r)
  row=h.data.vertices[0].groups[-2];bits=struct.unpack('<I',struct.pack('<f',row.weight))[0];row.weight=struct.unpack('<f',struct.pack('<I',bits+1))[0]
  with self.assertRaisesRegex(ValueError,'original groups'):m.verify_mask(h,r,proof,before)
 def test_partial_creation_failure_removes_owned_group(self):
  h,r=scene();before=m.source_group_signature(h);h.vertex_groups.fail=True
  with self.assertRaisesRegex(RuntimeError,'Invented add failure'):m.create_mask(h,r)
  self.assertIsNone(h.vertex_groups.get(m.MASK_NAME));self.assertEqual(m.source_group_signature(h),before)
 def test_occupied_name_cannot_be_overwritten(self):
  h,r=scene();h.vertex_groups.new(m.MASK_NAME);before=m.source_group_signature(h)
  with self.assertRaisesRegex(ValueError,'occupied'):m.create_mask(h,r)
  self.assertEqual(m.source_group_signature(h),before)
