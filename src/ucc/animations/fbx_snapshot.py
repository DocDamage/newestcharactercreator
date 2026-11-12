"""Independent pure-Python verification of private native FBX source transforms."""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import struct
from typing import Any

from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256

CONVENTION = "BLENDER_FBX_ARMATURE_POSE_MATRICES_V1"
MAX_SNAPSHOT_BYTES = 64*1024*1024
MAX_SOURCE_BYTES = 256*1024*1024
IMPORT_OPTIONS = {"use_anim": True, "anim_offset": 1., "use_image_search": False,
                  "use_custom_props": False, "automatic_bone_orientation": False,
                  "ignore_leaf_bones": False, "force_connect_children": False,
                  "use_prepost_rot": True, "bake_space_transform": False,
                  "use_manual_orientation": False, "global_scale": 1.}


def _number(v: Any, bound: float = 1e6) -> bool:
    return type(v) in (float,int) and math.isfinite(v) and abs(v) <= bound


def _matrix(v: Any) -> None:
    if type(v) is not list or len(v) != 16 or any(not _number(x) for x in v):
        raise ValidationError("Invalid FBX matrix values")
    if max(abs(v[12+i] - (1 if i == 3 else 0)) for i in range(4)) > 1e-6:
        raise ValidationError("FBX matrix must be affine")
    axes = [[v[r*4+c] for r in range(3)] for c in range(3)]
    lengths = [math.sqrt(sum(x*x for x in a)) for a in axes]
    if any(not 1e-7 < n < 1e4 for n in lengths):
        raise ValidationError("FBX singular or excessive scale")
    axes = [[x/lengths[i] for x in a] for i,a in enumerate(axes)]
    a,b,c = axes
    determinant = a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if determinant < .9999 or any(abs(sum(x*y for x,y in zip(axes[i],axes[j]))) > 1e-4 for i in range(3) for j in range(i)):
        raise ValidationError("FBX reflected or sheared transform")


def _text(v: Any, maximum=128) -> bool:
    return type(v) is str and 0 < len(v) <= maximum and all(ord(c) >= 32 for c in v)


