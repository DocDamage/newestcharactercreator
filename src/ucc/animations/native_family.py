"""Narrow measured Hips-object family adapter, never filename/alias guessing."""
from hashlib import sha256
import json

from ucc.core.errors import ValidationError
from .native_profile import CONVENTION, validate_native_profile

# Metadata fingerprint only: no purchased rest/pose data or assets are bundled.
# Measured on all 30 authorized local sources; positions/axes/skin compatibility
# are independently checked for every individual clip and target by the worker.
HIPS_OBJECT_TOPOLOGY = "37e1bed9064939b9e60010c88f3499efefd22dcfbbbacb2f2b3ece9de7f32405"


def measured_body_profile(source,source_sha,snapshot_sha,master_sha):
    bones=source.get("bones")
    if (type(bones) is not list or len(bones)!=76 or any(type(b) is not dict or type(b.get("name")) is not str or
            (b.get("parent") is not None and type(b["parent"]) is not str) or "parent" not in b for b in bones) or
            len({b["name"] for b in bones})!=76):
        raise ValidationError("This FBX skeleton has no supported automatic body map; a reviewed explicit map is required")
    topology=json.dumps(sorted((b["name"],b["parent"]) for b in bones),separators=(",",":"))
    if sha256(topology.encode()).hexdigest()!=HIPS_OBJECT_TOPOLOGY:
        raise ValidationError("This FBX skeleton differs from the measured Hips-object family; no automatic aliases were applied")
    pairs=[("@ARMATURE","root",None,None,"BODY"),
           ("Spine1","spine05","Spine2","spine03","FORWARD"),
           ("Spine2","spine03","Chest","spine01","FORWARD"),
           ("Chest","spine01","Neck1","neck01","FORWARD"),
           ("Neck1","neck01","Neck2","neck02","FORWARD"),
           ("Neck2","neck02","Head","head","FORWARD"),
           ("Head","head","HeadEnd",None,"FORWARD")]
    for side,suffix in (("Left",".L"),("Right",".R")):
        pairs.extend([(side+"Shoulder","clavicle"+suffix,side+"Arm","upperarm01"+suffix,"FORWARD"),
            (side+"Arm","upperarm01"+suffix,side+"ForeArm","lowerarm01"+suffix,"FORWARD"),
            (side+"ForeArm","lowerarm01"+suffix,side+"Hand","wrist"+suffix,"FORWARD"),
            (side+"Hand","wrist"+suffix,side+"HandMiddle1","finger3-1"+suffix,"FORWARD"),
            (side+"Leg","upperleg01"+suffix,side+"Shin","lowerleg01"+suffix,"FORWARD"),
            (side+"Shin","lowerleg01"+suffix,side+"Foot","foot"+suffix,"FORWARD"),
            (side+"Foot","foot"+suffix,side+"ToeBase","toe3-1"+suffix,"UP")])
    landmarks={key:{"source":a,"target":b} for key,a,b in (
        ("left_hip","LeftLeg","upperleg01.L"),("right_hip","RightLeg","upperleg01.R"),
        ("head","Head","head"),("left_hand","LeftHand","wrist.L"),("right_hand","RightHand","wrist.R"),
        ("left_foot","LeftFoot","foot.L"),("right_foot","RightFoot","foot.R"))}
    profile={"schema_version":1,"convention":CONVENTION,"source_sha256":source_sha,"root_motion_policy":"SOURCE_HIP_MIDPOINT_V1",
             "skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1",
             "snapshot_sha256":snapshot_sha,"master_sha256":master_sha,"landmarks":landmarks,
             "pairs":[dict(zip(("source","target","source_tip","target_tip","secondary"),row)) for row in pairs]}
    return validate_native_profile(profile,source_sha,snapshot_sha,master_sha)
