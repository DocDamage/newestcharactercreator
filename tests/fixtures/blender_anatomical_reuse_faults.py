"""Actual evaluated MPFB geometry faults; repeated pose, not clip-quality proof."""
from array import array
from hashlib import sha256
import math
import struct
import sys

from blender_bridge.anatomical_reuse import ExactSourceFrames,ExactInspector,MAX_KEY_BYTES


def hashes(mesh):
    vertices=array('f',[0.])*(3*len(mesh.vertices));mesh.vertices.foreach_get('co',vertices)
    triangles=array('I',[0])*(3*len(mesh.loop_triangles));mesh.loop_triangles.foreach_get('vertices',triangles)
    rounded=sha256()
    for i in range(0,len(vertices),3):
        rounded.update(struct.pack('<qqq',*(round(v*1000000) for v in vertices[i:i+3])))
    if sys.byteorder!='little':vertices.byteswap();triangles.byteswap()
    return rounded.hexdigest(),sha256(triangles.tobytes()).hexdigest(),sha256(vertices.tobytes()).hexdigest()


def verify_exact_reuse(mesh,profile,rig,human):
    before=hashes(mesh);memo=ExactSourceFrames()
    source=ExactInspector(profile,rig,human,memo,True);fitted=ExactInspector(profile,rig,human,memo,False)
    for frame in (1,2,3):source.inspect(mesh,frame,before[0],before[1])
    fitted.inspect(mesh,1,before[0],before[1]);fitted.inspect(mesh,2,before[0],before[1])
    if memo.hits!=1 or memo.misses!=1:raise RuntimeError('Exact actual geometry did not exercise one real reuse hit')
    for name in ('rows','enclosure_rows','complete_rows'):
        if getattr(source,name)[:2]!=getattr(fitted,name):raise RuntimeError('Reused actual contact observations differ')
    chosen=None
    for vertex_id in sorted(source.vertices['right_hand']):
        for axis,old in enumerate(mesh.vertices[vertex_id].co):
            if not .001<abs(old)<10000:continue
            bits=struct.unpack('<I',struct.pack('<f',old))[0]
            value=struct.unpack('<f',struct.pack('<I',bits+1 if old>0 else bits-1))[0]
            if (math.isfinite(value) and 0<abs(value-old)<1e-6 and
                    round(value*1000000)==round(old*1000000)):
                chosen=vertex_id,axis,float(old),value;break
        if chosen:break
    if chosen is None:raise RuntimeError('Cannot construct an actual submicron hand-vertex fault')
    vertex_id,axis,old,value=chosen
    try:
        mesh.vertices[vertex_id].co[axis]=value;changed=hashes(mesh)
        if changed[:2]!=before[:2] or changed[2]==before[2]:raise RuntimeError('Actual fault does not isolate the rounded-hash alias')
        fitted.inspect(mesh,3,changed[0],changed[1])
        if memo.hits!=1 or memo.misses!=2:raise RuntimeError('Submicron actual geometry incorrectly reused an earlier verdict')
    finally:mesh.vertices[vertex_id].co[axis]=old
    if hashes(mesh)!=before:raise RuntimeError('Actual evaluated vertex was not restored')
    bounded=ExactSourceFrames();bounded.bytes=MAX_KEY_BYTES
    budget_source=ExactInspector(profile,rig,human,bounded,True)
    budget_fitted=ExactInspector(profile,rig,human,bounded,False)
    for frame in (1,2):budget_source.inspect(mesh,frame,before[0],before[1])
    for frame in (1,2):budget_fitted.inspect(mesh,frame,before[0],before[1])
    if bounded.frames or bounded.hits or bounded.misses!=2 or bounded.dropped!=2:
        raise RuntimeError('Exhausted memo did not fall back to full actual geometry')
    for name in ('rows','enclosure_rows','complete_rows'):
        if getattr(budget_source,name)!=getattr(budget_fitted,name):
            raise RuntimeError('Bounded full-computation fallback changed actual observations')
    if hashes(mesh)!=before:raise RuntimeError('Reuse faults changed evaluated geometry')
    return {'status':'REAL_MPFB_EXACT_ANATOMICAL_REUSE_FAULTS_PASSED',
        'scope':'REPEATED_ACTUAL_POSE_AND_SUBMICRON_FAULT_NOT_FULL_CLIP_QUALITY',
        'fresh_source_calculations':3,'fitted_exact_reuse_hits':memo.hits,'fitted_full_calculations':memo.misses,
        'all_three_exact_hit_observations_match':True,'actual_raw_coordinate_bytes_changed':True,
        'quantized_skin_and_triangle_hashes_unchanged':True,'submicron_change_recomputed':True,
        'exhausted_memo_falls_back_to_full_geometry':True,'evaluated_vertex_restored':True,
        'saved_scene_created':False,'quality_approved':False}
