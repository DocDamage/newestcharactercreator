"""Invented tiny central-body observations; never physical/animation evidence."""
from copy import deepcopy
from hashlib import sha256
import json
import struct

from fixtures.surface_cache_contract import write_surface_cache
from fixtures.motion_skin_contract import file_record


def write_body_contract(folder,paired=False):
    _manifest,cache_report,bindings,baseline,profile,_arm,_verified=write_surface_cache(folder)
    profile['landmarks']['head']={'target':'head'};baseline['neutral_target_helpers']+=['root','spine','head']
    parents={'root':None,'spine':'root','head':'spine','AL':'spine','AR':'spine','WL':'AL','WR':'AR'}
    regions={'left_hand':['WL'],'right_hand':['WR'],'central_body':['head','spine']}
    empty={'pair_count':0,'pair_sha256':sha256().hexdigest(),'hand_triangles':[],'central_triangles':[]}
    rows=[]
    for f,(r,arm) in enumerate(zip(baseline['full_timeline_frames'],_arm['frames']),1):
        left=deepcopy(empty)
        if f==2:left.update(pair_count=1,pair_sha256=sha256(struct.pack('<II',1,2)).hexdigest(),hand_triangles=[1],central_triangles=[2])
        rows.append({'frame':f,'skin_sha256':r['evaluated_sha256'],'triangle_sha256':arm['triangle_sha256'],'left':left,'right':deepcopy(empty)})
    original={'policy':'HAND_CENTRAL_BODY_TRIANGLES_V1','status':'CHECKED','reason':'','hands':{'left':'WL','right':'WR'},'head':'head',
        'parents':parents,'deform_bones':sorted(set(parents)-{'root'}),'world_matrix':_manifest['world_matrix'],
        'region_bones':regions,'region_vertex_counts':{k:10 for k in regions},'frame_count':3,'frames':rows,
        'contact_quality_verified':False,'engine_import_verified':False}
    if paired:bindings={**bindings,'fit_sha256':'b'*64,'fitted_sha256':'c'*64,'fit_report_sha256':'d'*64}
    fitted=deepcopy(original) if paired else None
    if paired:fitted['frames'][2]['right']=deepcopy(rows[1]['left'])
    data={'schema_version':1,'policy':'HAND_CENTRAL_BODY_TRIANGLES_V1','measurement':'FRESH_SAVED_ACTION_BODY_SURFACES_V1','bindings':bindings,
        'paired':paired,'source_frame_count':3,'source_first_frame':7,'fps':30.,'original':original,'fitted':fitted,
        'original_review_verification':cache_report['saved_review_verification'],'fitted_frames_verified':3 if paired else 0,
        'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    fitted_timeline={'bindings':{k:v for k,v in bindings.items() if k!='fit_report_sha256'},'frame_count':3,
        'frames':[{'skin_sha256':r['skin_sha256'],'triangle_sha256':r['triangle_sha256']} for r in rows]} if paired else None
    path=folder/'body_contacts.json';path.write_text(json.dumps(data))
    report={'status':'REAL_NATIVE_BODY_CONTACTS_MEASURED','bindings':bindings,'frames':3,'report':file_record(path),'originals_unchanged':True,
        'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    receipt={'status':'REAL_NATIVE_BODY_CONTACTS_VERIFIED','bindings':{**bindings,'body_review_sha256':report['report']['sha256']},
        'frames_verified':3,'paired':paired,'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    return data,report,receipt,bindings,baseline,profile,fitted_timeline,cache_report,_verified