def validate_snapshot(data: Any, source_sha: str, *, cancel_check=lambda: None) -> dict[str, Any]:
    fields = {"schema_version", "convention", "source_sha256", "blender_version", "import_options",
              "action", "fps", "first_frame", "last_frame", "bones", "frames",
              "retargeting_verified", "animation_visual_quality_verified", "engine_import_verified",
              "rest_import_options", "armature_rest_world"}
    if (type(data) is not dict or set(data) != fields or type(data["schema_version"]) is not int or
            data["schema_version"] != 1 or data["convention"] != CONVENTION or
            not is_sha256(source_sha) or data["source_sha256"] != source_sha or
            not _text(data["blender_version"],64) or not _text(data["action"],512) or
            json.dumps(data["import_options"],sort_keys=True) != json.dumps(IMPORT_OPTIONS,sort_keys=True) or
            json.dumps(data["rest_import_options"],sort_keys=True) != json.dumps({**IMPORT_OPTIONS,"use_anim":False},sort_keys=True) or
            not _number(data["fps"],240) or data["fps"] < 1 or
            any(data[f] is not False for f in ("retargeting_verified", "animation_visual_quality_verified", "engine_import_verified"))):
        raise ValidationError("FBX source identity, convention, importer or approval mismatch")
    _matrix(data["armature_rest_world"])
    first,last = data["first_frame"], data["last_frame"]
    if any(type(f) is not int or abs(f) > 100_000 for f in (first,last)) or not 2 <= last-first+1 <= 2400:
        raise ValidationError("FBX full frame range is out of bounds")
    bones,frames = data["bones"],data["frames"]
    if (type(bones) is not list or not 1 <= len(bones) <= 256 or len(bones)*(last-first+1) > 100_000 or
            type(frames) is not list or len(frames) != last-first+1):
        raise ValidationError("FBX incomplete or oversized skeleton/timeline")
    names,folded,roots = set(),set(),0
    for bone in bones:
        if (type(bone) is not dict or set(bone) != {"name","parent","head","tail","matrix"} or
                not _text(bone["name"]) or bone["name"].casefold() in folded or
                (bone["parent"] is not None and (type(bone["parent"]) is not str or bone["parent"] not in names))):
            raise ValidationError("FBX skeleton names/parents must be unique and ordered")
        _matrix(bone["matrix"])
        for key in ("head","tail"):
            if type(bone[key]) is not list or len(bone[key]) != 3 or any(not _number(x) for x in bone[key]):
                raise ValidationError("Invalid FBX rest endpoints")
        head,tail = bone["head"],bone["tail"]
        if sum((a-b)**2 for a,b in zip(head,tail)) < 1e-14 or any(abs(head[i]-bone["matrix"][i*4+3]) > 1e-5 for i in range(3)):
            raise ValidationError("FBX rest bone matrix/endpoints disagree")
        direction=[tail[i]-head[i] for i in range(3)]
        axis=[bone["matrix"][i*4+1] for i in range(3)]
        cosine=sum(a*b for a,b in zip(direction,axis))/(sum(a*a for a in direction)*sum(a*a for a in axis))**.5
        if cosine < .99999:
            raise ValidationError("FBX rest tail and bone orientation disagree")
        roots += bone["parent"] is None
        names.add(bone["name"])
        folded.add(bone["name"].casefold())
    hashes = set()
    for frame,row in enumerate(frames,first):
        cancel_check()
        if (type(row) is not dict or set(row) != {"frame","armature_world","poses","pose_sha256"} or
                type(row["frame"]) is not int or row["frame"] != frame or type(row["poses"]) is not list or
                len(row["poses"]) != len(bones) or not is_sha256(row["pose_sha256"])):
            raise ValidationError("FBX full-pose coverage or signature missing")
        digest=sha256()
        for matrix in [row["armature_world"],*row["poses"]]:
            _matrix(matrix)
            digest.update(struct.pack("<16q",*(round(v*1_000_000) for v in matrix)))
        if digest.hexdigest() != row["pose_sha256"]:
            raise ValidationError("FBX measured pose signature differs")
        hashes.add(row["pose_sha256"])
    if len(hashes) < 2:
        raise ValidationError("FBX source contains no measured motion")
    return {"bone_count":len(bones),"root_count":roots,"frame_count":len(frames),
            "first_frame":first,"last_frame":last,"fps":data["fps"],"action":data["action"],
            "blender_version":data["blender_version"]}


def read_snapshot(folder: Path, report: Any, source_sha: str, *, cancel_check=lambda: None) -> tuple[dict,Path]:
    if (type(report) is not dict or report.get("status") != "REAL_BLENDER_FBX_SOURCE_SNAPSHOT" or
            report.get("convention") != CONVENTION or report.get("source_sha256") != source_sha or
            any(report.get(f) is not False for f in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified"))):
        raise ValidationError("Missing native FBX source evidence")
    record=report.get("snapshot")
    path=folder/"source_snapshot.json"
    if (type(record) is not dict or set(record) != {"name","bytes","sha256"} or
            record["name"] != path.name or type(record["bytes"]) is not int or
            not 0 < record["bytes"] <= MAX_SNAPSHOT_BYTES or not is_sha256(record["sha256"]) or
            path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]):
        raise ValidationError("Missing/redirected/oversized FBX snapshot")
    with path.open("rb") as stream:
        payload=stream.read(MAX_SNAPSHOT_BYTES+1)
    if len(payload) != record["bytes"] or sha256(payload).hexdigest() != record["sha256"]:
        raise ValidationError("FBX snapshot SHA-256 mismatch")
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError("Duplicate FBX snapshot key")
            result[key]=value
        return result
    def nonfinite(value):
        raise ValueError("Nonfinite FBX number")
    try:
        data=json.loads(payload,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ValidationError("Invalid private FBX snapshot JSON") from exc
    observed=validate_snapshot(data,source_sha,cancel_check=cancel_check)
    if any(type(report.get(k)) is not type(v) or report[k] != v for k,v in observed.items()):
        raise ValidationError("FBX report differs from full measured source snapshot")
    return data,path
