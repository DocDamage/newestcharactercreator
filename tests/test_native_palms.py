"""Independent parser, branch and rest-plane evidence negatives."""
from copy import deepcopy
import unittest
from fixtures.native_palm_contract import palm_contract
from ucc.animations.native_profile import validate_native_profile
from ucc.animations.native_palms import palm_normal, palm_evidence, validate_palm_hierarchy
from ucc.core.errors import ValidationError
from blender_bridge.native_inputs import validate_profile
from blender_bridge.native_palms import measure_planes, check_branches, normal


class NativePalmTests(unittest.TestCase):
    def test_closed_profile_passes_both_parsers_and_independent_normals_agree(self):
        p,d,sp,tp,parents,tparents,landmarks=palm_contract()
        validate_native_profile(p,"a"*64,"b"*64,"c"*64);validate_profile(p,"a"*64,"b"*64,"c"*64)
        actual=measure_planes(p,sp,tp,parents,tparents,1.,1.)
        for side in ("left","right"):
            self.assertAlmostEqual(actual["planes"][side]["source_normal"][2],-1.)
        result=palm_evidence(d,p,sp,parents,landmarks,1.,1.)
        self.assertEqual(set(result),{"left","right"})
        self.assertEqual(result["left"],([0.,0.,-1.],[0.,0.,-1.]))

    def test_incomplete_unused_retyped_or_unbound_declarations_reject_at_both_boundaries(self):
        for kind in ("version","missing","extra","unused","skin","duplicate","body","pair","side","root","wrist"):
            p=palm_contract()[0];planes=p["hand_reference_planes"]
            if kind=="version":planes["schema_version"]=True
            if kind=="missing":del planes["planes"]["left"]
            if kind=="extra":planes["unknown"]=1
            if kind=="unused":p["pairs"][-1]["secondary"]=p["pairs"][-2]["secondary"]="FORWARD"
            if kind=="skin":del p["skin_deformation_policy"]
            if kind=="duplicate":planes["planes"]["left"]["pinky"]=planes["planes"]["left"]["index"]
            if kind=="body":planes["planes"]["left"]["index"]=p["landmarks"]["left_hand"]
            if kind=="pair":planes["planes"]["left"]["index"]["target"]="foreign"
            if kind=="side":planes["planes"]["other"]=planes["planes"].pop("left")
            if kind=="root":planes["planes"]["left"]["index"]={k:p["pairs"][0][k] for k in ("source","target")}
            if kind=="wrist":next(r for r in p["pairs"] if r["source"]==p["landmarks"]["left_hand"]["source"])["secondary"]="PALM_LEFT_V1"
            with self.subTest(kind=kind),self.assertRaises(ValidationError):validate_native_profile(p,"a"*64,"b"*64,"c"*64)
            with self.assertRaises(ValueError):validate_profile(p,"a"*64,"b"*64,"c"*64)

    def test_crossed_same_branch_cyclic_and_wrist_self_mapping_reject(self):
        for domain in ("source","target"):
            for kind in ("crossed","same_branch","cycle","wrist"):
                p,_,_,_,sp,tp,_=palm_contract();parents=sp if domain=="source" else tp
                plane=p["hand_reference_planes"]["planes"]["left"]
                index,pinky=plane["index"][domain],plane["pinky"][domain]
                if kind=="crossed":parents[index]=p["landmarks"]["right_hand"][domain]
                if kind=="same_branch":parents[pinky]=index
                if kind=="cycle":parents[index]=index
                if kind=="wrist":
                    row=next(r for r in p["pairs"] if r[domain]==p["landmarks"]["left_hand"][domain]);row["secondary"]="PALM_LEFT_V1"
                with self.subTest(domain=domain,kind=kind),self.assertRaises(ValidationError):validate_palm_hierarchy(p,parents,domain)
                with self.assertRaises(ValueError):check_branches(p,parents,domain)

    def test_missing_forged_normals_and_displaced_wrist_proofs_reject(self):
        for kind in ("missing","extra","version","normal","nan","wrist","undeclared"):
            p,d,sp,_,parents,_,landmarks=palm_contract()
            row=d["hand_plane_proofs"]["planes"]["left"]
            if kind=="missing":del d["hand_plane_proofs"]
            if kind=="extra":row["unchecked"]=True
            if kind=="version":d["hand_plane_proofs"]["schema_version"]=True
            if kind=="normal":row["source_normal"][2]=1.
            if kind=="nan":row["target_normal"][0]=float('nan')
            if kind=="wrist":row["target_points"]["wrist"][0]+=.01
            if kind=="undeclared":del p["hand_reference_planes"]
            with self.subTest(kind=kind),self.assertRaises(ValidationError):palm_evidence(d,p,sp,parents,landmarks,1.,1.)

    def test_collinear_degenerate_oversized_nonfinite_and_boolean_geometry_reject(self):
        for kind in ("collinear","zero","large","nan","bool","huge_integer"):
            points=deepcopy(palm_contract()[1]["hand_plane_proofs"]["planes"]["left"]["target_points"])
            if kind=="collinear":points["pinky"]=points["index"][:]
            if kind=="zero":points["index"]=points["wrist"][:]
            if kind=="large":points["index"][0]+=100.
            if kind=="nan":points["index"][0]=float('nan')
            if kind=="bool":points["index"][0]=True
            if kind=="huge_integer":points["index"][0]=10**1000
            with self.subTest(kind=kind),self.assertRaises(ValidationError):palm_normal(points,1.)
            with self.assertRaises(ValueError):normal(points,1.)

    def test_reopened_plane_count_is_required_exact_and_absent_for_legacy(self):
        from fixtures.native_body_contract import contract
        from ucc.jobs.native_skin_evidence import validate_reopen_report
        d,_,_,_,bindings=contract()
        d["hand_plane_proofs"]=palm_contract()[1]["hand_plane_proofs"]
        r={"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":bindings,"frames_verified":5,
           "uncorrected_skin_frames_verified":5,"master_strain_frames_verified":5,"hip_frames_verified":0,
           "skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1","original_master_unchanged":True,
           "review_unchanged":True,"retargeting_verified":False,"animation_visual_quality_verified":False,
           "engine_import_verified":False,"hand_reference_planes_verified":2}
        validate_reopen_report(r,bindings,d)
        for value in (True,1,3,None):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                validate_reopen_report({**r,"hand_reference_planes_verified":value},bindings,d)
        del d["hand_plane_proofs"]
        with self.assertRaises(ValidationError):validate_reopen_report(r,bindings,d)
