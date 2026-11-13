"""Read-only actual MPFB geometry faults; no substitute humanoid or saved scene."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from blender_bridge.native_review_reopen import reopen_native,scene_objects
from blender_bridge.native_inputs import read_json
from blender_bridge.native_body_contacts import BodyContactInspector,triangle_pairs
from blender_bridge.skin_winding import observe_hand_skin,signed_ray,DIRECTIONS


def verify(job,output):
    details=json.loads((job/'result.json').read_text(encoding='utf-8'))['details']
    bindings={k:v for k,v in details['bindings'].items() if k!='body_review_sha256'}
    if 'fitted_sha256' in bindings:raise RuntimeError('Original-source geometry faults require an original-only job')
    files=('candidate.blend','review_motion.blend','target_timeline.json','source_snapshot.json','native_mapping.json')
    before={n:sha256((job/n).read_bytes()).hexdigest() for n in files}
    reopen_native(bpy,job,bindings);human,rig=scene_objects(bpy)
    profile=read_json(job/'native_mapping.json',bindings['mapping_sha256'],64*1024)
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
    obj=human.evaluated_get(graph);mesh=obj.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles();inspector=BodyContactInspector(profile,rig,human);inspector.inspect(mesh,1,'','')
        if inspector.status!='CHECKED':raise RuntimeError('Actual geometry fault lacks weighted body/hand selection')
        points=[human.matrix_world@v.co for v in mesh.vertices];triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
        tree=BVHTree.FromPolygons(points,triangles,all_triangles=True);directions=[tuple(Vector(d).normalized()) for d in DIRECTIONS]
        diagonal=(Vector(tuple(max(p[i] for p in points) for i in range(3)))-Vector(tuple(min(p[i] for p in points) for i in range(3)))).length
        def cast(origin,direction,length):return tree.ray_cast(Vector(origin),Vector(direction),length)
        hand=inspector.vertices['right_hand'];centroid=sum((points[i] for i in hand),Vector())/len(hand)
        radius=max((points[i]-centroid).length for i in hand)*.05
        head=rig.pose.bones[profile['landmarks']['head']['target']];bone=head;center=None
        while bone is not None:
            if 'spine' in bone.name.lower():
                candidate=rig.matrix_world@((bone.head+bone.tail)*.5)
                counts=[signed_ray(cast,candidate,d,diagonal,diagonal*1e-6) for d in directions]
                nearest=tree.find_nearest(candidate)
                if counts==[1,1,1] and nearest[0] is not None and nearest[3]>radius*2:
                    center=candidate;break
            bone=bone.parent
        if center is None:raise RuntimeError('No independently ray-checked interior torso point for actual fault')
        modified=[p.copy() for p in points]
        for i in hand:modified[i]=center+(points[i]-centroid)*.05
        body=[(i,t) for i,t in enumerate(triangles) if all(v in inspector.vertices['central_body'] for v in t)]
        selected=[(i,t) for i,t in enumerate(triangles) if all(v in hand for v in t)]
        crossing=triangle_pairs(modified,selected,body,BVHTree)
        if crossing['pair_count']!=0:raise RuntimeError('Buried-hand fault still has hand/central-body surface crossings')
        hands={s:inspector.vertices[s+'_hand'] for s in ('left','right')}
        actual=observe_hand_skin([tuple(p) for p in modified],triangles,hands)
        nonzero=len(actual['right']['nonzero_triangles']);total=len(actual['right']['selected_triangles'])
        if nonzero<total*.9:raise RuntimeError('Signed winding missed most of the actual buried hand')
        faults={}
        for name,faces in (('open',triangles[:-1]),('inverted',[tuple(reversed(t)) for t in triangles])):
            try:observe_hand_skin([tuple(p) for p in points],faces,hands)
            except ValueError as error:faults[name]=str(error)
            else:raise RuntimeError('Invalid actual skin topology was accepted: '+name)
    finally:obj.to_mesh_clear()
    if before!={n:sha256((job/n).read_bytes()).hexdigest() for n in files}:raise RuntimeError('Skin fault changed a saved input')
    summary={'status':'REAL_MPFB_SKIN_INCLUSION_FAULTS_PASSED','buried_hand_central_triangle_pairs':0,
        'buried_hand_nonzero_faces':nonzero,'buried_hand_selected_faces':total,'topology_rejections':faults,
        'original_inputs_unchanged':True,'saved_scene_created':False,'animation_quality_approved':False}
    output.write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(verify(args.job,args.output)))
