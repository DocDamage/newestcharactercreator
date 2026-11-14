"""Blender-side palm declaration, branch and actual rest-geometry verification."""
import math

PALM_AXES={"PALM_LEFT_V1":"left","PALM_RIGHT_V1":"right"}


def validate_palm_profile(profile: dict) -> None:
    used={PALM_AXES[r["secondary"]] for r in profile["pairs"] if r["secondary"] in PALM_AXES}
    if not used:
        if "hand_reference_planes" in profile:raise ValueError("Unused native palm declaration")
        return
    declaration=profile.get("hand_reference_planes")
    if (profile.get("skin_deformation_policy")!="BOUND_CORRECTIVE_SMOOTH_V1" or
            type(declaration) is not dict or set(declaration)!={"schema_version","planes"} or
            type(declaration["schema_version"]) is not int or declaration["schema_version"]!=1 or
            type(declaration["planes"]) is not dict or set(declaration["planes"])!=used):
        raise ValueError("Native palm axes require versioned planes and independent corrective-skin reopening")
    mapping={r["source"]:r["target"] for r in profile["pairs"]}
    selected=set();body={"@ARMATURE",*(r["source"] for r in profile["landmarks"].values())}
    if any(r["secondary"] in PALM_AXES and r["source"] in body for r in profile["pairs"]):
        raise ValueError("Native palm axes cannot replace body/wrist landmark references")
    for plane in declaration["planes"].values():
        if type(plane) is not dict or set(plane)!={"index","pinky"}:raise ValueError("Missing declared palm knuckles")
        for row in plane.values():
            if (type(row) is not dict or set(row)!={"source","target"} or
                    type(row["source"]) is not str or type(row["target"]) is not str or
                    mapping.get(row["source"])!=row["target"] or row["source"] in body or row["source"] in selected):
                raise ValueError("Native palm landmarks must be distinct mapped non-body pairs")
            selected.add(row["source"])


def check_branches(profile: dict, parents: dict, domain: str) -> None:
    def child(name,root):
        visited=set()
        while name in parents and name!=root and name not in visited:
            visited.add(name)
            if parents[name]==root:return name
            name=parents[name]
        raise ValueError("Native palm joint/knuckle is not a strict wrist descendant")
    for side,plane in profile.get("hand_reference_planes",{}).get("planes",{}).items():
        root=profile["landmarks"][side+"_hand"][domain]
        if child(plane["index"][domain],root)==child(plane["pinky"][domain],root):
            raise ValueError("Native palm knuckles occupy the same wrist branch")
        for pair in profile["pairs"]:
            if PALM_AXES.get(pair["secondary"])==side:child(pair[domain],root)


def normal(points: dict, height: float) -> list[float]:
    if type(height) not in (int,float) or not .01<height<1e5:raise ValueError("Invalid palm body height")
    if type(points) is not dict or set(points)!={"wrist","index","pinky"}:raise ValueError("Missing native palm corners")
    if any(type(p) is not list or len(p)!=3 or any(type(v) not in (int,float) or not -1e6<=v<=1e6 for v in p) for p in points.values()):
        raise ValueError("Invalid finite native palm corner")
    vectors=[]
    for key in ("index","pinky"):
        ray=[float(points[key][i])-float(points["wrist"][i]) for i in range(3)]
        size=math.sqrt(sum(x*x for x in ray))
        if not .005*height<size<.3*height:raise ValueError("Native palm length is incompatible with body proportions")
        vectors.append([v/size for v in ray])
    a,b=vectors
    if abs(sum(x*y for x,y in zip(a,b)))>=.99:raise ValueError("Native palm landmarks are nearly collinear")
    result=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    size=math.sqrt(sum(v*v for v in result))
    return [v/size for v in result]


def measure_planes(profile: dict, source_points: dict, target_points: dict,
                   source_parents: dict, target_parents: dict, source_height: float, target_height: float) -> dict | None:
    validate_palm_profile(profile)
    declaration=profile.get("hand_reference_planes")
    if declaration is None:return None
    for parents,domain in ((source_parents,"source"),(target_parents,"target")):
        check_branches(profile,parents,domain)
    planes={}
    for side,plane in declaration["planes"].items():
        measured={}
        for domain,points,height in (("source",source_points,source_height),("target",target_points,target_height)):
            corners={"wrist":list(points[profile["landmarks"][side+"_hand"][domain]]),
                     **{key:list(points[row[domain]]) for key,row in plane.items()}}
            measured[domain]=(corners,normal(corners,height))
        planes[side]={"target_points":measured["target"][0],"source_normal":measured["source"][1],"target_normal":measured["target"][1]}
    return {"schema_version":1,"planes":planes}


def reopen_planes(profile: dict, source: dict, rig, timeline: dict) -> int:
    """Recompute from the actual original/reopened rig, never from pose evidence."""
    if "hand_reference_planes" not in profile:
        if "hand_plane_proofs" in timeline:raise ValueError("Undeclared saved palm proof")
        return 0
    from mathutils import Matrix,Vector
    from blender_bridge.native_reference import body_frame
    sw=Matrix([source["armature_rest_world"][i:i+4] for i in range(0,16,4)])
    sp={b["name"]:sw@Vector(b["head"]) for b in source["bones"]}
    tp={b.name:rig.matrix_world@b.head_local for b in rig.data.bones}
    sh=body_frame(*(tuple(sp[profile["landmarks"][k]["source"]]) for k in ("left_hip","right_hip","head")))[1]
    th=body_frame(*(tuple(tp[profile["landmarks"][k]["target"]]) for k in ("left_hip","right_hip","head")))[1]
    expected=measure_planes(profile,sp,tp,{b["name"]:b["parent"] for b in source["bones"]},
        {b.name:b.parent.name if b.parent else None for b in rig.data.bones},sh,th)
    def same(actual,wanted):
        if type(wanted) is not type(actual):return False
        if type(actual) is dict:return set(actual)==set(wanted) and all(same(v,wanted[k]) for k,v in actual.items())
        if type(actual) is list:return len(actual)==len(wanted) and all(same(a,b) for a,b in zip(actual,wanted))
        if type(actual) is float:return math.isfinite(wanted) and abs(actual-wanted)<=1e-7
        return actual==wanted
    if not same(expected,timeline.get("hand_plane_proofs")):
        raise ValueError("Native palm rest geometry differs from actual master/reopened rig")
    return len(expected["planes"])
