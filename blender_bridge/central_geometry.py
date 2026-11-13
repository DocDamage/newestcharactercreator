"""Measured whole-polygon trunk patch and protected diagnostic boundary chains."""
from collections import Counter
from dataclasses import dataclass
import math

from blender_bridge.central_cap import bounded_cap
from blender_bridge.closed_skin import closed_skin_geometry


@dataclass(frozen=True,slots=True)
class CentralGeometry:
    skin_points: tuple
    body_points: tuple
    body_faces: tuple
    cap_faces: tuple
    body_triangle_ids: tuple
    body_vertex_ids: tuple
    boundaries: tuple
    cap_boxes: tuple
    pivot_local: tuple
    origin_world: tuple
    bounds: tuple
    diagonal: float
    signed_volume: float


def _recenter(points,world,used):
    if (len(world)!=16 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10000 for v in world) or
        tuple(world[12:])!=(0.,0.,0.,1.)):
        raise ValueError('CENTRAL_VOLUME_WORLD_TRANSFORM_UNAVAILABLE')
    if any(len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10000 for v in p) for p in points):
        raise ValueError('CENTRAL_VOLUME_INVALID_SKIN')
    pivot=tuple((min(points[v][i] for v in used)+max(points[v][i] for v in used))/2 for i in range(3))
    origin=tuple(sum(world[row+i]*pivot[i] for i in range(3))+world[row+3] for row in (0,4,8))
    # Subtract the local pivot before applying the linear world transform. Large
    # world translations never enter the BVH's float32 arithmetic.
    transformed=[]
    for p in points:
        relative=tuple(p[i]-pivot[i] for i in range(3))
        position=tuple(sum(world[row+i]*relative[i] for i in range(3)) for row in (0,4,8))
        if any(not math.isfinite(v) or abs(v)>10000 for v in position):raise ValueError('CENTRAL_VOLUME_WORLD_SCALE_UNAVAILABLE')
        transformed.append(position)
    return transformed,pivot,origin


