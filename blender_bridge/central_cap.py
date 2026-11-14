"""Bounded diagnostic closures with mandatory unknown regions and safe rays.

These oriented chains are not character parts or physical surface repairs.
Any two closures inside the same box differ by a closed cycle whose winding
outside that box is zero. Classify only outside every protected box, using
rays that avoid the boxes entirely and therefore never hit artificial caps.
"""
import math


def _point(point):
    if len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):
        raise ValueError('Invalid closure coordinates')


def _boxes(boxes):
    if not 1<=len(boxes)<=4:raise ValueError('Invalid protected closure count')
    for box in boxes:
        if len(box)!=2:raise ValueError('Invalid closure bounds')
        for p in box:_point(p)
        if any(box[0][i]>box[1][i] for i in range(3)):raise ValueError('Inverted closure bounds')


def bounded_cap(points: list,body_boundary: list[int],*,cancel_check=lambda:None) -> tuple[list,tuple,tuple,dict]:
    """Fill an oriented boundary as a chain contained in a protected box.

    A non-planar jagged skin boundary need not have a simple planar projection.
    A centroid fan preserves the boundary without flattening any measured skin.
    Its possible self crossings are contained in the box and must never be used
    for physical clearance claims. Callers also validate the complete patch's
    topology, orientation, nondegenerate faces and real-body self intersections.
    """
    cancel_check()
    if (type(body_boundary) is not list or not 3<=len(body_boundary)<=256 or
        any(type(v) is not int or not 0<=v<len(points) for v in body_boundary) or len(set(body_boundary))!=len(body_boundary)):
        raise ValueError('CENTRAL_CAP_INVALID_BOUNDARY')
    coords=[tuple(points[i]) for i in body_boundary]
    for p in coords:
        _point(p)
        if any(abs(v)>10000 for v in p):raise ValueError('CENTRAL_CAP_INVALID_COORDINATES')
    center=tuple(math.fsum(p[i] for p in coords)/len(coords) for i in range(3))
    radius=max(math.dist(p,center) for p in coords)
    if radius<=1e-9:raise ValueError('CENTRAL_CAP_DEGENERATE_CHAIN')
    faces=[(body_boundary[(i+1)%len(body_boundary)],v,len(points)) for i,v in enumerate(body_boundary)]
    for a,b,_ in faces:
        cancel_check();x=tuple(points[a][i]-center[i] for i in range(3));y=tuple(points[b][i]-center[i] for i in range(3))
        cross=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])
        if math.hypot(*cross)<=radius**2*1e-12:raise ValueError('CENTRAL_CAP_DEGENERATE_CHAIN')
    box=(tuple(min(p[i] for p in coords) for i in range(3)),tuple(max(p[i] for p in coords) for i in range(3)))
    if not in_cap_box(center,box,0.):raise ValueError('CENTRAL_CAP_CENTER_OUTSIDE_PROTECTION')
    return faces,center,box,{'vertices':len(coords),'triangles':len(faces),'radius_world':radius,
        'method':'BOUNDED_ORIENTED_FAN_CHAIN'}


def in_cap_box(point,box,margin: float) -> bool:
    _point(point);_boxes([box])
    if type(margin) not in (int,float) or not math.isfinite(margin) or margin<0:raise ValueError('Invalid closure margin')
    return all(box[0][i]-margin<=point[i]<=box[1][i]+margin for i in range(3))


def ray_avoids_cap_boxes(point,direction,boxes,maximum: float,margin: float) -> bool:
    """Conservative closed-slab test: even a grazing cap-box ray is excluded."""
    _point(point);_point(direction);_boxes(boxes)
    if (type(maximum) not in (int,float) or not math.isfinite(maximum) or maximum<=0 or
        type(margin) not in (int,float) or not math.isfinite(margin) or margin<0 or
        not math.isclose(math.hypot(*direction),1.,rel_tol=1e-6)):
        raise ValueError('Invalid bounded diagnostic ray')
    for low,high in boxes:
        near=0.;far=maximum
        for i in range(3):
            lo,hi=low[i]-margin,high[i]+margin
            if abs(direction[i])<1e-15:
                if not lo<=point[i]<=hi:break
            else:
                a,b=(lo-point[i])/direction[i],(hi-point[i])/direction[i]
                if a>b:a,b=b,a
                near=max(near,a);far=min(far,b)
                if far<near:break
        else:return False
    return True


def _directions():
    seeds=((1.,.371,.529),(-.437,1.,.283),(.193,-.613,1.))
    result=[tuple(sign*v/math.hypot(*d) for v in d) for d in seeds for sign in (1.,-1.)]
    for i in range(32):
        z=1-2*(i+.5)/32;angle=i*math.pi*(3-math.sqrt(5));r=math.sqrt(1-z*z)
        result.append((r*math.cos(angle),r*math.sin(angle),z))
    return tuple(result)


DIRECTIONS=_directions()


def safe_ray_directions(point,boxes,diagonal: float) -> tuple:
    if type(diagonal) not in (int,float) or not math.isfinite(diagonal) or diagonal<=0:raise ValueError('Invalid enclosure scale')
    result=[]
    for direction in DIRECTIONS:
        if ray_avoids_cap_boxes(point,direction,boxes,diagonal*4,diagonal*1e-5):result.append(direction)
        if len(result)==3:return tuple(result)
    return ()
