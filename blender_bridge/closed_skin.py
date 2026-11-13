"""Bounded closed, oriented sphere-topology prerequisites; no quality verdict."""
import math

MAX_VERTICES=50000
MAX_TRIANGLES=100000


def closed_skin_geometry(points: list,triangles: list,*,cancel_check=lambda:None) -> tuple[float,float]:
    """Reject open, disconnected, inverted, pinched or degenerate surfaces.

    A positive total volume does not exclude self intersection. That is precisely
    why the separate winding observations must not imply a valid solid or quality.
    """
    if not 4<=len(points)<=MAX_VERTICES or not 4<=len(triangles)<=MAX_TRIANGLES:
        raise ValueError('SKIN_GEOMETRY_BUDGET')
    for p in points:
        if len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10000 for v in p):
            raise ValueError('SKIN_INVALID_GEOMETRY')
    origin=points[0]
    diagonal=math.dist(tuple(min(p[i] for p in points) for i in range(3)),
                       tuple(max(p[i] for p in points) for i in range(3)))
    if diagonal<=1e-9:raise ValueError('SKIN_DEGENERATE_GEOMETRY')
    edges={};links=[{} for _ in points];seen=set();volume=0.
    for index,face in enumerate(triangles):
        if index%256==0:cancel_check()
        if (len(face)!=3 or any(type(v) is not int or not 0<=v<len(points) for v in face) or len(set(face))!=3):
            raise ValueError('SKIN_INVALID_GEOMETRY')
        key=tuple(sorted(face))
        if key in seen:raise ValueError('SKIN_DUPLICATE_FACE')
        seen.add(key);a,b,c=(tuple(points[v][i]-origin[i] for i in range(3)) for v in face)
        ab=tuple(b[i]-a[i] for i in range(3));ac=tuple(c[i]-a[i] for i in range(3))
        cross=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
        if math.hypot(*cross)<=diagonal**2*1e-14:raise ValueError('SKIN_DEGENERATE_GEOMETRY')
        volume+=sum(a[i]*cross[i] for i in range(3))/6
        for x,y,z in ((face[0],face[1],face[2]),(face[1],face[2],face[0]),(face[2],face[0],face[1])):
            edge=(min(x,y),max(x,y));n,d=edges.get(edge,(0,0));edges[edge]=(n+1,d+(1 if x<y else -1))
            links[x].setdefault(y,set()).add(z);links[x].setdefault(z,set()).add(y)
    if any(n!=2 or d!=0 for n,d in edges.values()):raise ValueError('SKIN_OPEN_OR_UNORIENTED')
    for index,link in enumerate(links):
        if index%256==0:cancel_check()
        if not link or any(len(v)!=2 for v in link.values()):raise ValueError('SKIN_NONMANIFOLD_VERTEX')
        pending=[next(iter(link))];visited=set()
        while pending:
            v=pending.pop()
            if v not in visited:visited.add(v);pending.extend(link[v]-visited)
        if len(visited)!=len(link):raise ValueError('SKIN_NONMANIFOLD_VERTEX')
    # A connected genus-zero visible MPFB body is the supported diagnostic scope.
    pending=[0];visited=set()
    while pending:
        v=pending.pop()
        if v not in visited:visited.add(v);pending.extend(set(links[v])-visited)
    if len(visited)!=len(points) or len(points)-len(edges)+len(triangles)!=2:
        raise ValueError('SKIN_UNSUPPORTED_TOPOLOGY')
    if volume<=diagonal**3*1e-12:raise ValueError('SKIN_NONPOSITIVE_VOLUME')
    return diagonal,volume
