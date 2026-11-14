"""Original non-shipping perforated cube metadata, solely for parser tests.

This fixture invents zero classifications. It provides no physical/BVH evidence.
Actual Blender fault tests separately verify the production classifier.
"""
from hashlib import sha256
import struct
import zlib

from blender_bridge.central_geometry import central_geometry
from blender_bridge.central_regions import volume_regions
from ucc.preview.motion_cache import MotionCache


def central_contract():
    points=[];lookup={};polygons=[]
    def vertex(p):
        p=tuple(round(v,9) for v in p)
        if p not in lookup:lookup[p]=len(points);points.append(p)
        return lookup[p]
    faces=[((1,0,0),(0,1,0),(0,0,1)),((-1,0,0),(0,-1,0),(0,0,1)),
           ((0,1,0),(-1,0,0),(0,0,1)),((0,-1,0),(1,0,0),(0,0,1)),
           ((0,0,1),(1,0,0),(0,1,0)),((0,0,-1),(-1,0,0),(0,1,0))]
    for side,(normal,u,v) in enumerate(faces):
        for a in range(3):
            for b in range(3):
                if side<4 and a==b==1:continue
                corners=[]
                for x,y in ((a,b),(a+1,b),(a+1,b+1),(a,b+1)):
                    corners.append(vertex(tuple(normal[i]+u[i]*(-1+2*x/3)+v[i]*(-1+2*y/3) for i in range(3))))
                polygons.append(corners)
    members=set(range(len(points)));hands={}
    for side,x in (('left',-4),('right',4)):
        base=len(points);points.extend(((x,0,0),(x+.1,0,0),(x,.1,0),(x,0,.1)))
        hands[side]=set(range(base,base+4))
        polygons.extend([[base+i for i in f] for f in ((0,2,1),(0,1,3),(1,2,3),(2,0,3))])
    # Match the float32 values actually carried by immutable playback.
    raw=b''.join(struct.pack('<fff',*p) for p in points);points=list(struct.iter_unpack('<fff',raw))
    triangles=[];polygon_ids=[]
    for index,face in enumerate(polygons):
        for i in range(1,len(face)-1):triangles.append((face[0],face[i],face[i+1]));polygon_ids.append(index)
    indices=b''.join(struct.pack('<III',*t) for t in triangles);packed=zlib.compress(raw+indices)
    world=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
    cache=MotionCache(packed,((0,len(packed)),)*3,((0.,0.,0.),)*3,world,30.,len(points),len(triangles),5.)
    parents={'root':None,'spine':'root','head':'spine','LH':'root','RH':'root'}
    for s in ('L','R'):
        previous='spine'
        for part in ('clav','upper','lower','hand'):
            parents[s+part]=previous;previous=s+part
    profile={'pairs':[{'target':n} for n in parents],
             'landmarks':{k:{'target':v} for k,v in {'left_hand':'Lhand','right_hand':'Rhand','head':'head','left_hip':'LH','right_hip':'RH'}.items()}}
    regions,roots=volume_regions(profile,parents,set(parents))
    geometry=central_geometry(points,triangles,polygon_ids,polygons,members,world)
    count=len(geometry.body_faces)
    obs={'diagonal_world':geometry.diagonal,'offset_world':geometry.diagonal*1e-6,'signed_volume_world':geometry.signed_volume,
         'pivot_local':list(geometry.pivot_local),'origin_world':list(geometry.origin_world),'bounds':[list(v) for v in geometry.bounds],
         'cap_boxes':[[list(p) for p in box] for box in geometry.cap_boxes],'boundaries':[list(loop) for loop in geometry.boundaries],
         'body_triangle_ids':list(geometry.body_triangle_ids),'ray_queries':0,
         'body_surface_audit':{'method':'BOUNDED_NONADJACENT_BODY_TRIANGLES_V1','triangles':count,'candidate_pairs':0,
            'chunk_queries':(count+63)//64,'max_transient_pairs':262144,'nonadjacent_pairs':0,'adjacent_fold_quality_verified':False}}
    for side in ('left','right'):
        ids=[i for i,t in enumerate(triangles) if set(t)<=hands[side]];trace=sha256()
        for i in ids:trace.update(struct.pack('<IB',i,0))
        obs[side]={'selected_triangles':ids,'nonzero_triangles':[],'ambiguous_triangles':[],
                   'inside_polygons':[],'ambiguous_polygons':[],'classification_sha256':trace.hexdigest()}
    rows=[{'frame':i,'skin_sha256':'a'*64,'triangle_sha256':sha256(indices).hexdigest(),'observation':obs} for i in range(1,4)]
    body={'parents':parents,'deform_bones':sorted(parents),'region_vertex_counts':{s+'_hand':4 for s in ('left','right')},
          'frames':[{k:v for k,v in r.items() if k!='observation'} for r in rows]}
    data={'world_matrix':list(world),'limb_roots':roots,'region_bones':{k:sorted(v) for k,v in regions.items()},
          'region_vertex_ids':{'central_body':sorted(members),**{s+'_hand':sorted(v) for s,v in hands.items()}},'frames':rows}
    return data,cache,body,polygons,profile
