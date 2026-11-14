"""Actual MPFB trunk/hand geometry faults, no substitute assets or saved scenes."""
from hashlib import sha256
from dataclasses import replace
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent)]
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from blender_bridge.body_contact_review import SOURCE_FIELDS,unchanged,input_hashes
from blender_bridge.native_review_reopen import reopen_native,scene_objects
from blender_bridge.native_inputs import read_json
from blender_bridge.native_body_contacts import BodyContactInspector
from blender_bridge.body_contact_regions import weighted_central_region
from blender_bridge.central_regions import volume_regions
from blender_bridge.central_enclosure import observe_central_enclosure
from blender_bridge.central_geometry import central_geometry,outward_probe
from blender_bridge.central_surface import observe_central_surfaces
from blender_bridge.central_cap import in_cap_box,safe_ray_directions
from blender_bridge.central_self import require_body_surface
from blender_bridge.skin_winding import signed_ray,consistent_winding
from blender_solid_angle_oracle import solid_angle_values


def verify(job,output):
    if output.exists() or output.is_symlink():raise RuntimeError('Refuse to replace geometry fault evidence')
    result=json.loads((job/'result.json').read_text(encoding='utf-8'))['details']
    base={k:result['bindings'][k] for k in SOURCE_FIELDS};unchanged(job,base)
    before={n:sha256((job/n).read_bytes()).hexdigest() for n in input_hashes(base)}
    reopened=reopen_native(bpy,job,base);human,rig=scene_objects(bpy)
    profile=read_json(job/'native_mapping.json',base['mapping_sha256'],64*1024)
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
    obj=human.evaluated_get(graph);mesh=obj.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles();parents={b.name:b.parent.name if b.parent else None for b in rig.data.bones}
        deform={b.name for b in rig.data.bones if b.use_deform};regions,roots=volume_regions(profile,parents,deform)
        names={g.index:g.name for g in human.vertex_groups};members=set()
        for vertex in mesh.vertices:
            label=weighted_central_region({names[g.group]:g.weight for g in vertex.groups},regions,deform)
            if label=='central_body':members.add(vertex.index)
        triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
        geometry=central_geometry([tuple(v.co) for v in mesh.vertices],triangles,[t.polygon_index for t in mesh.loop_triangles],
            [tuple(p.vertices) for p in mesh.polygons],members,tuple(float(v) for row in human.matrix_world for v in row))
        audit=require_body_surface(geometry.body_points,geometry.body_faces,BVHTree)
        selected=BodyContactInspector(profile,rig,human);selected.inspect(mesh,1,'fault-test-only','fault-test-only')
        if selected.status!='CHECKED':raise RuntimeError('Actual fault lacks weighted hand identities')
        hand=selected.vertices['right_hand'];assert not hand&set(geometry.body_vertex_ids)
        center_hand=tuple(sum(geometry.skin_points[v][i] for v in hand)/len(hand) for i in range(3))
        radius=max(math.dist(geometry.skin_points[v],center_hand) for v in hand)*.05
        tree=BVHTree.FromPolygons(geometry.body_points,geometry.body_faces,all_triangles=True)
        def cast(origin,direction,length):return tree.ray_cast(Vector(origin),Vector(direction),length)
        def ancestry(name):
            path=[]
            while name is not None:path.append(name);name=parents[name]
            return path
        common=next(n for n in ancestry(roots['left_arm']) if n in ancestry(roots['right_arm']))
        center=None
        for name in ancestry(common):
            bone=rig.pose.bones[name];world=rig.matrix_world@((bone.head+bone.tail)*.5)
            point=tuple(world[i]-geometry.origin_world[i] for i in range(3))
            if any(in_cap_box(point,box,radius*2) for box in geometry.cap_boxes):continue
            directions=safe_ray_directions(point,geometry.cap_boxes,geometry.diagonal)
            nearest=tree.find_nearest(Vector(point))
            if len(directions)==3 and nearest[0] is not None and nearest[3]>radius*2:
                if [signed_ray(cast,point,d,geometry.diagonal,geometry.diagonal*1e-6) for d in directions]==[1,1,1]:
                    center=point;break
        if center is None:raise RuntimeError('No independently checked interior trunk ball for real hand fault')
        moved=list(geometry.skin_points)
        for v in hand:moved[v]=tuple(center[i]+.05*(geometry.skin_points[v][i]-center_hand[i]) for i in range(3))
        hand_faces=[t for t in triangles if all(v in hand for v in t)]
        hand_tree=BVHTree.FromPolygons(moved,hand_faces,all_triangles=True)
        if hand_tree.overlap(tree):raise RuntimeError('Hand fault is not fully inside without measured surface crossings')
        counts={'ZERO':0,'NONZERO':0,'AMBIGUOUS':0};queries=[]
        for t in hand_faces:
            point=outward_probe(tuple(moved),t,geometry.diagonal*1e-6);queries.append(point)
            if any(in_cap_box(point,box,geometry.diagonal*1e-5) for box in geometry.cap_boxes):
                raise RuntimeError('Interior fault ball touches an explicitly unknown cap region')
            directions=safe_ray_directions(point,geometry.cap_boxes,geometry.diagonal)
            values=[signed_ray(cast,point,d,geometry.diagonal,geometry.diagonal*1e-6) for d in directions]
            verdict='AMBIGUOUS' if len(values)!=3 else consistent_winding(values);counts[verdict]+=1
        production=observe_central_enclosure(moved,triangles,[t.polygon_index for t in mesh.loop_triangles],
            [tuple(p.vertices) for p in mesh.polygons],members,
            {s:selected.vertices[s+'_hand'] for s in ('left','right')},(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.))
        if (len(production['right']['nonzero_triangles'])!=len(hand_faces) or production['right']['ambiguous_triangles'] or
            not production['right']['inside_polygons']):raise RuntimeError('Production sampler missed fully enclosed actual hand')
        hands={s:selected.vertices[s+'_hand'] for s in ('left','right')}
        polygon_ids=[t.polygon_index for t in mesh.loop_triangles]
        buried=observe_central_surfaces(replace(geometry,skin_points=tuple(moved)),triangles,polygon_ids,hands,BVHTree)
        if buried['right']['pair_count']!=0:raise RuntimeError('Fully buried hand unexpectedly crosses the complete actual trunk skin')
        # Move one actual hand triangle across an actual trunk triangle omitted
        # by the older head/spine-only weighted partition. No source is saved.
        legacy=selected.vertices['central_body']
        omitted=next(i for i in geometry.body_triangle_ids if not set(triangles[i])<=legacy and
            (Vector(geometry.skin_points[triangles[i][1]])-Vector(geometry.skin_points[triangles[i][0]])).cross(
             Vector(geometry.skin_points[triangles[i][2]])-Vector(geometry.skin_points[triangles[i][0]])).length>1e-9)
        a,b,c=(Vector(geometry.skin_points[v]) for v in triangles[omitted]);middle=(a+b+c)/3
        normal=(b-a).cross(c-a).normalized();tangent=(b-a).normalized()
        extent=min((b-a).length,(c-a).length,(c-b).length)*.1
        chosen=next(i for i,t in enumerate(triangles) if set(t)<=hand);fault=list(geometry.skin_points)
        for v,p in zip(triangles[chosen],(middle+normal*extent,middle-normal*extent+tangent*extent,
                                         middle-normal*extent-tangent*extent)):fault[v]=tuple(p)
        crossing=observe_central_surfaces(replace(geometry,skin_points=tuple(fault)),triangles,polygon_ids,hands,BVHTree)
        if omitted not in crossing['right']['central_triangles'] or chosen not in crossing['right']['hand_triangles']:
            raise RuntimeError('Complete trunk producer missed actual crossing outside the older partition')
        from unittest.mock import patch
        with patch('blender_bridge.central_surface.MAX_PAIR_WORK',1):
            try:observe_central_surfaces(geometry,triangles,polygon_ids,hands,BVHTree)
            except ValueError as error:
                if str(error)!='COMPLETE_TRUNK_SURFACE_SELECTION_OR_WORKLOAD':raise
            else:raise RuntimeError('Complete trunk pair budget produced a partial verdict')
        with patch('blender_bridge.central_enclosure.MAX_FRAME_RAY_HITS',1):
            try:observe_central_enclosure(moved,triangles,[t.polygon_index for t in mesh.loop_triangles],
                [tuple(p.vertices) for p in mesh.polygons],members,
                {s:selected.vertices[s+'_hand'] for s in ('left','right')},(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.))
            except ValueError as error:
                if str(error)!='CENTRAL_VOLUME_RAY_BUDGET':raise
            else:raise RuntimeError('Production ray budget returned partial enclosure verdict')
        exact=solid_angle_values(geometry.body_points,geometry.body_faces+geometry.cap_faces,queries)
        if any(not math.isfinite(v) or abs(v-1)>1e-5 for v in exact):raise RuntimeError('Actual interior hand differs from independent enclosure oracle')
        if counts['ZERO'] or counts['NONZERO']<len(hand_faces)*.9:raise RuntimeError('Cap-free rays miss the actual enclosed hand')
        # Controlled copied-body fault: two real, nonadjacent body triangles
        # intersect. Neither the mesh datablock nor original scene is changed.
        bad=list(geometry.body_points);first=geometry.body_faces[0]
        other=next(face for face in geometry.body_faces[1:] if not set(face)&set(first))
        middle=tuple(sum(bad[v][i] for v in other)/3 for i in range(3))
        for a,b in zip(first,other):bad[a]=tuple(middle[i]+.5*(bad[b][i]-middle[i]) for i in range(3))
        try:require_body_surface(bad,geometry.body_faces,BVHTree)
        except ValueError as error:
            if str(error)!='CENTRAL_VOLUME_NONADJACENT_SELF_INTERSECTION':raise
        else:raise RuntimeError('Actual nonadjacent body collision was accepted')
        try:require_body_surface(geometry.body_points,geometry.body_faces,BVHTree,candidate_limit=1)
        except ValueError as error:
            if str(error)!='CENTRAL_VOLUME_SELF_WORK_BUDGET':raise
        else:raise RuntimeError('Body candidate budget produced a partial verdict')
        for box in geometry.cap_boxes:
            midpoint=tuple((box[0][i]+box[1][i])/2 for i in range(3))
            if safe_ray_directions(midpoint,geometry.cap_boxes,geometry.diagonal):raise RuntimeError('Protected closure interior received definite rays')
    finally:obj.to_mesh_clear()
    unchanged(job,base)
    if before!={n:sha256((job/n).read_bytes()).hexdigest() for n in input_hashes(base)}:raise RuntimeError('Fault test changed a staged source')
    summary={'status':'REAL_MPFB_CENTRAL_ENCLOSURE_FAULTS_PASSED','saved_source_frames_reopened':reopened['frames_verified'],
        'measured_body_triangles':len(geometry.body_faces),'virtual_boundaries':len(geometry.boundaries),
        'fully_enclosed_hand_triangle_pairs':0,'actual_hand_probes':len(hand_faces),'cap_free_classifications':counts,
        'independent_oracle_all_hand_probes_inside':True,'production_sampler_detected_every_enclosed_probe':True,
        'production_ray_budget_rejected_without_partial_verdict':True,'nonadjacent_body_fault_rejected':True,
        'bounded_body_workload_rejected_without_partial_verdict':True,'cap_interiors_never_definite':True,
        'original_inputs_unchanged':True,'saved_scene_created':False,'anatomical_or_animation_quality_approved':False,
        'body_surface_audit':audit,'complete_surface_faults':{
            'actual_omitted_region_triangle':omitted,'actual_omitted_region_crossing_detected':True,
            'global_hand_triangle_highlighted':chosen in crossing['right']['hand_triangles'],
            'injected_pairs':crossing['right']['pair_count'],'fully_buried_complete_surface_pairs':buried['right']['pair_count'],
            'buried_hand_requires_separate_enclosure':True,'pair_budget_rejected_without_partial_verdict':True}}
    with output.open('x',encoding='utf-8') as stream:json.dump(summary,stream,indent=2,allow_nan=False)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(verify(args.job,args.output)))
