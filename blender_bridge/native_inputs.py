"""Independent bounded parsing of staged native snapshots and explicit maps."""
from hashlib import sha256
import json
import math
from pathlib import Path

from blender_bridge.fbx_source import IMPORT_OPTIONS, CONVENTION as SOURCE_CONVENTION, matrix_values, pose_digest
from blender_bridge.native_reference import CONVENTION

LANDMARKS = {"left_hip","right_hip","head","left_hand","right_hand","left_foot","right_foot"}


def read_json(path: Path, digest: str, maximum: int):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError("Missing, redirected or oversized native input")
    with path.open("rb") as stream: payload = stream.read(maximum+1)
    if len(payload) > maximum or sha256(payload).hexdigest() != digest:
        raise ValueError("Native input SHA-256 differs")
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result: raise ValueError("Duplicate native input key")
            result[key] = value
        return result
    def nonfinite(value): raise ValueError("Nonfinite native input")
    try:
        result=json.loads(payload,object_pairs_hook=unique,parse_constant=nonfinite)
        if type(result) is not dict:raise ValueError("Native input must be a JSON object")
        return result
    except (ValueError,UnicodeError,RecursionError) as exc: raise ValueError("Invalid native input JSON") from exc


def name(v):
    return type(v) is str and 0 < len(v) <= 128 and all(c.isprintable() for c in v)


def vector(v, count):
    if type(v) is not list or len(v) != count or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in v):
        raise ValueError("Invalid bounded native vector")


def matrix(v):
    vector(v,16)
    return matrix_values([v[i:i+4] for i in range(0,16,4)])


