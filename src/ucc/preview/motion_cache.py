"""Bounded actual-skin cache reader. Pure Python; no Blender, Qt or GPU imports."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import zlib

from ucc.core.errors import ValidationError
from ucc.jobs.native_evidence import bound_file
from ucc.jobs.native_skin_evidence import validate_reopen_report
from ucc.animations.source_rest_frames import is_sha256

MAGIC=b"UCCSKN1\0"
MAX_BYTES=256*1024*1024
HASHES={"source_sha256","snapshot_sha256","mapping_sha256","master_sha256","review_sha256","timeline_sha256"}


def _number(v,low,high):return type(v) in (int,float) and math.isfinite(v) and low<=v<=high


def _pairs(rows):
    result={}
    for k,v in rows:
        if k in result:raise ValidationError("Duplicate playback JSON field")
        result[k]=v
    return result


def unpack_frame(packed: bytes, expected: int) -> bytes:
    """Bound decompression before allocation; reject concatenation/trailing data."""
    try:
        decoder=zlib.decompressobj()
        raw=decoder.decompress(packed,expected+1)
        if len(raw)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValidationError("Incomplete, oversized or concatenated playback frame")
        return raw
    except zlib.error as error:raise ValidationError("Corrupted playback compression") from error


@dataclass(frozen=True,slots=True)
class MotionCache:
    """Validated immutable bytes; later disk replacement cannot alter GPU inputs."""
    packed: bytes
    chunks: tuple[tuple[int,int],...]
    hips: tuple[tuple[float,float,float],...]
    world_matrix: tuple[float,...]
    fps: float
    vertex_count: int
    triangle_count: int
    radius: float
    source_first_frame: int=1

    @property
    def frame_count(self):return len(self.chunks)

    def frame(self,index: int) -> tuple[bytes,bytes]:
        if type(index) is not int or not 0<=index<self.frame_count:
            raise ValidationError("Playback frame is outside the complete clip")
        offset,size=self.chunks[index]
        raw=unpack_frame(self.packed[offset:offset+size],12*(self.vertex_count+self.triangle_count))
        return raw[:12*self.vertex_count],raw[12*self.vertex_count:]


def read_motion_cache(folder: Path, report: dict, bindings: dict, timeline: dict, *, cancel_check=lambda:None) -> MotionCache:
    if (type(report) is not dict or type(bindings) is not dict or type(timeline) is not dict or set(report)!={"status","bindings","saved_review_verification","manifest"} or
            report["status"]!="REAL_NATIVE_SKIN_CACHE_EXPORTED" or report["bindings"]!=bindings or
            set(bindings)!=HASHES or any(not is_sha256(v) for v in bindings.values())):
        raise ValidationError("Playback result identity/contract differs")
    validate_reopen_report(report["saved_review_verification"],bindings,timeline)
    path=bound_file(folder,report["manifest"],"motion_skin.json",4*1024*1024,cancel_check=cancel_check)
    with path.open("rb") as stream:payload=stream.read(4*1024*1024+1)
    if len(payload)!=report["manifest"]["bytes"] or sha256(payload).hexdigest()!=report["manifest"]["sha256"]:
        raise ValidationError("Playback manifest changed while reading")
    try:
        data=json.loads(payload,object_pairs_hook=_pairs,
            parse_constant=lambda _v:(_ for _ in ()).throw(ValidationError("Nonfinite playback JSON")))
    except (ValueError,UnicodeError,RecursionError) as error:raise ValidationError("Invalid playback manifest JSON") from error
    fields={"schema_version","status","bindings","coordinate_space","world_matrix","fps","frame_count","source_first_frame",
            "vertex_count","triangle_count","frames","geometry","animation_visual_quality_verified","engine_import_verified"}
    if (type(data) is not dict or set(data)!=fields or type(data["schema_version"]) is not int or data["schema_version"]!=1 or
            data["status"]!="NATIVE_VERIFIED_SKIN_CACHE_V1" or data["bindings"]!=bindings or
            data["coordinate_space"]!="BLENDER_LOCAL_Z_UP" or
            any(data[k] is not False for k in ("animation_visual_quality_verified","engine_import_verified"))):
        raise ValidationError("Playback schema, convention or approval flags differ")
    n,t,count=data["vertex_count"],data["triangle_count"],data["frame_count"]
    if (type(n) is not int or not 100<n<=100000 or type(t) is not int or not 100<t<=200000 or
            type(count) is not int or not 2<=count<=2000 or 12*(n+t)*count>MAX_BYTES or
            count!=timeline.get("source_frame_count") or type(data["frames"]) is not list or len(data["frames"])!=count or
            not _number(data["fps"],1,240) or data["fps"]!=timeline.get("fps") or
            type(data["source_first_frame"]) is not int or data["source_first_frame"]!=timeline.get("source_first_frame")):
        raise ValidationError("Playback count, workload, fps or complete coverage differs")
    world=data["world_matrix"]
    if (type(world) is not list or len(world)!=16 or any(not _number(v,-10000,10000) for v in world) or
            world[12:]!=[0,0,0,1]):raise ValidationError("Invalid playback world transform")
    # No reflection, shear or collapsed scale; those targets are unsupported.
    columns=[world[j:12:4] for j in range(3)]
    lengths=[sum(x*x for x in c)**.5 for c in columns]
    det=(world[0]*(world[5]*world[10]-world[6]*world[9])-world[1]*(world[4]*world[10]-world[6]*world[8])+world[2]*(world[4]*world[9]-world[5]*world[8]))
    if min(lengths)<1e-5 or det<=0 or any(abs(sum(a*b for a,b in zip(columns[i],columns[j])))>1e-5*lengths[i]*lengths[j] for i in range(3) for j in range(i)):
        raise ValidationError("Playback world scale, axes or reflection is incompatible")
    geometry=bound_file(folder,data["geometry"],"motion_skin.bin",MAX_BYTES,cancel_check=cancel_check)
    with geometry.open("rb") as stream:packed=stream.read(MAX_BYTES+1)
    if len(packed)!=data["geometry"]["bytes"] or sha256(packed).hexdigest()!=data["geometry"]["sha256"] or packed[:8]!=MAGIC:
        raise ValidationError("Playback changed while reading or has wrong binary header")
    rows=timeline.get("full_timeline_frames")
    if type(rows) is not list or len(rows)!=count:raise ValidationError("Playback has no complete measured skin reference")
    offset=8;chunks=[];hips=[];radius=0.
    for frame,(record,row) in enumerate(zip(data["frames"],rows),1):
        cancel_check()
        if (type(record) is not dict or set(record)!={"frame","offset","compressed_bytes","raw_sha256","skin_sha256","hip_world"} or
                type(record["frame"]) is not int or record["frame"]!=frame or
                type(record["offset"]) is not int or record["offset"]!=offset or
                type(record["compressed_bytes"]) is not int or not 0<record["compressed_bytes"]<=MAX_BYTES-offset or
                record["skin_sha256"]!=row.get("evaluated_sha256") or not is_sha256(record["raw_sha256"])):
            raise ValidationError("Playback frame ordering, offsets or skin binding differs")
        hip=record["hip_world"]
        if (type(hip) is not list or len(hip)!=3 or any(not _number(v,-10000,10000) for v in hip) or
                hip!=row.get("hip_midpoint_world",row.get("root_world_head"))):raise ValidationError("Playback hip trajectory differs")
        size=record["compressed_bytes"]
        raw=unpack_frame(packed[offset:offset+size],12*(n+t))
        if sha256(raw).hexdigest()!=record["raw_sha256"]:raise ValidationError("Playback frame SHA differs")
        h=sha256();bounds=[]
        for xyz in struct.iter_unpack("<fff",raw[:12*n]):
            if any(not _number(v,-10000,10000) for v in xyz):raise ValidationError("Invalid playback vertex coordinate")
            h.update(struct.pack("<qqq",*(round(v*1000000) for v in xyz)))
            if frame==1:bounds.append(xyz)
        if h.hexdigest()!=record["skin_sha256"]:raise ValidationError("Playback vertices do not reproduce measured skin")
        for triangle in struct.iter_unpack("<III",raw[12*n:]):
            if any(v>=n for v in triangle) or len(set(triangle))!=3:raise ValidationError("Invalid playback triangle indices")
        if frame==1:
            diagonal=sum((max(p[i] for p in bounds)-min(p[i] for p in bounds))**2 for i in range(3))**.5
            radius=diagonal*max(lengths)/2
            if not .01<radius<100:raise ValidationError("Playback surface has invalid bounds")
        chunks.append((offset,size));hips.append(tuple(hip));offset+=size
    if offset!=len(packed):raise ValidationError("Playback has gaps, overlaps or trailing bytes")
    cancel_check()
    return MotionCache(packed,tuple(chunks),tuple(hips),tuple(world),float(data["fps"]),n,t,radius,data["source_first_frame"])
