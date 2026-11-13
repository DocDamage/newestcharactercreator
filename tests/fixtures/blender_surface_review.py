"""Real MPFB skin with an isolated, non-shipping deformation fault injection.

This tests a detector, not source-animation compatibility or realistic motion.
No rig, master, review, cache or original evaluated skin is saved or changed.
"""
from pathlib import Path
from hashlib import sha256
import argparse,json,sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from blender_bridge.native_surface_review import SurfaceInspector
from blender_bridge.pose_deformation import _evaluated_vertices


def verify(job: Path,output: Path):
    a=BVHTree.FromPolygons([(0,0,0),(2,0,0),(0,2,0)],[(0,1,2)],all_triangles=True)
    disjoint=BVHTree.FromPolygons([(1.5,1.5,-1),(1.5,1.5,1),(1.5,3,0)],[(0,1,2)],all_triangles=True)
    crossing=BVHTree.FromPolygons([(.5,.5,-1),(.5,.5,1),(.5,1.5,0)],[(0,1,2)],all_triangles=True)
    if a.overlap(disjoint) or a.overlap(crossing)!=[(0,0)]:raise RuntimeError("Triangle test did not distinguish overlap from bounding boxes")
    review=job/'review_motion.blend';before=sha256(review.read_bytes()).hexdigest()
    profile=json.loads((job/'native_mapping.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(review),load_ui=False);bpy.context.scene.frame_set(1)
    human=next(o for o in bpy.data.objects if o.type=='MESH' and len(o.data.vertices)>100)
    rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
    original=_evaluated_vertices(bpy,human)[1]
    graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
    mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles();inspector=SurfaceInspector(profile,rig,human)
        inspector.inspect(mesh,1,original,'a'*64)
        if inspector.status!='CHECKED':raise RuntimeError('Actual MPFB regions unavailable')
        baseline=inspector.rows[0]
        if any(baseline[s]['pair_count'] for s in ('left','right')):raise RuntimeError('Original CI T-pose unexpectedly intersects')
        hp=next(p for p in mesh.polygons if len(p.vertices)>=3 and all(v in inspector.regions['right_hand'] for v in p.vertices))
        triangles=[t for t in mesh.loop_triangles if all(v in inspector.regions['left_arm'] for v in t.vertices)]
        def area(t):
            a,b,c=(human.matrix_world@mesh.vertices[i].co for i in t.vertices)
            return (b-a).cross(c-a).length
        triangle=max(triangles,key=area)
        a,b,c=(human.matrix_world@mesh.vertices[i].co for i in triangle.vertices)
        center=(a+b+c)/3;normal=(b-a).cross(c-a).normalized();edge=(b-a).normalized();size=min((b-a).length,(c-a).length)*.05
        inverse=human.matrix_world.inverted()
        for index,point in zip(hp.vertices[:3],(center+normal*size,center-normal*size,center+edge*size)):
            mesh.vertices[index].co=inverse@point
        mesh.calc_loop_triangles();inspector.inspect(mesh,2,'b'*64,'c'*64)
        count=inspector.rows[-1]['right']['pair_count']
        if count<=0:raise RuntimeError('Real MPFB surface fault was not detected')
    finally:evaluated.to_mesh_clear()
    if _evaluated_vertices(bpy,human)[1]!=original or sha256(review.read_bytes()).hexdigest()!=before:
        raise RuntimeError('Surface fault test changed original skin/review')
    result={'status':'REAL_MPFB_SURFACE_FAULT_DETECTED_ORIGINALS_UNCHANGED','baseline_intersections':0,
            'injected_triangle_pairs':count,'bounds_only_false_positive_rejected':True,'original_skin_and_review_unchanged':True,
            'non_shipping_deformation_fault_injection':True,'animation_compatibility_verified':False}
    output.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);verify(args.job,args.output)
