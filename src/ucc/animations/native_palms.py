"""Explicit palm-plane declarations and independent source geometry checks."""
import math
from ucc.core.errors import ValidationError

PALM_AXES = {"PALM_LEFT_V1":"left", "PALM_RIGHT_V1":"right"}


def validate_palm_profile(profile: dict) -> None:
    used={PALM_AXES[p["secondary"]] for p in profile["pairs"] if p["secondary"] in PALM_AXES}
    if not used:
        if "hand_reference_planes" in profile:raise ValidationError("Unused palm reference declaration")
        return
    planes=profile.get("hand_reference_planes")
    if (profile.get("skin_deformation_policy")!="BOUND_CORRECTIVE_SMOOTH_V1" or
            type(planes) is not dict or set(planes)!={"schema_version","planes"} or
            type(planes["schema_version"]) is not int or planes["schema_version"]!=1 or
            type(planes["planes"]) is not dict or set(planes["planes"])!=used):
        raise ValidationError("Palm references need an exact versioned declaration and saved-skin reopening")
    mapped={r["source"]:r["target"] for r in profile["pairs"]}
    selected=set()
    body_sources={"@ARMATURE",*(r["source"] for r in profile["landmarks"].values())}
    if any(r["secondary"] in PALM_AXES and r["source"] in body_sources for r in profile["pairs"]):
        raise ValidationError("Palm secondary axes apply strictly below the body landmarks")
    for side,plane in planes["planes"].items():
        if type(plane) is not dict or set(plane)!={"index","pinky"}:
            raise ValidationError("Palm reference needs explicit index and pinky knuckles")
        for pair in plane.values():
            if (type(pair) is not dict or set(pair)!={"source","target"} or
                    type(pair["source"]) is not str or type(pair["target"]) is not str or
                    mapped.get(pair["source"])!=pair["target"] or pair["source"] in body_sources or
                    pair["source"] in selected):
                raise ValidationError("Palm knuckles must be distinct explicitly mapped non-body joints")
            selected.add(pair["source"])


def validate_palm_hierarchy(profile: dict, parents: dict, domain: str) -> None:
    def branch(name: str, wrist: str) -> str:
        seen=set()
        while name!=wrist and name in parents and name not in seen:
            seen.add(name)
            if parents[name]==wrist:return name
            name=parents[name]
        raise ValidationError("Palm landmark/joint is not strictly below its declared wrist")
    for side,plane in profile.get("hand_reference_planes",{}).get("planes",{}).items():
        wrist=profile["landmarks"][side+"_hand"][domain]
        if branch(plane["index"][domain],wrist)==branch(plane["pinky"][domain],wrist):
            raise ValidationError("Palm knuckles must belong to different wrist branches")
        for pair in profile["pairs"]:
            if PALM_AXES.get(pair["secondary"])==side:branch(pair[domain],wrist)


def palm_normal(points: dict, height: float) -> list[float]:
    if type(height) not in (int,float) or not .01<height<1e5:
        raise ValidationError("Invalid body height for palm geometry")
    if type(points) is not dict or set(points)!={"wrist","index","pinky"}:
        raise ValidationError("Incomplete palm corner geometry")
    for p in points.values():
        if (type(p) is not list or len(p)!=3 or
                any(type(v) not in (int,float) or not -1e6<=v<=1e6 for v in p)):
            raise ValidationError("Invalid finite palm corner")
    rays=[]
    for key in ("index","pinky"):
        v=[points[key][i]-points["wrist"][i] for i in range(3)]
        size=math.sqrt(sum(x*x for x in v))
        if not .005*height<size<.3*height:raise ValidationError("Palm ray length is incompatible with body height")
        rays.append([x/size for x in v])
    a,b=rays
    if abs(sum(x*y for x,y in zip(a,b)))>=.99:raise ValidationError("Palm rays are nearly collinear")
    normal=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    size=math.sqrt(sum(x*x for x in normal))
    return [v/size for v in normal]


def palm_evidence(data: dict, profile: dict, source_points: dict, source_parents: dict,
                  target_landmarks: dict, source_height: float, target_height: float) -> dict:
    validate_palm_profile(profile)
    declaration=profile.get("hand_reference_planes")
    if declaration is None:
        if "hand_plane_proofs" in data:raise ValidationError("Undeclared palm geometry in legacy evidence")
        return {}
    validate_palm_hierarchy(profile,source_parents,"source")
    proof=data.get("hand_plane_proofs")
    if (type(proof) is not dict or set(proof)!={"schema_version","planes"} or
            type(proof["schema_version"]) is not int or proof["schema_version"]!=1 or
            type(proof["planes"]) is not dict or set(proof["planes"])!=set(declaration["planes"])):
        raise ValidationError("Missing closed palm-plane proof")
    result={}
    for side,plane in declaration["planes"].items():
        row=proof["planes"][side]
        if type(row) is not dict or set(row)!={"target_points","source_normal","target_normal"}:
            raise ValidationError("Invalid palm-plane proof fields")
        sp={"wrist":source_points[profile["landmarks"][side+"_hand"]["source"]],
            **{k:source_points[p["source"]] for k,p in plane.items()}}
        sn=palm_normal(sp,source_height);tn=palm_normal(row["target_points"],target_height)
        if max(abs(a-b) for a,b in zip(row["target_points"]["wrist"],target_landmarks[side+"_hand"]))>1e-6:
            raise ValidationError("Palm wrist corner differs from anatomical landmark")
        for key,normal in (("source_normal",sn),("target_normal",tn)):
            value=row[key]
            if (type(value) is not list or len(value)!=3 or
                    any(type(v) not in (int,float) or not -1.000001<=v<=1.000001 for v in value) or
                    max(abs(a-b) for a,b in zip(value,normal))>1e-6):
                raise ValidationError("Palm normal differs from actual declared rest geometry")
        result[side]=(sn,tn)
    return result
