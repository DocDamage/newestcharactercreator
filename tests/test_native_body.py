"""Synthetic boundary/negative tests. Actual Blender/owner gates are separate."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.native_body_contract import contract,digest
from blender_bridge.native_inputs import validate_profile as worker_profile, validate_source as worker_source, read_json
from ucc.animations.native_profile import validate_native_profile,read_native_profile
from ucc.animations.native_family import measured_body_profile
from ucc.animations.native_math import product,rows,inverse,rotation
from ucc.core.errors import ValidationError
from ucc.jobs.native_evidence import validate_native_timeline,read_native_timeline
from ucc.jobs.protocol import JobRequest


class NativeProfileTests(unittest.TestCase):
    def test_explicit_profile_passes_both_boundaries_and_binds_all_three_inputs(self):
        _,_,source,profile,_=contract()
        validate_native_profile(profile,"a"*64,"b"*64,"c"*64)
        worker_profile(profile,"a"*64,"b"*64,"c"*64)
        worker_source(source,"a"*64)
        for key in ("source_sha256","snapshot_sha256","master_sha256"):
            bad=deepcopy(profile);bad[key]="f"*64
            with self.subTest(key=key),self.assertRaises(ValidationError):validate_native_profile(bad,"a"*64,"b"*64,"c"*64)
            with self.assertRaises(ValueError):worker_profile(bad,"a"*64,"b"*64,"c"*64)

    def test_names_roles_root_convention_and_false_schema_versions_reject(self):
        _,_,_,profile,_=contract()
        for case in ("version","convention","extra","root","root_tip","duplicate","secondary","secondary_list","secondary_object","landmark","landmark_pair","count","control"):
            p=deepcopy(profile)
            if case=="version":p["schema_version"]=True
            if case=="convention":p["convention"]="FIRST_FRAME_DELTA"
            if case=="extra":p["path"]="../../master.blend"
            if case=="root":p["pairs"][0]["source"]="S01"
            if case=="root_tip":p["pairs"][0]["source_tip"]="S01"
            if case=="duplicate":p["pairs"][-1]["source"]="s01"
            if case=="secondary":p["pairs"][-1]["secondary"]="AUTO"
            if case=="secondary_list":p["pairs"][-1]["secondary"]=["UP"]
            if case=="secondary_object":p["pairs"][-1]["secondary"]={"axis":"UP"}
            if case=="landmark":del p["landmarks"]["head"]
            if case=="landmark_pair":p["landmarks"]["head"]["target"]="OTHER"
            if case=="count":p["pairs"]=p["pairs"][:5]
            if case=="control":p["pairs"][-1]["target"]="bad\nname"
            with self.subTest(case=case),self.assertRaises(ValidationError):validate_native_profile(p,"a"*64,"b"*64,"c"*64)
            with self.assertRaises(ValueError):worker_profile(p,"a"*64,"b"*64,"c"*64)

    def test_bounded_duplicate_nonfinite_invalid_utf8_and_deep_profile_json_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"profile.json"
            for payload in (b'{"schema_version":1,"schema_version":1}',b'NaN',b'\xff',b'['*2000+b'0'+b']'*2000,b' '*65537):
                path.write_bytes(payload)
                with self.assertRaises(ValidationError):read_native_profile(path,"a"*64,"b"*64,"c"*64)
                with self.assertRaises(ValueError):read_json(path,sha256(payload).hexdigest(),65536)

    def test_automatic_adapter_does_not_guess_unknown_names_or_parent_topology(self):
        _,_,source,_,_=contract()
        for value in (source,{"bones":[{"name":f"Unknown{i}","parent":None} for i in range(76)]}):
            with self.assertRaises(ValidationError):measured_body_profile(value,"a"*64,"b"*64,"c"*64)

    def test_native_job_requires_exact_bound_inputs_and_literal_render_flag(self):
        options={k:"a"*64 for k in ("source_sha256","snapshot_sha256","mapping_sha256","master_sha256")}
        options["render_private_frames"]=False
        JobRequest.new("verify_native_fbx_body",input_project="candidate.blend",options=options)
        for bad in ({**options,"render_private_frames":1},{**options,"path":"arbitrary"},{**options,"master_sha256":None}):
            with self.assertRaises(ValidationError):JobRequest.new("verify_native_fbx_body",input_project="candidate.blend",options=bad)
        with self.assertRaises(ValidationError):JobRequest.new("verify_native_fbx_body",options=options)


class NativeEvidenceTests(unittest.TestCase):
    def check(self,data,report,source,profile,bindings):
        return validate_native_timeline(data,report,source,profile,bindings)

    def test_complete_pose_skin_root_evidence_contract(self):
        args=contract();self.assertIs(self.check(*args),args[0])

    def test_summary_flags_missing_frames_bind_strain_and_omissions_reject(self):
        for case in ("approval","binding","count","missing","frame","hash","strain","bind_strain","helpers","omitted","reference","calibration","root_speed","root_frame","skin_probe","bind_hash"):
            data,report,source,profile,bindings=contract()
            if case=="approval":report["retargeting_verified"]=True
            if case=="binding":report["bindings"]={**bindings,"mapping_sha256":"e"*64}
            if case=="count":report["mapped_bone_count"]=True
            if case=="missing":data["full_timeline_frames"].pop()
            if case=="frame":data["full_timeline_frames"][-1]["source_frame"]=1
            if case=="hash":data["full_timeline_frames"][-1]["target_pose_sha256"]="f"*64
            if case=="strain":data["full_timeline_frames"][-1]["max_edge_stretch_ratio"]=4.01
            if case=="bind_strain":data["bind_relative_frames"][-1]["min_edge_length_ratio"]=.01
            if case=="helpers":data["neutral_target_helpers"]=[["not a bone name"]]
            if case=="omitted":data["omitted_source_bones"]=["unreported"]
            if case=="reference":data["reference_proofs"][1]["source_segment"]=[1.,0.,0.]
            if case=="calibration":data["root_motion_scale"]=2.
            if case=="root_speed":data["root_motion_metrics"]["max_speed_world"]=0.
            if case=="root_frame":data["root_motion_metrics"]["max_rotation_step_frame"]=99
            if case=="skin_probe":data["deformation_probes"][0]["moved_vertices"]=0
            if case=="bind_hash":data["neutral_bind_skin_sha256"]="unbound"
            with self.subTest(case=case),self.assertRaises(ValidationError):self.check(data,report,source,profile,bindings)

    def test_rehashed_actual_target_rotation_still_must_implement_source_conversion(self):
        import math
        data,report,source,profile,bindings=contract();row=data["full_timeline_frames"][-1]
        pose=row["target_global_poses"][-1];angle=math.radians(10)
        pose[0]=pose[5]=math.cos(angle);pose[1]=-math.sin(angle);pose[4]=math.sin(angle)
        row["target_pose_sha256"]=digest(data["target_armature_world"],row["target_global_poses"])
        with self.assertRaisesRegex(ValidationError,"source bind/pose conversion"):self.check(data,report,source,profile,bindings)

    def test_rehashed_root_pose_cannot_silently_discard_source_displacement(self):
        data,report,source,profile,bindings=contract();row=data["full_timeline_frames"][-1]
        row["target_global_poses"][0][3]=0.;row["root_world_head"][0]=0.
        row["target_pose_sha256"]=digest(data["target_armature_world"],row["target_global_poses"])
        with self.assertRaisesRegex(ValidationError,"root displacement"):self.check(data,report,source,profile,bindings)

    def test_source_animated_scale_translation_or_first_pose_cannot_be_hidden_by_summary(self):
        for case in ("translation","scale","initial_pose"):
            data,report,source,profile,bindings=contract();row=source["frames"][0]
            if case=="translation":row["poses"][0][3]+=.1
            if case=="scale":row["armature_world"][0]=row["armature_world"][5]=row["armature_world"][10]=2.
            if case=="initial_pose":
                row["poses"][0][0]=row["poses"][0][5]=0.
                row["poses"][0][1]=-1.;row["poses"][0][4]=1.
            row["pose_sha256"]=digest(row["armature_world"],row["poses"])
            with self.subTest(case=case),self.assertRaises(ValidationError):self.check(data,report,source,profile,bindings)

    def test_private_timeline_and_blend_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);data,report,source,profile,bindings=contract()
            blend=b"BLENDER"+b"SYNTHETIC_UNIT_ONLY"*1000
            (folder/"review_motion.blend").write_bytes(blend)
            action={"name":"review_motion.blend","bytes":len(blend),"sha256":sha256(blend).hexdigest()}
            data["visual_review_blend"]=report["visual_review_blend"]=action
            payload=json.dumps(data).encode();(folder/"target_timeline.json").write_bytes(payload)
            report["timeline"]={"name":"target_timeline.json","bytes":len(payload),"sha256":sha256(payload).hexdigest()}
            read_native_timeline(folder,report,source,profile,bindings)
            (folder/"review_motion.blend").write_bytes(blend+b"tampered")
            with self.assertRaises(ValidationError):read_native_timeline(folder,report,source,profile,bindings)

    def test_affine_inverse_and_bounded_target_noise_do_not_allow_shear_reflections(self):
        transform=rows([2.,0,0,3,0,2.,0,4,0,0,2.,5,0,0,0,1])
        identity=product(transform,inverse(transform))
        self.assertLess(max(abs(identity[i][j]-(i==j)) for i in range(4) for j in range(4)),1e-12)
        for value in (-1.,0.):
            m=[1.,0,0,0,0,1.,0,0,0,0,1.,0,0,0,0,1.];m[0]=value
            with self.assertRaises(ValidationError):rotation(m,target_noise=True)
        m=[1.,.00002,0,0,0,1.,0,0,0,0,1.,0,0,0,0,1.]
        _,correction=rotation(m,target_noise=True);self.assertGreater(correction,0.)
        m[1]=.01
        with self.assertRaises(ValidationError):rotation(m,target_noise=True)
