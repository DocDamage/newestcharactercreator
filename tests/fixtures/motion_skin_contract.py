"""Tiny original non-shipping geometry solely for cache boundary tests."""
from hashlib import sha256
import json
import struct
import zlib


def skin_sha(vertices):
    h=sha256()
    for xyz in struct.iter_unpack("<fff",vertices):
        h.update(struct.pack("<qqq",*(round(v*1000000) for v in xyz)))
    return h.hexdigest()


def file_record(path):return {"name":path.name,"bytes":path.stat().st_size,"sha256":sha256(path.read_bytes()).hexdigest()}


def write_cache(folder):
    bindings={key:"a"*64 for key in ("source_sha256","snapshot_sha256","mapping_sha256","master_sha256","review_sha256","timeline_sha256")}
    binary=bytearray(b"UCCSKN1\0");frames=[];timeline={"source_frame_count":3,"source_first_frame":7,"fps":30.,"full_timeline_frames":[]}
    for f in range(3):
        vertices=b"".join(struct.pack("<fff",(i%10)*.02,(i//10)*.02,f*.01) for i in range(120))
        indices=b"".join(struct.pack("<III",i,(i+1+f)%120,(i+11+f)%120) for i in range(120))
        raw=vertices+indices;packed=zlib.compress(raw,1);hip=[0.,0.,1.]
        frames.append({"frame":f+1,"offset":len(binary),"compressed_bytes":len(packed),"raw_sha256":sha256(raw).hexdigest(),"skin_sha256":skin_sha(vertices),"hip_world":hip})
        timeline["full_timeline_frames"].append({"frame":f+1,"evaluated_sha256":skin_sha(vertices),"root_world_head":hip})
        binary.extend(packed)
    path=folder/"motion_skin.bin";path.write_bytes(binary)
    data={"schema_version":1,"status":"NATIVE_VERIFIED_SKIN_CACHE_V1","bindings":bindings,
          "coordinate_space":"BLENDER_LOCAL_Z_UP","world_matrix":[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],"fps":30.,
          "frame_count":3,"source_first_frame":7,"vertex_count":120,"triangle_count":120,"frames":frames,"geometry":file_record(path),
          "animation_visual_quality_verified":False,"engine_import_verified":False}
    manifest=folder/"motion_skin.json";manifest.write_text(json.dumps(data))
    reopen={"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":bindings,"frames_verified":3,
            "uncorrected_skin_frames_verified":3,"master_strain_frames_verified":3,"hip_frames_verified":0,
            "skin_deformation_policy":"BOUND_CORRECTIVE_SMOOTH_V1","original_master_unchanged":True,"review_unchanged":True,
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
    report={"status":"REAL_NATIVE_SKIN_CACHE_EXPORTED","bindings":bindings,"saved_review_verification":reopen,"manifest":file_record(manifest)}
    return data,report,bindings,timeline
