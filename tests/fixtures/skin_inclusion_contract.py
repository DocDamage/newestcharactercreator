"""Invented cube/cache receipts solely for closed-skin intake boundary tests."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct
import zlib

from fixtures.body_contact_contract import write_body_contract
from fixtures.motion_skin_contract import file_record,skin_sha
from ucc.preview.motion_cache import read_motion_cache
from ucc.preview.skin_inclusion import POLICY


def write_skin_contract(folder,paired=False):
    data,report,receipt,bindings,baseline,profile,fitted,cache_report,arm_verified=write_body_contract(folder,paired)
    old=read_motion_cache(folder,cache_report,cache_report['bindings'],baseline,profile=profile,surface_verification=arm_verified)
    cube=json.loads((Path(__file__).parent/'closed_skin_cube.json').read_text(encoding='utf-8'))
    vertices=b''.join(struct.pack('<fff',*p) for p in cube['points']);indices=b''.join(struct.pack('<III',*t) for t in cube['triangles'])
    packed=zlib.compress(vertices+indices);skin=skin_sha(vertices);topology=sha256(indices).hexdigest()
    cache=replace(old,packed=packed*3,chunks=tuple((len(packed)*i,len(packed)) for i in range(3)),vertex_count=8,triangle_count=12,
        surface_review=replace(old.surface_review,triangle_hashes=(topology,)*3))
    for row in baseline['full_timeline_frames']:row['evaluated_sha256']=skin
    data.update(policy=POLICY,measurement='FRESH_SAVED_ACTION_CLOSED_SKIN_V1')
    for variant in (data['original'],data['fitted']):
        if variant is None:continue
        variant['policy']=POLICY;variant['region_vertex_counts']={'left_hand':3,'right_hand':3,'central_body':2}
        variant['frames']=[{'frame':i+1,'skin_sha256':skin,'triangle_sha256':topology,
            'observation':{'diagonal_world':3**.5,'offset_world':3**.5*1e-6,'signed_volume_world':1.,'ray_queries':12,
                'left':{'selected_triangles':[0],'nonzero_triangles':[0],'ambiguous_triangles':[]},
                'right':{'selected_triangles':[2],'nonzero_triangles':[],'ambiguous_triangles':[2]}}} for i in range(3)]
    if fitted:
        for row in fitted['frames']:row.update(skin_sha256=skin,triangle_sha256=topology)
    report['status']='REAL_NATIVE_SKIN_INCLUSION_MEASURED';receipt['status']='REAL_NATIVE_SKIN_INCLUSION_VERIFIED'
    path=folder/'body_contacts.json';path.write_text(json.dumps(data),encoding='utf-8');report['report']=file_record(path)
    receipt['bindings']['body_review_sha256']=report['report']['sha256']
    return data,report,receipt,bindings,baseline,profile,fitted,cache
