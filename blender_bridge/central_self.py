"""Bound transient BVH results before auditing nonadjacent measured body faces."""
MAX_TRANSIENT=262144
MAX_CANDIDATES=1000000


def require_body_surface(points,faces,tree_type,*,cancel_check=lambda:None,
                         transient_limit=MAX_TRANSIENT,candidate_limit=MAX_CANDIDATES) -> dict:
    """Reject nonadjacent crossings or unavailable workload, never a partial pass.

    This is explicitly a nonadjacent-face test. Shared-vertex/edge contacts are
    excluded; it does not by itself certify all adjacent fold or skin quality.
    Internal budget arguments support isolated boundary tests; worker policies
    always use these fixed defaults and do not accept budget options.
    """
    cancel_check();count=len(faces)
    if (not 1<=count<=100000 or not 4<=len(points)<=50004 or type(transient_limit) is not int or
        not count<=transient_limit<=MAX_TRANSIENT or type(candidate_limit) is not int or not 1<=candidate_limit<=MAX_CANDIDATES):
        raise ValueError('CENTRAL_VOLUME_SELF_WORK_BUDGET')
    tree=tree_type.FromPolygons(points,faces,all_triangles=True);total=0;queries=0
    chunk_size=min(64,max(1,transient_limit//count))
    for start in range(0,count,chunk_size):
        cancel_check();chunk=faces[start:start+chunk_size]
        used=sorted({v for face in chunk for v in face});lookup={v:i for i,v in enumerate(used)}
        probe=tree_type.FromPolygons([points[v] for v in used],[tuple(lookup[v] for v in face) for face in chunk],all_triangles=True)
        overlaps=probe.overlap(tree);queries+=1;total+=len(overlaps)
        if len(overlaps)>transient_limit or total>candidate_limit:raise ValueError('CENTRAL_VOLUME_SELF_WORK_BUDGET')
        for a,b in overlaps:
            if type(a) is not int or type(b) is not int or not 0<=a<len(chunk) or not 0<=b<count:
                raise ValueError('CENTRAL_VOLUME_INVALID_BVH_RESULT')
            global_a=start+a
            if global_a<b and not set(faces[global_a])&set(faces[b]):
                raise ValueError('CENTRAL_VOLUME_NONADJACENT_SELF_INTERSECTION')
    return {'method':'BOUNDED_NONADJACENT_BODY_TRIANGLES_V1','triangles':count,'candidate_pairs':total,'chunk_queries':queries,
        'max_transient_pairs':transient_limit,'nonadjacent_pairs':0,'adjacent_fold_quality_verified':False}
