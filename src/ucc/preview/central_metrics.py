"""Reconstruct reported trunk geometry from immutable playback bytes."""
from collections import Counter
import math
import struct

from ucc.core.errors import ValidationError


def require_metrics(obs,cache,frame,body_ids,triangles,*,cancel_check=lambda:None):
    raw,_=cache.frame(frame);local=list(struct.iter_unpack('<fff',raw));matrix=cache.world_matrix
    used=sorted({v for i in body_ids for v in triangles[i]})
    pivot=tuple((min(local[v][i] for v in used)+max(local[v][i] for v in used))/2 for i in range(3))
    points=[tuple(sum(matrix[row+i]*(p[i]-pivot[i]) for i in range(3)) for row in (0,4,8)) for p in local]
    origin=tuple(sum(matrix[row+i]*pivot[i] for i in range(3))+matrix[row+3] for row in (0,4,8))
    used_set=set(used)
    body=[triangles[i] for i in sorted(body_ids)];edges=Counter();directed=[]
    for index,(a,b,c) in enumerate(body):
        if index%256==0:cancel_check()
        for x,y in ((a,b),(b,c),(c,a)):edges[(min(x,y),max(x,y))]+=1;directed.append((x,y))
    if any(n not in (1,2) for n in edges.values()):raise ValidationError('Nonmanifold enclosure body patch')
    boundary={(a,b) for a,b in directed if edges[(min(a,b),max(a,b))]==1}
    loops=obs['boundaries']
    if type(loops) is not list or len(loops)!=4:raise ValidationError('Enclosure needs four protected boundaries')
    reported=set();seen=set();caps=[];boxes=[]
    for loop in loops:
        if (type(loop) is not list or not 3<=len(loop)<=256 or any(type(v) is not int or v not in used_set for v in loop) or
            len(set(loop))!=len(loop) or seen&set(loop) or loop[0]!=min(loop)):
            raise ValidationError('Invalid enclosure boundary loop')
        seen.update(loop);reported.update(zip(loop,loop[1:]+loop[:1]))
        center=tuple(sum(points[v][i] for v in loop)/len(loop) for i in range(3));ci=len(points);points.append(center)
        caps.extend((b,a,ci) for a,b in zip(loop,loop[1:]+loop[:1]))
        boxes.append([list(min(points[v][i] for v in loop) for i in range(3)),
                      list(max(points[v][i] for v in loop) for i in range(3))])
    if reported!=boundary or [loop[0] for loop in loops]!=sorted(loop[0] for loop in loops):
        raise ValidationError('Enclosure boundaries differ from measured body skin')
    full_used=used+list(range(len(local),len(points)))
    bounds=[[min(points[v][i] for v in full_used) for i in range(3)],
            [max(points[v][i] for v in full_used) for i in range(3)]]
    diagonal=math.dist(*bounds);volume=0.
    for a,b,c in body+caps:
        x,y,z=points[a],points[b],points[c]
        volume+=(x[0]*(y[1]*z[2]-y[2]*z[1])+x[1]*(y[2]*z[0]-y[0]*z[2])+x[2]*(y[0]*z[1]-y[1]*z[0]))/6
    if not math.isfinite(diagonal) or diagonal<=1e-9 or volume<=diagonal**3*1e-12:
        raise ValidationError('Enclosure cache has nonpositive body volume')
    def close(actual,expected):
        if isinstance(expected,(tuple,list)):
            return type(actual) is list and len(actual)==len(expected) and all(close(a,b) for a,b in zip(actual,expected))
        return type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-5,abs_tol=diagonal*1e-7)
    for key,value in (('pivot_local',pivot),('origin_world',origin),('bounds',bounds),('cap_boxes',boxes),
                      ('diagonal_world',diagonal)):
        if not close(obs[key],value):raise ValidationError('Enclosure geometry does not reproduce from playback: '+key)
    reported_volume=obs['signed_volume_world']
    if (type(reported_volume) not in (int,float) or not math.isfinite(reported_volume) or
        not math.isclose(reported_volume,volume,rel_tol=1e-5,abs_tol=diagonal**3*1e-10)):
        raise ValidationError('Enclosure volume does not reproduce from playback')
    offset=obs['offset_world']
    if type(offset) not in (int,float) or not math.isclose(offset,diagonal*1e-6,rel_tol=1e-5,abs_tol=diagonal*1e-13):
        raise ValidationError('Enclosure probe resolution differs')
    audit=obs['body_surface_audit'];count=len(body)
    expected={'method':'BOUNDED_NONADJACENT_BODY_TRIANGLES_V1','triangles':count,'max_transient_pairs':262144,
        'nonadjacent_pairs':0,'adjacent_fold_quality_verified':False}
    if (type(audit) is not dict or set(audit)!=set(expected)|{'candidate_pairs','chunk_queries'} or
        any(type(audit[k]) is not type(v) or audit[k]!=v for k,v in expected.items()) or
        type(audit['candidate_pairs']) is not int or not 0<=audit['candidate_pairs']<=1000000 or
        type(audit['chunk_queries']) is not int or audit['chunk_queries']!=math.ceil(count/min(64,max(1,262144//count)))):
        raise ValidationError('Enclosure body audit is incomplete or exceeds fixed work bounds')
