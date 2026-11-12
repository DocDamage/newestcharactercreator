"""Original synthetic boundary cases; actual licensed Blender evidence is separate."""
from copy import deepcopy
import unittest

from fixtures.native_body_contract import contract
from blender_bridge.motion_quality import EdgeStrain,MotionQualityError
from blender_bridge.native_inputs import validate_profile as worker_profile
from blender_bridge.native_review_reopen import same_strain
from ucc.animations.native_profile import validate_native_profile
from ucc.core.errors import ValidationError
from ucc.jobs.native_evidence import validate_native_timeline
from ucc.jobs.native_skin_evidence import validate_reopen_report
from ucc.jobs.motion_quality_evidence import validate_motion_quality


def v2_contract():
    data,report,source,profile,bindings=contract()
    profile["mesh_strain_reference"]="TRUE_NEUTRAL_BIND_V2"
    data["mesh_strain_reference"]="TRUE_NEUTRAL_BIND_V2";data["motion_quality_schema_version"]=2
    data["first_pose_edge_strain"]=deepcopy(data["mesh_edge_strain"])
    data["mesh_edge_strain"]=deepcopy(data["bind_edge_strain"])
    data["first_pose_relative_frames"]=[]
    for row,bind in zip(data["full_timeline_frames"],data["bind_relative_frames"]):
        for key in ("min_edge_length_ratio","max_edge_stretch_ratio"):row[key]=bind[key]
        data["first_pose_relative_frames"].append({"frame":row["frame"],"min_edge_length_ratio":1.,"max_edge_stretch_ratio":1.})
    return data,report,source,profile,bindings


class NeutralStrainTests(unittest.TestCase):
    def test_saved_strain_comparisons_reject_nan_bool_and_missing_fields(self):
        measured={"max_edge_stretch_ratio":2.,"min_edge_length_ratio":.1}
        good={"frame":201,**measured};self.assertTrue(same_strain(measured,good,201))
        for value in (float('nan'),float('inf'),True,"2",None):
            bad={**good,"max_edge_stretch_ratio":value};self.assertFalse(same_strain(measured,bad,201))
        self.assertFalse(same_strain(measured,{**good,"frame":True},201))
        self.assertFalse(same_strain(measured,{**good,"extra":1},201))

    def test_compressed_posed_origin_recovery_is_not_neutral_stretch(self):
        neutral=EdgeStrain(((0.,0.,0.),(1.,0.,0.)),((0,1),))
        posed=EdgeStrain(((0.,0.,0.),(.1,0.,0.)),((0,1),))
        recovery=((0.,0.,0.),(.435,0.,0.))
        self.assertAlmostEqual(neutral.measure(recovery,((0,1),),201)["max_edge_stretch_ratio"],.435)
        self.assertAlmostEqual(posed.observe(recovery,((0,1),),201)["max_edge_stretch_ratio"],4.35)
        with self.assertRaises(MotionQualityError):posed.measure(recovery,((0,1),),201)
        for endpoint in (.049,4.001):
            with self.assertRaises(MotionQualityError):neutral.measure(((0.,0.,0.),(endpoint,0.,0.)),((0,1),),1)
        with self.assertRaises(MotionQualityError):posed.observe(((0.,0.,0.),(float('nan'),0.,0.)),((0,1),),2)

    def test_both_profile_boundaries_close_the_new_policy_and_keep_missing_legacy(self):
        _,_,_,profile,_=contract()
        for value in (None,"FIRST_POSE_AND_NEUTRAL_V1","TRUE_NEUTRAL_BIND_V2"):
            p=deepcopy(profile)
            if value is not None:p["mesh_strain_reference"]=value
            validate_native_profile(p,"a"*64,"b"*64,"c"*64);worker_profile(p,"a"*64,"b"*64,"c"*64)
        for value in (False,[],{},"FIRST_FRAME_IS_REST",None):
            p=deepcopy(profile);p["mesh_strain_reference"]=value
            with self.subTest(value=value),self.assertRaises(ValidationError):validate_native_profile(p,"a"*64,"b"*64,"c"*64)
            with self.assertRaises(ValueError):worker_profile(p,"a"*64,"b"*64,"c"*64)

    def test_v2_uses_neutral_main_rows_and_keeps_complete_posed_observations(self):
        data,report,source,profile,bindings=v2_contract()
        data["bind_relative_frames"][0]["min_edge_length_ratio"]=.1
        data["full_timeline_frames"][0]["min_edge_length_ratio"]=.1
        data["full_timeline_frames"][0]["max_bind_displacement_local"]=.01
        for row in data["first_pose_relative_frames"][1:]:row["max_edge_stretch_ratio"]=10.
        validate_native_timeline(data,report,source,profile,bindings)
        # The generic/BVH validator cannot silently reinterpret V2 as V1.
        with self.assertRaises(ValidationError):validate_motion_quality(data,[p["target"] for p in profile["pairs"][1:]])

    def test_policy_version_neutral_bounds_coverage_and_false_observations_reject(self):
        for fault in ("profile","version","missing","frame","bounds","main","topology","first","nan","contradiction"):
            data,report,source,profile,bindings=v2_contract()
            if fault=="profile":profile.pop("mesh_strain_reference")
            if fault=="version":data["motion_quality_schema_version"]=1
            if fault=="missing":data["first_pose_relative_frames"].pop()
            if fault=="frame":data["first_pose_relative_frames"][1]["frame"]=1
            if fault=="bounds":data["bind_relative_frames"][1]["max_edge_stretch_ratio"]=4.1
            if fault=="main":data["full_timeline_frames"][1]["max_edge_stretch_ratio"]=1.01
            if fault=="topology":data["first_pose_edge_strain"]["evaluated_topology_sha256"]="0"*64
            if fault=="first":data["first_pose_relative_frames"][0]["min_edge_length_ratio"]=.9
            if fault=="nan":data["first_pose_relative_frames"][1]["max_edge_stretch_ratio"]=float('nan')
            if fault=="contradiction":data["first_pose_relative_frames"][1]["max_edge_stretch_ratio"]=100.
            with self.subTest(fault=fault),self.assertRaises(ValidationError):validate_native_timeline(data,report,source,profile,bindings)

    def test_reopen_must_explicitly_confirm_every_new_observation(self):
        data={"source_frame_count":5,"mesh_strain_reference":"TRUE_NEUTRAL_BIND_V2"}
        bindings={"source_sha256":"a"*64}
        report={"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":bindings,"frames_verified":5,
            "uncorrected_skin_frames_verified":5,"master_strain_frames_verified":5,"hip_frames_verified":0,
            "skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1","original_master_unchanged":True,"review_unchanged":True,
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False,
            "mesh_strain_reference":"TRUE_NEUTRAL_BIND_V2","first_pose_observation_frames_verified":5}
        validate_reopen_report(report,bindings,data)
        for value in (None,True,4):
            bad=deepcopy(report);bad["first_pose_observation_frames_verified"]=value
            with self.assertRaises(ValidationError):validate_reopen_report(bad,bindings,data)