def validate_source(data, source_sha):
    if (type(data) is not dict or set(data) != {"schema_version","convention","source_sha256","blender_version",
            "import_options","rest_import_options","armature_rest_world","action","fps","first_frame","last_frame",
            "bones","frames","retargeting_verified","animation_visual_quality_verified","engine_import_verified"} or
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["convention"] != SOURCE_CONVENTION or
            data["source_sha256"] != source_sha or
            json.dumps(data["import_options"],sort_keys=True) != json.dumps(IMPORT_OPTIONS,sort_keys=True) or
            json.dumps(data["rest_import_options"],sort_keys=True) != json.dumps({**IMPORT_OPTIONS,"use_anim":False},sort_keys=True) or
            type(data["action"]) is not str or not 0<len(data["action"])<=512 or not data["action"].isprintable() or
            type(data["blender_version"]) is not str or not 0<len(data["blender_version"])<=64 or not data["blender_version"].isprintable() or
            any(data[f] is not False for f in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified"))):
        raise ValueError("Native source convention/identity differs")
    matrix(data["armature_rest_world"])
    first,last = data["first_frame"],data["last_frame"]
    if (any(type(f) is not int or abs(f)>100000 for f in (first,last)) or not 5 <= last-first+1 <= 2400 or
            type(data["fps"]) not in (int,float) or not math.isfinite(data["fps"]) or not 1<=data["fps"]<=240):
        raise ValueError("Native body preview needs a complete bounded five-frame-or-longer source")
    bones,frames = data["bones"],data["frames"]
    if (type(bones) is not list or not 1<=len(bones)<=256 or len(bones)*(last-first+1)>100000 or
            type(frames) is not list or len(frames)!=last-first+1):
        raise ValueError("Native source skeleton/frame count differs")
    seen,folded = set(),set()
    for bone in bones:
        if (type(bone) is not dict or set(bone)!={"name","parent","head","tail","matrix"} or not name(bone["name"]) or bone["name"]=="@ARMATURE" or
                bone["name"].casefold() in folded or (bone["parent"] is not None and bone["parent"] not in seen)):
            raise ValueError("Invalid native bone name/parent ordering")
        vector(bone["head"],3);vector(bone["tail"],3);matrix(bone["matrix"])
        direction=[bone["tail"][i]-bone["head"][i] for i in range(3)]
        axis=[bone["matrix"][i*4+1] for i in range(3)]
        length=sum(v*v for v in direction)**.5
        if (length<1e-7 or any(abs(bone["head"][i]-bone["matrix"][i*4+3])>1e-5 for i in range(3)) or
                sum(a*b for a,b in zip(direction,axis))/(length*sum(v*v for v in axis)**.5)<.99999):
            raise ValueError("Native source rest endpoints and matrix disagree")
        seen.add(bone["name"]);folded.add(bone["name"].casefold())
    hashes=set()
    for frame,row in enumerate(frames,first):
        if (type(row) is not dict or set(row)!={"frame","armature_world","poses","pose_sha256"} or
                type(row["frame"]) is not int or row["frame"]!=frame or type(row["poses"]) is not list or len(row["poses"])!=len(bones)):
            raise ValueError("Native source pose coverage differs")
        matrix(row["armature_world"])
        for pose in row["poses"]: matrix(pose)
        digest=pose_digest(row["armature_world"],row["poses"])
        if digest!=row["pose_sha256"]: raise ValueError("Native source pose digest differs")
        hashes.add(digest)
    if len(hashes)<2: raise ValueError("Native source contains no measured motion")
    return data


def validate_profile(data, source_sha, snapshot_sha, master_sha):
    if (type(data) is not dict or set(data)-{"root_motion_policy","skin_deformation_policy","mesh_strain_reference"}!={"schema_version","convention","source_sha256","snapshot_sha256","master_sha256","landmarks","pairs"} or
            type(data["schema_version"]) is not int or data["schema_version"]!=1 or data["convention"]!=CONVENTION or
            any(data[k]!=v for k,v in (("source_sha256",source_sha),("snapshot_sha256",snapshot_sha),("master_sha256",master_sha)))):
        raise ValueError("Native map convention/binding differs")
    if "root_motion_policy" in data and (type(data["root_motion_policy"]) is not str or data["root_motion_policy"] not in {"ARMATURE_ORIGIN_DISPLACEMENT_V1", "SOURCE_HIP_MIDPOINT_V1"}):
        raise ValueError("Invalid explicit native root-motion policy")
    if "skin_deformation_policy" in data and (type(data["skin_deformation_policy"]) is not str or data["skin_deformation_policy"] not in {"MASTER_MODIFIERS_V1","BOUND_CORRECTIVE_SMOOTH_V1"}):
        raise ValueError("Invalid explicit native skin-deformation policy")
    if "mesh_strain_reference" in data and (type(data["mesh_strain_reference"]) is not str or data["mesh_strain_reference"] not in {"FIRST_POSE_AND_NEUTRAL_V1","TRUE_NEUTRAL_BIND_V2"}):
        raise ValueError("Invalid explicit native mesh-strain reference")
    pairs=data["pairs"]
    if type(pairs) is not list or not 15<=len(pairs)<=64: raise ValueError("Native map needs 15–64 explicit pairs")
    sources,targets,exact=set(),set(),{}
    for index,row in enumerate(pairs):
        if (type(row) is not dict or set(row)!={"source","target","source_tip","target_tip","secondary"} or
                any(not name(row[k]) for k in ("source","target")) or row["target"].startswith("@") or
                row["source"].casefold() in sources or row["target"].casefold() in targets or
                any(v is not None and not name(v) for v in (row["source_tip"],row["target_tip"]))):
            raise ValueError("Invalid native map names/tips")
        if index==0:
            if row["source"]!="@ARMATURE" or row["secondary"]!="BODY" or row["source_tip"] is not None or row["target_tip"] is not None:
                raise ValueError("Native map must start at the armature object")
        elif row["source"].startswith("@") or type(row["secondary"]) is not str or row["secondary"] not in {"UP","FORWARD"}: raise ValueError("Invalid native anatomical axes")
        sources.add(row["source"].casefold());targets.add(row["target"].casefold());exact[row["source"]]=row["target"]
    landmarks=data["landmarks"]
    if type(landmarks) is not dict or set(landmarks)!=LANDMARKS: raise ValueError("Incomplete native anatomical landmarks")
    for row in landmarks.values():
        if (type(row) is not dict or set(row)!={"source","target"} or not name(row["source"]) or not name(row["target"]) or
                row["source"]=="@ARMATURE" or exact.get(row["source"])!=row["target"]): raise ValueError("Native landmark/pair mismatch")
    if len({r["source"] for r in landmarks.values()})!=len(LANDMARKS): raise ValueError("Native landmarks must be distinct")
    return data