def central_geometry(points: list,triangles: list,polygon_ids: list,polygons: list,members: set,world: tuple,
                     *,expected_caps: int=4,cancel_check=lambda:None) -> CentralGeometry:
    """Keep only complete weighted polygons, with pose-specific triangulation.

    Whole polygons keep anatomical boundaries stable when posed quad diagonals
    change. The supported production scope has four mapped limb boundaries;
    expected_caps is an internal geometry-test parameter, never a worker option.
    Closure faces validate a closed oriented chain but never enter ray queries.
    """
    cancel_check()
    if (not 4<=len(points)<=50000 or not 4<=len(triangles)<=100000 or len(polygon_ids)!=len(triangles) or
        type(polygons) is not list or not 1<=len(polygons)<=100000 or type(members) is not set or
        not members or any(type(v) is not int or not 0<=v<len(points) for v in members) or
        type(expected_caps) is not int or not 1<=expected_caps<=4):
        raise ValueError('CENTRAL_VOLUME_GEOMETRY_BUDGET')
    faces=[];seen=set();loops=0
    for face in polygons:
        if (type(face) not in (tuple,list) or not 3<=len(face)<=64 or
            any(type(v) is not int or not 0<=v<len(points) for v in face) or len(set(face))!=len(face)):
            raise ValueError('CENTRAL_VOLUME_INVALID_POLYGON')
        key=tuple(sorted(face));loops+=len(face)
        if key in seen or loops>1000000:raise ValueError('CENTRAL_VOLUME_INVALID_POLYGON')
        seen.add(key);faces.append(set(face))
    selected={i for i,face in enumerate(faces) if face<=members};counts=Counter();source=[];seen=set()
    for index,(tri,poly) in enumerate(zip(triangles,polygon_ids)):
        if index%256==0:cancel_check()
        if (type(tri) not in (tuple,list) or len(tri)!=3 or any(type(v) is not int or not 0<=v<len(points) for v in tri) or
            len(set(tri))!=3 or type(poly) is not int or not 0<=poly<len(polygons) or not set(tri)<=faces[poly]):
            raise ValueError('CENTRAL_VOLUME_TRIANGLE_POLYGON_MISMATCH')
        key=tuple(sorted(tri))
        if key in seen:raise ValueError('CENTRAL_VOLUME_DUPLICATE_TRIANGLE')
        seen.add(key);counts[poly]+=1
        if poly in selected:source.append(index)
    if any(counts[i]!=len(face)-2 for i,face in enumerate(polygons)):
        raise ValueError('CENTRAL_VOLUME_INCOMPLETE_POLYGON_TRIANGULATION')
    if not source:raise ValueError('CENTRAL_VOLUME_EMPTY_BODY_PATCH')
    body=[tuple(triangles[i]) for i in source];edges=Counter()
    for a,b,c in body:
        for x,y in ((a,b),(b,c),(c,a)):edges[(min(x,y),max(x,y))]+=1
    if any(n not in (1,2) for n in edges.values()):raise ValueError('CENTRAL_VOLUME_NONMANIFOLD_PATCH')
    directed=[(a,b) for tri in body for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])) if edges[(min(a,b),max(a,b))]==1]
    outgoing={a:b for a,b in directed};incoming={b:a for a,b in directed}
    if not directed or len(outgoing)!=len(incoming) or len(outgoing)!=len(directed) or set(outgoing)!=set(incoming):
        raise ValueError('CENTRAL_VOLUME_BRANCHED_BOUNDARY')
    boundaries=[];remaining=set(outgoing)
    while remaining:
        first=min(remaining);loop=[];v=first
        while v not in loop:
            if v not in remaining or len(loop)>=256:raise ValueError('CENTRAL_VOLUME_BOUNDARY_BUDGET')
            loop.append(v);remaining.remove(v);v=outgoing[v]
        if v!=first:raise ValueError('CENTRAL_VOLUME_BRANCHED_BOUNDARY')
        boundaries.append(loop)
        if len(boundaries)>expected_caps:raise ValueError('CENTRAL_VOLUME_BOUNDARY_COUNT')
    if len(boundaries)!=expected_caps:raise ValueError('CENTRAL_VOLUME_BOUNDARY_COUNT')
    used=sorted({v for face in body for v in face});skin,pivot,origin=_recenter(points,world,used)
    lookup={v:i for i,v in enumerate(used)};body_points=[skin[v] for v in used]
    body_faces=[tuple(lookup[v] for v in face) for face in body];cap_faces=[];boxes=[]
    construction=list(skin)
    for loop in boundaries:
        cancel_check();closure,center,box,_=bounded_cap(construction,loop,cancel_check=cancel_check)
        lookup[len(construction)]=len(body_points);construction.append(center);body_points.append(center)
        cap_faces.extend(tuple(lookup[v] for v in face) for face in closure);boxes.append(box)
    diagonal,volume=closed_skin_geometry(body_points,body_faces+cap_faces,cancel_check=cancel_check)
    bounds=(tuple(min(p[i] for p in body_points) for i in range(3)),tuple(max(p[i] for p in body_points) for i in range(3)))
    return CentralGeometry(tuple(skin),tuple(body_points),tuple(body_faces),tuple(cap_faces),tuple(source),tuple(used),
        tuple(tuple(loop) for loop in boundaries),tuple(boxes),pivot,origin,bounds,diagonal,volume)


def outward_probe(points: tuple,triangle: tuple,offset: float) -> tuple:
    """Double-precision centroid/normal in the declared recentered world frame."""
    if (len(triangle)!=3 or len(set(triangle))!=3 or any(type(v) is not int or not 0<=v<len(points) for v in triangle) or
        type(offset) not in (int,float) or not math.isfinite(offset) or offset<=0):
        raise ValueError('CENTRAL_VOLUME_INVALID_HAND_PROBE')
    a,b,c=(points[v] for v in triangle);ab=tuple(b[i]-a[i] for i in range(3));ac=tuple(c[i]-a[i] for i in range(3))
    normal=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]);length=math.hypot(*normal)
    if not math.isfinite(length) or length<=1e-20:raise ValueError('CENTRAL_VOLUME_DEGENERATE_HAND_PROBE')
    return tuple((a[i]+b[i]+c[i])/3+normal[i]*(offset/length) for i in range(3))
