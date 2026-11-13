"""Non-shipping central-body detector fault on real evaluated MPFB geometry.

Only a disposable evaluated mesh is changed. This is not an authored animation
or a claim that any source pack has realistic contact or compatible motion.
"""
from pathlib import Path
from hashlib import sha256
import argparse,json,sys
import bpy
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from blender_bridge.native_body_contacts import BodyContactInspector,triangle_pairs
from blender_bridge.pose_deformation import _evaluated_vertices


def verify(job,output):
    # AABB overlap alone must not produce a surface crossing verdict.
    points=[(0,0,0),(2,0,0),(0,2,0),(1.5,1.5,-1),(1.5,1.5,1),(1.5,3,0)]
    disjoint=triangle_pairs(points,[(17,(0,1,2))],[(29,(3,4,5))],BVHTree)
    if disjoint['pair_count']:raise RuntimeError('Central-body detector accepted a bounds-only overlap')
    review=job/'review_motion.blend';before=sha256(review.read_bytes()).hexdigest()
    profile=json.loads((job/'native_mapping.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(review),load_ui=False);bpy.context.scene.frame_set(1)
    human=next(o for o in bpy.data.objects if o.type=='MESH' and len(o.data.vertices)>100)
    rig=next(o for o in bpy.data.objects if o.type=='ARMATURE');original=_evaluated_vertices(bpy,human)[1]
    graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
    mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles();inspector=BodyContactInspector(profile,rig,human)
        inspector.inspect(mesh,1,original,'a'*64)
        if inspector.status!='CHECKED':raise RuntimeError('Actual MPFB central-body regions unavailable')
        selected={k:[t for t in mesh.loop_triangles if all(v in members for v in t.vertices)]
                  for k,members in inspector.vertices.items()}
        def area(t):
            a,b,c=(human.matrix_world@mesh.vertices[i].co for i in t.vertices)
            return (b-a).cross(c-a).length
        hand=max(selected['right_hand'],key=area);body=max(selected['central_body'],key=area)
        a,b,c=(human.matrix_world@mesh.vertices[i].co for i in body.vertices)
        center=(a+b+c)/3;normal=(b-a).cross(c-a).normalized();edge=(b-a).normalized()
        size=min((b-a).length,(c-a).length)*.05;inverse=human.matrix_world.inverted()
        for index,point in zip(hand.vertices,(center+normal*size,center-normal*size,center+edge*size)):
            mesh.vertices[index].co=inverse@point
        mesh.calc_loop_triangles();points=[human.matrix_world@v.co for v in mesh.vertices]
        actual=triangle_pairs(points,[(hand.index,tuple(hand.vertices))],[(body.index,tuple(body.vertices))],BVHTree)
        if actual['pair_count']!=1:raise RuntimeError('Actual injected MPFB triangles did not cross')
        inspector.inspect(mesh,2,'b'*64,'c'*64);hit=inspector.rows[-1]['right']
        if hand.index not in hit['hand_triangles'] or body.index not in hit['central_triangles']:
            raise RuntimeError('Full central-body inspector did not highlight the injected real triangles')
        count=hit['pair_count']
    finally:evaluated.to_mesh_clear()
    if _evaluated_vertices(bpy,human)[1]!=original or sha256(review.read_bytes()).hexdigest()!=before:
        raise RuntimeError('Central-body fault changed original evaluated skin or review file')
    result={'status':'REAL_MPFB_BODY_FAULT_DETECTED_ORIGINALS_UNCHANGED','injected_triangle_pairs':count,
        'actual_global_triangle_ids_highlighted':True,'bounds_only_false_positive_rejected':True,
        'original_skin_and_review_unchanged':True,'non_shipping_deformation_fault_injection':True,
        'animation_compatibility_verified':False}
    output.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);verify(args.job,args.output)
