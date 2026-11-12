"""Closed-form pivot tests and synthetic evidence faults, never asset acceptance."""
from copy import deepcopy
import math
from types import SimpleNamespace
import unittest

from blender_bridge.native_anchor import root_position, validate_target_chain, POLICY
from blender_bridge.native_inputs import validate_profile as worker_profile
from fixtures.native_body_contract import contract, digest
from ucc.animations import native_math as nm
from ucc.animations.native_profile import validate_native_profile
from ucc.core.errors import ValidationError
from ucc.jobs.native_evidence import validate_native_timeline

IDENTITY = [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
QUARTER = [[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]]


def anchored_contract():
    data, report, source, profile, bindings = contract()
    profile["root_motion_policy"] = POLICY
    data.update(root_motion_policy=POLICY, hip_anchor={"source_bind_midpoint_world":[0.,0.,1.],
        "target_bind_midpoint_world":[0.,0.,1.],"frames_measured":5,"max_residual_world":0.,
        "source_bones":[profile["landmarks"][k]["source"] for k in ("left_hip","right_hip")],
        "target_bones":[profile["landmarks"][k]["target"] for k in ("left_hip","right_hip")]})
    roots=[]
    for i,(src,row) in enumerate(zip(source["frames"],data["full_timeline_frames"])):
        angle=i*.02;c,s=math.cos(angle),math.sin(angle)
        world=[[1.,0.,0.,i*.01],[0.,c,-s,0.],[0.,s,c,0.],[0.,0.,0.,1.]]
        src["armature_world"]=[v for line in world for v in line]
        src["pose_sha256"]=digest(src["armature_world"],src["poses"])
        root=nm.product(world,nm.rows([1.,0,0,0,0,1.,0,0,0,0,1.,1,0,0,0,1.]))
        actual=[[v for line in root for v in line]]
        actual.extend([v for line in nm.product(world,nm.rows(b["matrix"])) for v in line] for b in source["bones"])
        row["target_global_poses"]=actual;row["target_pose_sha256"]=digest(data["target_armature_world"],actual)
        point=[root[j][3] for j in range(3)];roots.append(point)
        row["root_world_head"]=point;row["hip_midpoint_world"]=point[:]
        row["root_speed_world"]=0. if i==0 else math.dist(point,roots[-2])*source["fps"]
    speeds=[r["root_speed_world"] for r in data["full_timeline_frames"]]
    data["root_motion_metrics"].update(max_speed_world=max(speeds),max_speed_frame=speeds.index(max(speeds))+1,
        max_step_distance_world=max(speeds)/source["fps"],max_distance_from_bind_world=max(math.dist(p,[0,0,1]) for p in roots),
        max_rotation_step_degrees=math.degrees(.02),max_rotation_step_frame=2)
    return data,report,source,profile,bindings


class NativeAnchorTests(unittest.TestCase):
    def test_hip_origin_source_rotates_target_floor_root_around_hips(self):
        root,hip=root_position((0,0,1),(0,0,1),(0,0,1),(0,0,0),IDENTITY,1.,IDENTITY,QUARTER)
        self.assertEqual(hip,(0.,0.,1.))
        self.assertEqual(root,(0.,1.,1.))

    def test_floor_origin_source_retains_floor_pivot_and_translated_hip_path(self):
        root,hip=root_position((0,0,1),(2,-1,0),(0,0,1),(0,0,0),IDENTITY,1.,IDENTITY,QUARTER)
        self.assertEqual(hip,(2.,-1.,0.))
        self.assertEqual(root,(2.,0.,0.))

    def test_nonzero_target_bind_roll_is_removed_before_pivoting(self):
        root,hip=root_position((0,0,2),(1,0,2),(0,0,1),(0,0,0),IDENTITY,.5,QUARTER,QUARTER)
        self.assertEqual(root,(.5,0.,0.));self.assertEqual(hip,(.5,0.,1.))

    def test_independent_all_frame_hip_and_root_positions_validate(self):
        args=anchored_contract()
        self.assertIs(validate_native_timeline(*args),args[0])

    def test_rehashed_legacy_pivot_and_hip_translation_forgery_reject(self):
        for fault in ("old_pivot","hip","reported","summary","bind","missing","unrequested"):
            data,report,source,profile,bindings=anchored_contract()
            row=data["full_timeline_frames"][-1]
            if fault=="old_pivot":
                delta=[.04-row["root_world_head"][0],-row["root_world_head"][1],1.-row["root_world_head"][2]]
                for pose in row["target_global_poses"]:
                    for i in range(3):pose[i*4+3]+=delta[i]
                row["root_world_head"]=[.04,0.,1.];row["hip_midpoint_world"]=[.04,0.,1.]
            if fault=="hip":row["target_global_poses"][1][3]+=.01
            if fault=="reported":row["hip_midpoint_world"][0]+=.01
            if fault=="summary":data["hip_anchor"]["max_residual_world"] = .00005
            if fault=="bind":data["hip_anchor"]["target_bind_midpoint_world"][2]+=.01
            if fault=="missing":del data["hip_anchor"]
            if fault=="unrequested":del profile["root_motion_policy"]
            row["target_pose_sha256"]=digest(data["target_armature_world"],row["target_global_poses"])
            with self.subTest(fault=fault),self.assertRaises(ValidationError):
                validate_native_timeline(data,report,source,profile,bindings)

    def test_legacy_profiles_remain_valid_and_unknown_policy_never_guessed(self):
        data,report,source,profile,bindings=contract()
        validate_native_timeline(data,report,source,profile,bindings)
        for value in (POLICY,"ARMATURE_ORIGIN_DISPLACEMENT_V1", "AUTO", None, [POLICY], True):
            p=deepcopy(profile);p["root_motion_policy"]=value
            if type(value) is str and value in {POLICY,"ARMATURE_ORIGIN_DISPLACEMENT_V1"}:
                validate_native_profile(p,"a"*64,"b"*64,"c"*64);worker_profile(p,"a"*64,"b"*64,"c"*64)
            else:
                with self.assertRaises(ValidationError):validate_native_profile(p,"a"*64,"b"*64,"c"*64)
                with self.assertRaises(ValueError):worker_profile(p,"a"*64,"b"*64,"c"*64)

    def test_mapped_pelvis_or_nonstandard_inheritance_reject_anchor_policy(self):
        def bone(name,parent=None):return SimpleNamespace(name=name,parent=parent,use_inherit_rotation=True,inherit_scale="FULL")
        root=bone("root");helper=bone("pelvis",root);left=bone("left",helper);right=bone("right",root)
        rig=SimpleNamespace(data=SimpleNamespace(bones={b.name:b for b in (root,helper,left,right)}))
        pairs=[{"target":n} for n in ("root","left","right")]
        landmarks={"left_hip":{"target":"left"},"right_hip":{"target":"right"}}
        validate_target_chain(rig,pairs,landmarks)
        with self.assertRaises(ValueError):validate_target_chain(rig,pairs+[{"target":"pelvis"}],landmarks)
        helper.use_inherit_rotation=False
        with self.assertRaises(ValueError):validate_target_chain(rig,pairs,landmarks)
