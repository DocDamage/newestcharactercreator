"""Invented boundary-only palm geometry, never Blender/owned-motion evidence."""
from copy import deepcopy
from fixtures.native_body_contract import contract


def palm_contract():
    _,_,source,profile,_=contract()
    profile["skin_deformation_policy"]="BOUND_CORRECTIVE_SMOOTH_V1"
    declarations={};proofs={};sp={b["name"]:b["head"][:] for b in source["bones"]}
    parents={b["name"]:b["parent"] for b in source["bones"]};tp={};target_parents={}
    for side in ("left","right"):
        wrist=profile["landmarks"][side+"_hand"]
        origin=sp[wrist["source"]]
        tp[wrist["target"]]=origin[:]
        plane={};corners={"wrist":origin[:]}
        for key,offset in (("index",(.05,-.06,0.)),("pinky",(-.025,-.06,0.))):
            s,t=side+"_"+key,"target_"+side+"_"+key
            plane[key]={"source":s,"target":t}
            point=[origin[i]+offset[i] for i in range(3)]
            sp[s]=point;tp[t]=point[:];corners[key]=point[:]
            parents[s]=wrist["source"];target_parents[t]=wrist["target"]
            profile["pairs"].append({"source":s,"target":t,"source_tip":None,"target_tip":None,"secondary":"PALM_"+side.upper()+"_V1"})
        declarations[side]=plane
        proofs[side]={"target_points":corners,"source_normal":[0.,0.,-1.],"target_normal":[0.,0.,-1.]}
    profile["hand_reference_planes"]={"schema_version":1,"planes":declarations}
    data={"hand_plane_proofs":{"schema_version":1,"planes":proofs}}
    landmarks={k:sp[v["source"]][:] for k,v in profile["landmarks"].items()}
    return profile,data,sp,tp,parents,target_parents,landmarks
