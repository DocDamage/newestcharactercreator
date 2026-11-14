"""Independent closed-skin checks on verified cache bytes; no Blender imports."""
from collections import Counter
import math
import struct

from ucc.core.errors import ValidationError
from .motion_cache import MotionCache


def cached_skin_metrics(cache: MotionCache,frame: int,*,cancel_check=lambda:None) -> tuple[float,float]:
    vertices,indices=cache.frame(frame)
    if not 4<=cache.vertex_count<=50000 or not 4<=cache.triangle_count<=100000:
        raise ValidationError('Closed-skin cache exceeds diagnostic scope')
    matrix=cache.world_matrix;points=[]
    for x,y,z in struct.iter_unpack('<fff',vertices):
        p=tuple(matrix[i]*x+matrix[i+1]*y+matrix[i+2]*z+matrix[i+3] for i in (0,4,8))
        if any(not math.isfinite(v) or abs(v)>10000 for v in p):raise ValidationError('Invalid world skin coordinates')
        points.append(p)
    if len(points)!=cache.vertex_count or len(indices)!=cache.triangle_count*12:
        raise ValidationError('Incomplete closed-skin cache geometry')
    diagonal=math.dist(tuple(min(p[i] for p in points) for i in range(3)),tuple(max(p[i] for p in points) for i in range(3)))
    if diagonal<=1e-9:raise ValidationError('Degenerate closed skin')
    edges=Counter();directions=Counter();adjacency=[set() for _ in points];fans=[{} for _ in points];volume=0.;seen=set()
    origin=points[0]
    for index,tri in enumerate(struct.iter_unpack('<III',indices)):
        if index%256==0:cancel_check()
        if len(set(tri))!=3 or any(v>=len(points) for v in tri) or tuple(sorted(tri)) in seen:
            raise ValidationError('Invalid or duplicate closed-skin triangle')
        seen.add(tuple(sorted(tri)))
        a,b,c=(tuple(points[v][i]-origin[i] for i in range(3)) for v in tri)
        ab=tuple(b[i]-a[i] for i in range(3));ac=tuple(c[i]-a[i] for i in range(3))
        normal=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
        if math.hypot(*normal)<=diagonal**2*1e-14:raise ValidationError('Degenerate skin face')
        volume+=sum(a[i]*normal[i] for i in range(3))/6
        for x,y,z in ((tri[0],tri[1],tri[2]),(tri[1],tri[2],tri[0]),(tri[2],tri[0],tri[1])):
            key=tuple(sorted((x,y)));edges[key]+=1;directions[key]+=1 if x<y else -1
            adjacency[x].add(y);adjacency[y].add(x)
            fans[x].setdefault(y,set()).add(z);fans[x].setdefault(z,set()).add(y)
    def connected(graph):
        if not graph:return False
        visited=set();pending=[next(iter(graph))]
        while pending:
            n=pending.pop()
            if n not in visited:visited.add(n);pending.extend(graph[n]-visited)
        return len(visited)==len(graph)
    if (any(n!=2 for n in edges.values()) or any(directions.values()) or
        len(points)-len(edges)+cache.triangle_count!=2 or not connected(dict(enumerate(adjacency))) or
        volume<=diagonal**3*1e-12):raise ValidationError('Cache is outside closed oriented sphere-topology scope')
    for index,fan in enumerate(fans):
        if index%256==0:cancel_check()
        if any(len(v)!=2 for v in fan.values()) or not connected(fan):raise ValidationError('Nonmanifold skin vertex')
    return diagonal,volume
