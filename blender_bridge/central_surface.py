"""Bounded pairs against actual complete trunk skin; virtual caps are excluded."""
from blender_bridge.native_body_contacts import triangle_pairs
from blender_bridge.body_contact_regions import MAX_PAIR_WORK,MAX_HIGHLIGHTS

POLICY='MEASURED_COMPLETE_TRUNK_HAND_SURFACES_V1'


def observe_central_surfaces(geometry,triangles,polygon_ids,hands,tree_type,*,cancel_check=lambda:None):
    """Return actual global triangle and stable polygon identities for both hands.

    ``geometry`` must come from the closed, bounded actual-polygon trunk
    selector. Its virtual caps establish diagnostic topology but never enter
    this BVH. Recentered coordinates avoid losing local precision to travel.
    An empty crossing result does not prove a hand is outside the body.
    """
    cancel_check()
    if len(triangles)!=len(polygon_ids) or set(hands)!={'left','right'}:
        raise ValueError('COMPLETE_TRUNK_SURFACE_INPUTS_UNAVAILABLE')
    body=[(index,triangles[index]) for index in geometry.body_triangle_ids]
    if not body or len(body)!=len(geometry.body_faces):
        raise ValueError('COMPLETE_TRUNK_SURFACE_BODY_UNAVAILABLE')
    # Each compact face must preserve the exact global triangle order expected
    # by triangle_pairs when it converts BVH overlap IDs back to global IDs.
    lookup={v:i for i,v in enumerate(geometry.body_vertex_ids)}
    if (len(lookup)!=len(geometry.body_vertex_ids) or
        any(tuple(lookup[v] for v in tri)!=tuple(face)
            for (_,tri),face in zip(body,geometry.body_faces))):
        raise ValueError('COMPLETE_TRUNK_SURFACE_BODY_ORDER_DIFFERS')
    selected={side:[(i,t) for i,t in enumerate(triangles) if set(t)<=members]
              for side,members in hands.items()}
    if (any(not rows or len(rows)*len(body)>MAX_PAIR_WORK for rows in selected.values()) or
        {i for i,_ in selected['left']}&{i for i,_ in selected['right']}):
        raise ValueError('COMPLETE_TRUNK_SURFACE_SELECTION_OR_WORKLOAD')
    tree=tree_type.FromPolygons(geometry.body_points,geometry.body_faces,all_triangles=True)
    result={'body_triangle_ids':list(geometry.body_triangle_ids)};highlights=0
    for side in ('left','right'):
        cancel_check()
        hit=triangle_pairs(geometry.skin_points,selected[side],body,tree_type,body_tree=tree)
        hit['selected_hand_triangles']=[i for i,_ in selected[side]]
        hit['hand_polygons']=sorted({polygon_ids[i] for i in hit['hand_triangles']})
        hit['body_polygons']=sorted({polygon_ids[i] for i in hit['central_triangles']})
        highlights+=len(hit['hand_triangles'])+len(hit['central_triangles'])
        if highlights>MAX_HIGHLIGHTS:raise ValueError('COMPLETE_TRUNK_SURFACE_HIGHLIGHTS_EXCEEDED')
        result[side]=hit
    cancel_check()
    return result
