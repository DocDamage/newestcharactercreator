"""Resolution-limited signed-ray observations on actual evaluated closed skin.

Nonzero winding outside a selected hand face can reveal buried skin even without
triangle crossings. Other fingers and all body regions contribute. Ambiguity is
reported explicitly; zero never approves contacts, grasps or animation quality.
"""
import math

from blender_bridge.closed_skin import closed_skin_geometry

POLICY='CLOSED_SKIN_HAND_OUTWARD_WINDING_V1'
DIRECTIONS=((1.,.371,.529),(-.437,1.,.283),(.193,-.613,1.))
MAX_HAND_TRIANGLES=10000
MAX_RAY_HITS=128
MAX_FRAME_RAY_HITS=1000000


def signed_ray(ray_cast,point,direction,diagonal: float,epsilon: float,*,consume=lambda:None) -> int | None:
    """Sum oriented exits minus entries; preserve disagreement/near-hit unknowns."""
    origin=tuple(point);remaining=diagonal*4;total=0
    for _ in range(MAX_RAY_HITS):
        consume();hit,normal,index,distance=ray_cast(origin,direction,remaining)
        if hit is None:return total
        if (normal is None or type(index) is not int or index<0 or
            not isinstance(distance,(int,float)) or not math.isfinite(distance) or not epsilon*.01<=distance<=remaining or
            any(not math.isfinite(v) for v in (*hit,*normal))):return None
        cosine=sum(normal[i]*direction[i] for i in range(3))
        if abs(cosine)<1e-6:return None
        total+=1 if cosine>0 else -1
        remaining-=distance+epsilon
        if remaining<=0:return None
        origin=tuple(hit[i]+direction[i]*epsilon for i in range(3))
    return None


def consistent_winding(counts: list) -> str:
    if len(counts)!=3 or any(type(n) is not int for n in counts) or len(set(counts))!=1:return 'AMBIGUOUS'
    return 'NONZERO' if counts[0] else 'ZERO'


def observe_hand_skin(points: list,triangles: list,hands: dict,*,cancel_check=lambda:None) -> dict:
    """Inspect every selected face at its outward-offset centroid, not vertices.

    Topology is checked for this posed frame, including vertex manifold links.
    BVH/ray arithmetic uses Blender's actual geometry. Offsets and stepping are
    explicit at 1e-6 of world bounding-box diagonal; sub-resolution overlaps and
    coincident/tangent skin are outside this diagnostic's guarantee.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    diagonal,volume=closed_skin_geometry(points,triangles,cancel_check=cancel_check)
    epsilon=diagonal*1e-6
    tree=BVHTree.FromPolygons(points,triangles,all_triangles=True)
    directions=[tuple(Vector(v).normalized()) for v in DIRECTIONS]
    selected={side:[i for i,t in enumerate(triangles) if all(v in hands[side] for v in t)] for side in ('left','right')}
    if any(not ids or len(ids)>MAX_HAND_TRIANGLES for ids in selected.values()):raise ValueError('SKIN_HAND_SELECTION_BUDGET')
    if set(selected['left'])&set(selected['right']):raise ValueError('SKIN_HAND_SELECTION_OVERLAP')
    hits=0
    def consume():
        nonlocal hits
        hits+=1
        if hits%256==0:cancel_check()
        if hits>MAX_FRAME_RAY_HITS:raise ValueError('SKIN_RAY_BUDGET')
    def cast(origin,direction,distance):return tree.ray_cast(Vector(origin),Vector(direction),distance)
    result={'diagonal_world':diagonal,'offset_world':epsilon,'signed_volume_world':volume,'ray_queries':0}
    for side,ids in selected.items():
        nonzero=[];ambiguous=[]
        for index in ids:
            a,b,c=(Vector(points[v]) for v in triangles[index]);normal=(b-a).cross(c-a).normalized()
            point=(a+b+c)/3+normal*epsilon
            counts=[signed_ray(cast,point,d,diagonal,epsilon,consume=consume) for d in directions]
            verdict=consistent_winding(counts)
            if verdict=='NONZERO':nonzero.append(index)
            elif verdict=='AMBIGUOUS':ambiguous.append(index)
        result[side]={'selected_triangles':ids,'nonzero_triangles':nonzero,'ambiguous_triangles':ambiguous}
    result['ray_queries']=hits
    return result
