"""Bounded hand probes against measured trunk skin; closure boxes stay unknown."""
from hashlib import sha256
import struct

from blender_bridge.central_cap import in_cap_box,safe_ray_directions
from blender_bridge.central_geometry import central_geometry,outward_probe
from blender_bridge.central_self import require_body_surface
from blender_bridge.skin_winding import signed_ray,consistent_winding,MAX_FRAME_RAY_HITS,MAX_HAND_TRIANGLES

POLICY='MEASURED_TRUNK_CAP_FREE_HAND_ENCLOSURE_V1'


def observe_central_enclosure(points,triangles,polygon_ids,polygons,members,hands,world,*,cancel_check=lambda:None):
    """Measure every hand triangle, retaining stable source polygon identities.

    A definitive probe uses only actual skin triangles and three rays that
    avoid every protected boundary box. Ambiguity is never treated as clearance.
    This does not certify contact, adjacent folds, grasps or animation quality.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    geometry=central_geometry(points,triangles,polygon_ids,polygons,members,world,cancel_check=cancel_check)
    audit=require_body_surface(geometry.body_points,geometry.body_faces,BVHTree,cancel_check=cancel_check)
    tree=BVHTree.FromPolygons(geometry.body_points,geometry.body_faces,all_triangles=True)
    selected={s:[i for i,t in enumerate(triangles) if all(v in hands[s] for v in t)] for s in ('left','right')}
    if any(not ids or len(ids)>MAX_HAND_TRIANGLES for ids in selected.values()):raise ValueError('CENTRAL_VOLUME_HAND_SELECTION_BUDGET')
    if set(selected['left'])&set(selected['right']):raise ValueError('CENTRAL_VOLUME_HAND_SELECTION_OVERLAP')
    epsilon=geometry.diagonal*1e-6;hits=0
    def consume():
        nonlocal hits
        hits+=1
        if hits%256==0:cancel_check()
        if hits>MAX_FRAME_RAY_HITS:raise ValueError('CENTRAL_VOLUME_RAY_BUDGET')
    def cast(origin,direction,distance):return tree.ray_cast(Vector(origin),Vector(direction),distance)
    result={'diagonal_world':geometry.diagonal,'offset_world':epsilon,'signed_volume_world':geometry.signed_volume,
        'pivot_local':list(geometry.pivot_local),'origin_world':list(geometry.origin_world),
        'bounds':[list(p) for p in geometry.bounds],'cap_boxes':[[list(p) for p in box] for box in geometry.cap_boxes],
        'boundaries':[list(loop) for loop in geometry.boundaries],'body_triangle_ids':list(geometry.body_triangle_ids),
        'body_surface_audit':audit,'ray_queries':0}
    for side,ids in selected.items():
        nonzero=[];ambiguous=[];trace=sha256()
        for index in ids:
            cancel_check();point=outward_probe(geometry.skin_points,triangles[index],epsilon)
            if any(in_cap_box(point,box,epsilon*10) for box in geometry.cap_boxes):verdict='AMBIGUOUS'
            elif not in_cap_box(point,geometry.bounds,epsilon*10):verdict='ZERO'
            elif tree.find_nearest(Vector(point),epsilon*10)[0] is not None:verdict='AMBIGUOUS'
            else:
                directions=safe_ray_directions(point,geometry.cap_boxes,geometry.diagonal)
                values=[signed_ray(cast,point,d,geometry.diagonal,epsilon,consume=consume) for d in directions]
                verdict='AMBIGUOUS' if len(values)!=3 or any(type(v) is int and v not in (0,1) for v in values) else consistent_winding(values)
            trace.update(struct.pack('<IB',index,{'ZERO':0,'NONZERO':1,'AMBIGUOUS':2}[verdict]))
            if verdict=='NONZERO':nonzero.append(index)
            elif verdict=='AMBIGUOUS':ambiguous.append(index)
        result[side]={'selected_triangles':ids,'nonzero_triangles':nonzero,'ambiguous_triangles':ambiguous,
            'inside_polygons':sorted({polygon_ids[i] for i in nonzero}),
            'ambiguous_polygons':sorted({polygon_ids[i] for i in ambiguous}),'classification_sha256':trace.hexdigest()}
    result['ray_queries']=hits
    return result
