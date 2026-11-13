"""Export actual saved skin after full fresh-process verification; private only."""
from __future__ import annotations
from array import array
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any
import zlib

from blender_bridge.native_review_reopen import reopen_native, digest, scene_objects
from blender_bridge.native_inputs import read_json,validate_profile
from blender_bridge.native_surface_review import SurfaceInspector

MAGIC=b"UCCSKN1\0"
MAX_BYTES=256*1024*1024


def record(path: Path) -> dict:
    return {"name":path.name,"bytes":path.stat().st_size,"sha256":digest(path)}


def export_native_cache(bpy: Any, root: Path, options: dict) -> dict:
    # This rechecks actual binding/weights/world/Action and every raw/corrected
    # frame, not just the JSON assertion or the saved file's checksum.
    reopened=reopen_native(bpy,root,options)
    data=read_json(root/"target_timeline.json",options["timeline_sha256"],64*1024*1024)
    human,rig=scene_objects(bpy)
    profile=validate_profile(read_json(root/"native_mapping.json",options["mapping_sha256"],64*1024),
        options["source_sha256"],options["snapshot_sha256"],options["master_sha256"])
    inspector=SurfaceInspector(profile,rig,human)
    binary=root/"motion_skin.bin";manifest=root/"motion_skin.json"
    contacts=root/"motion_contacts.json"
    temporary=root/"motion_skin.partial"
    if any(p.exists() or p.is_symlink() for p in (binary,manifest,temporary,contacts)):
        raise ValueError("Refuse to replace private playback outputs")
    frames=[];total_raw=0;counts=None
    world=[float(v) for line in human.matrix_world for v in line]
    try:
        with temporary.open("xb") as stream:
            stream.write(MAGIC)
            for frame,row in enumerate(data["full_timeline_frames"],1):
                bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
                graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
                mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
                if mesh is None:raise ValueError("Cannot evaluate actual playback mesh")
                try:
                    mesh.calc_loop_triangles()
                    n,t=len(mesh.vertices),len(mesh.loop_triangles)
                    if not 100<n<=100000 or not 100<t<=200000:
                        raise ValueError("Playback surface exceeds bounded geometry workload")
                    if counts is None:counts=(n,t)
                    if counts!=(n,t):raise ValueError("Playback vertex/triangle count changes; no cropping")
                    raw_size=12*(n+t);total_raw+=raw_size
                    if total_raw>MAX_BYTES:raise ValueError("Complete playback exceeds 256 MiB; no frame cropping")
                    vertices=array("f",[0.])*(3*n);indices=array("I",[0])*(3*t)
                    mesh.vertices.foreach_get("co",vertices)
                    mesh.loop_triangles.foreach_get("vertices",indices)
                    if any(not math.isfinite(v) or abs(v)>10000 for v in vertices):
                        raise ValueError("Invalid playback skin coordinates")
                    h=sha256()
                    for i in range(0,len(vertices),3):
                        h.update(struct.pack("<qqq",*(round(v*1000000) for v in vertices[i:i+3])))
                    if h.hexdigest()!=row["evaluated_sha256"]:
                        raise ValueError("Playback skin differs from saved verified timeline")
                    if sys.byteorder!="little":vertices.byteswap();indices.byteswap()
                    inspector.inspect(mesh,frame,row["evaluated_sha256"],sha256(indices.tobytes()).hexdigest())
                    raw=vertices.tobytes()+indices.tobytes()
                    packed=zlib.compress(raw,1)
                    offset=stream.tell()
                    if offset+len(packed)>MAX_BYTES:raise ValueError("Packed playback exceeds 256 MiB")
                    stream.write(packed)
                    frames.append({"frame":frame,"offset":offset,"compressed_bytes":len(packed),
                        "raw_sha256":sha256(raw).hexdigest(),"skin_sha256":row["evaluated_sha256"],
                        "hip_world":row.get("hip_midpoint_world",row["root_world_head"])})
                finally:evaluated.to_mesh_clear()
        binary=temporary.rename(binary)
        contact_payload=json.dumps(inspector.report(options),allow_nan=False,separators=(",",":")).encode()
        if len(contact_payload)>16*1024*1024:raise ValueError("Complete surface review exceeds its bound; no truncation")
        with contacts.open("xb") as stream:stream.write(contact_payload)
        result={"schema_version":2,"status":"NATIVE_VERIFIED_SKIN_CACHE_V2","bindings":dict(options),
            "surface_review":record(contacts),
            "coordinate_space":"BLENDER_LOCAL_Z_UP","world_matrix":world,"fps":data["fps"],
            "source_first_frame":data["source_first_frame"],
            "frame_count":len(frames),"vertex_count":counts[0],"triangle_count":counts[1],
            "frames":frames,"geometry":record(binary),
            "animation_visual_quality_verified":False,"engine_import_verified":False}
        payload=json.dumps(result,allow_nan=False,separators=(",",":")).encode()
        if len(payload)>4*1024*1024:raise ValueError("Playback manifest exceeds limit")
        # Rehash all staged originals after evaluation, never save either scene.
        for name,key in (("candidate.blend","master_sha256"),("review_motion.blend","review_sha256"),
                         ("source_snapshot.json","snapshot_sha256"),("native_mapping.json","mapping_sha256"),
                         ("target_timeline.json","timeline_sha256")):
            if digest(root/name)!=options[key]:raise ValueError("Playback changed staged originals")
        with manifest.open("xb") as stream:stream.write(payload)
        return {"status":"REAL_NATIVE_SKIN_CACHE_EXPORTED","bindings":dict(options),
                "saved_review_verification":reopened,"manifest":record(manifest),"surface_review":record(contacts)}
    except BaseException:
        # The runner kills a cancelled process; its isolated folder is never
        # promoted. Ordinary exceptions also remove incomplete owned outputs.
        for path in (temporary,binary,manifest,contacts):
            if path.is_file() and not path.is_symlink():path.unlink()
        raise
