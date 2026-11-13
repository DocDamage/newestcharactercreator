"""Canonical saved-Action measurement and separate fresh fitting reproduction."""
from array import array
from hashlib import sha256
import json
import math
import struct
import sys

from blender_bridge.native_fit_scene import original_context,open_fitted,unchanged,check_scene
from blender_bridge.native_fit_policy import BASE_HASHES,fitted_world_poses
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import digest,same_world
from blender_bridge.pose_deformation import _evaluated_vertices,_movement
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.motion_quality import EdgeStrain,JointMotion
from blender_bridge.native_surface_review import SurfaceInspector
from blender_bridge.private_review_render import render_private_review
from blender_bridge.native_hand_fit import angular_bones


def measure_saved_fit(bpy,root,options,*,source_frame_observer=None,fitted_frame_observer=None):
    from mathutils import Matrix,Vector
    baseline,profile,plan,state,reopened=(original_context(bpy,root,options) if source_frame_observer is None else
        original_context(bpy,root,options,source_frame_observer=source_frame_observer))
    human,rig=open_fitted(bpy,root,options,baseline,profile,state)
    edges=evaluated_edges(bpy,human)
    bind=EdgeStrain(state['neutral'],edges);master=EdgeStrain(state['original'],edges)
    if bind.report()!=baseline['bind_edge_strain'] or master.report()!=baseline['master_bind_edge_strain']:
        raise ValueError('Fitted source edge topology differs from the original master')
    inspector=SurfaceInspector(profile,rig,human)
    metrics={p['target']:JointMotion(p['target']) for p in profile['pairs'][1:]}
    root_name=plan['targets'][0];helpers=set(baseline['neutral_target_helpers'])
    diagonal=baseline['model_baseline_diagonal_local'];inverse=human.matrix_world.inverted().to_3x3()
    rows=[];before=previous=None;previous_correction={};previous_velocity={n:Vector() for n in angular_bones(plan)}
    max_speed=max_acceleration=0.
    try:
        for frame,original in enumerate(baseline['full_timeline_frames'],1):
            bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
            if not same_world(rig,state['rig_world']) or not same_world(human,state['mesh_world']):
                raise ValueError('Fitted rig/mesh world transforms changed during playback')
            expected=fitted_world_poses(plan,original['target_global_poses'],frame)
            poses=[]
            for name in plan['targets']:
                pb=rig.pose.bones[name];actual=rig.matrix_world@pb.matrix;wanted=expected[name]
                if (actual.translation-wanted.translation).length>1e-5 or max(abs(actual[i][j]-wanted[i][j]) for i in range(3) for j in range(3))>1e-4:
                    raise ValueError('Saved fitted pose does not implement its declared bounded trajectory')
                poses.append([float(v) for row in actual for v in row])
                if name!=root_name:
                    if pb.location.length!=0:raise ValueError('Saved fit contains unkeyed mapped translation')
                    metrics[name].add(tuple(pb.rotation_quaternion),frame)
                if tuple(pb.scale)!=(1.,1.,1.):raise ValueError('Saved fit contains unkeyed scale')
            for name in helpers:
                pb=rig.pose.bones[name]
                if any(pb.matrix_basis[i][j]!=float(i==j) for i in range(4) for j in range(4)):
                    raise ValueError('Saved fit contains an unkeyed helper pose')
            for name in angular_bones(plan):
                i=plan['targets'].index(name);values=original['target_global_poses'][i]
                old=Matrix([values[j:j+4] for j in range(0,16,4)]).to_quaternion()
                correction=expected[name].to_quaternion()@old.inverted()
                if frame==1:velocity=Vector()
                else:
                    delta=correction@previous_correction[name].inverted()
                    if delta.w<0:delta.negate()
                    axis,angle=delta.to_axis_angle();velocity=axis*math.degrees(angle)*plan['fps']
                speed=velocity.length;acceleration=(velocity-previous_velocity[name]).length*plan['fps']
                if speed>90.+.01 or acceleration>900.+.1:raise ValueError('Saved fit correction has discontinuous angular motion')
                max_speed=max(max_speed,speed);max_acceleration=max(max_acceleration,acceleration)
                previous_correction[name]=correction;previous_velocity[name]=velocity
            points,skin=_evaluated_vertices(bpy,human);actual_edges=evaluated_edges(bpy,human)
            bound=bind.measure(points,actual_edges,frame);original_strain=master.measure(points,actual_edges,frame)
            travel=Vector(original['root_world_head'])-Vector(baseline['target_root_bind_head'])
            offset=inverse@travel;deformed=tuple(tuple(p[i]-offset[i] for i in range(3)) for p in points)
            if before is None:before=deformed
            moved,maximum=_movement(before,deformed)
            adjacent=_movement(previous,deformed)[1] if previous is not None else 0.
            bind_displacement=_movement(state['neutral'],deformed)[1]
            if max(maximum,bind_displacement)>diagonal*1.5 or adjacent>diagonal*.8:
                raise ValueError('Saved fit has extreme or discontinuous evaluated deformation')
            previous=deformed
            mod=human.modifiers[-1];mod.show_viewport=False
            try:raw,raw_sha=_evaluated_vertices(bpy,human)
            finally:mod.show_viewport=True;bpy.context.view_layer.update()
            changed,correction=_movement(raw,points)
            if correction>diagonal*.03:raise ValueError('Saved fit exceeds the unchanged three-percent skin correction bound')
            graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
            mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
            try:
                mesh.calc_loop_triangles();indices=array('I',[0])*(len(mesh.loop_triangles)*3)
                mesh.loop_triangles.foreach_get('vertices',indices)
                if sys.byteorder!='little':indices.byteswap()
                triangle_sha=sha256(indices.tobytes()).hexdigest();triangle_count=len(mesh.loop_triangles)
                inspector.inspect(mesh,frame,skin,triangle_sha)
                if fitted_frame_observer is not None:fitted_frame_observer(bpy,human,rig,mesh,frame,skin,triangle_sha)
            finally:evaluated.to_mesh_clear()
            rows.append({'frame':frame,'source_frame':baseline['source_first_frame']+frame-1,
                'target_global_poses':poses,'skin_sha256':skin,'raw_skin_sha256':raw_sha,'triangle_sha256':triangle_sha,
                'vertex_count':len(points),'triangle_count':triangle_count,'moved_vertices':moved,'max_displacement_local':maximum,
                'max_bind_displacement_local':bind_displacement,'adjacent_max_displacement_local':adjacent,
                'bind_strain':bound,'master_strain':original_strain,
                'skin_correction':{'corrected_vertices':changed,'max_correction_local':correction}})
        end_acceleration=max(v.length*plan['fps'] for v in previous_velocity.values())
        if end_acceleration>900.+.1:raise ValueError('Saved fit ends with discontinuous angular correction')
        check_scene(bpy,human,rig,baseline,profile,state)
        hashes={k:v for k,v in options.items() if k!='fit_report_sha256'}
        return {'schema_version':1,'policy':plan['policy'],'bindings':hashes,'measurement':'FRESH_SAVED_ACTION_V1',
                'frame_count':baseline['source_frame_count'],'source_first_frame':baseline['source_first_frame'],'fps':baseline['fps'],
                'target_rest_frames':state['rest'],'source_polygon_sha256':state['polygons'],
                'mesh_world':state['mesh_world'],'rig_world':state['rig_world'],'original_review_verification':reopened,
                'bind_edge_strain':bind.report(),'master_edge_strain':master.report(),
                'frames':rows,'joint_motion_metrics':[metrics[p['target']].report() for p in profile['pairs'][1:]],
                'surface_review':inspector.report(hashes),
                'angular_correction_metrics':{'max_speed_degrees_s':max_speed,'max_acceleration_degrees_s2':max(max_acceleration,end_acceleration)},
                'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    finally:unchanged(root,options)


def measure_fit(bpy,root,options):
    path=root/'fitted_timeline.json'
    if path.exists() or path.is_symlink():raise ValueError('Refuse to replace a fitted measurement')
    data=measure_saved_fit(bpy,root,options)
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    if len(payload)>64*1024*1024:raise ValueError('Fitted measurement exceeds bounded report size')
    with path.open('xb') as stream:stream.write(payload)
    return {'status':'REAL_NATIVE_FIT_MEASURED','bindings':dict(options),'frames':data['frame_count'],
            'timeline':{'name':path.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},
            'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}


def verify_fit(bpy,root,options):
    expected=read_json(root/'fitted_timeline.json',options['fit_report_sha256'],64*1024*1024)
    actual=measure_saved_fit(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh fitted Action/raw skin/rest/topology measurement differs')
    baseline=read_json(root/'target_timeline.json',options['timeline_sha256'],64*1024*1024)
    profile=read_json(root/'native_mapping.json',options['mapping_sha256'],64*1024)
    from blender_bridge.native_fit_policy import load_fit
    plan=load_fit(root,options,baseline,profile,{n:r['parent'] for n,r in actual['target_rest_frames'].items()})
    human=next(o for o in bpy.data.objects if o.type=='MESH' and len(o.data.vertices)>100)
    frames=plan['render_frames']
    if frames is None:
        active=[i for i,v in enumerate(plan['offsets'],1) if math.hypot(*v)>1e-7]
        peak=max(active,key=lambda i:math.hypot(*plan['offsets'][i-1]))
        chosen={1,baseline['source_frame_count'],active[0],active[-1],peak}
        for frame in range(1,baseline['source_frame_count']+1):
            if len(chosen)==5:break
            chosen.add(frame)
        frames=sorted(chosen)
    rendered=render_private_review(bpy,human,actual['frame_count'],root/'fitted_motion.blend',
        {'fit_bindings':dict(options),'scope':'BOUNDED_TARGET_FIT_NOT_SOURCE_FK_OR_CONTACT_APPROVAL'},sample_frames=frames,
        root_positions={r['frame']:r['root_world_head'] for r in baseline['full_timeline_frames']})
    unchanged(root,options)
    return {'status':'REAL_NATIVE_FIT_VERIFIED','bindings':dict(options),'frames_verified':actual['frame_count'],
            'private_review_renders':rendered,'originals_unchanged':True,
            'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
