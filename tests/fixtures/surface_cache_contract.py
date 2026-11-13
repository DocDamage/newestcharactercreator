"""Invented metadata for parser tests only; not physical intersection evidence."""
from copy import deepcopy
from hashlib import sha256
import json,struct,zlib
from fixtures.motion_skin_contract import write_cache,file_record


def write_surface_cache(folder):
    data,report,bindings,timeline=write_cache(folder)
    profile={"landmarks":{"left_hand":{"target":"WL"},"right_hand":{"target":"WR"}}}
    timeline.update(mapped_pairs=[{"target":"WL"},{"target":"WR"}],neutral_target_helpers=["AL","AR"])
    frames=[];binary=(folder/'motion_skin.bin').read_bytes()
    empty={"pair_count":0,"pair_sha256":sha256().hexdigest(),"hand_triangles":[],"opposite_arm_triangles":[]}
    for frame,row in enumerate(data['frames'],1):
        raw=zlib.decompress(binary[row['offset']:row['offset']+row['compressed_bytes']])
        hit=deepcopy(empty)
        if frame==2:hit.update(pair_count=1,pair_sha256=sha256(struct.pack('<II',1,2)).hexdigest(),hand_triangles=[1],opposite_arm_triangles=[2])
        frames.append({'frame':frame,'skin_sha256':row['skin_sha256'],'triangle_sha256':sha256(raw[1440:]).hexdigest(),
                       'left':hit,'right':deepcopy(empty)})
    surface={'schema_version':1,'policy':'HAND_OPPOSITE_UPPER_LIMB_TRIANGLES_V1','bindings':bindings,'status':'CHECKED','reason':'',
             'hands':{'left':'WL','right':'WR'},'region_bones':{'left_hand':['WL'],'right_hand':['WR'],'left_arm':['AL'],'right_arm':['AR']},
             'region_vertex_counts':{k:10 for k in ('left_hand','right_hand','left_arm','right_arm')},
             'frame_count':3,'frames':frames,'contact_quality_verified':False,'engine_import_verified':False}
    path=folder/'motion_contacts.json';path.write_text(json.dumps(surface));record=file_record(path)
    data.update(schema_version=2,status='NATIVE_VERIFIED_SKIN_CACHE_V2',surface_review=record)
    manifest=folder/'motion_skin.json';manifest.write_text(json.dumps(data))
    report.update(manifest=file_record(manifest),surface_review=record)
    verified={'status':'REAL_NATIVE_SURFACE_REVIEW_VERIFIED','bindings':{**bindings,'surface_review_sha256':record['sha256']},
              'frames_verified':3,'saved_review_verification':deepcopy(report['saved_review_verification']),
              'world_matrix':data['world_matrix'][:],'originals_unchanged':True,'contact_quality_verified':False}
    return data,report,bindings,timeline,profile,surface,verified
