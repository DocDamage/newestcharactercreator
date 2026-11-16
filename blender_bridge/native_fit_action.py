"""Bake one explicitly bounded fitted Action to a new disposable scene only."""
from blender_bridge.native_fit_scene import original_context,unchanged,check_scene
from blender_bridge.native_fit_policy import fitted_world_poses
from blender_bridge.native_review_reopen import scene_objects,digest
from blender_bridge.motion_quality import JointMotion
from blender_bridge.native_reference import RootRotation
from blender_bridge.native_hand_fit import changed


def stage_native_fit(bpy,root,options):
    from mathutils import Matrix,Vector
    baseline,profile,plan,state,reopened=original_context(bpy,root,options)
    output=root/'fitted_motion.blend'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace a fitted scene output')
    human,rig=scene_objects(bpy)
    action=rig.animation_data.action.copy();action.name='UCC_PRIVATE_BOUNDED_TARGET_FIT_UNAPPROVED'
    rig.animation_data.action=action
    ordered=sorted(rig.pose.bones,key=lambda b:len(b.parent_recursive))
    mapped=set(plan['targets']);root_name=plan['targets'][0]
    modified=({n for s in ('left','right') for n in (*plan[s]['chain'],plan[s]['clavicle'])}
              if 'active_frames' in plan else set(plan['chain']))
    metrics={n:JointMotion(n) for n in mapped if n!=root_name};root_metric=RootRotation()
    inverse=rig.matrix_world.inverted();max_local_translation=max_scale_error=0.
    maximum_residual=0.
    try:
        for frame,row in enumerate(baseline['full_timeline_frames'],1):
            for pb in rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
            bpy.context.scene.frame_set(frame)
            expected=fitted_world_poses(plan,row['target_global_poses'],frame)
            computed={}
            for pb in ordered:
                bone=pb.bone
                kw={'parent_matrix':computed[pb.parent.name],'parent_matrix_local':pb.parent.bone.matrix_local} if pb.parent else {}
                tracker=root_metric if pb.name==root_name else metrics.get(pb.name)
                if pb.name in modified and changed(plan,frame):
                    desired=inverse@expected[pb.name]
                    basis=bone.convert_local_to_pose(desired,bone.matrix_local,invert=True,**kw)
                    scale_error=max(abs(v-1) for v in basis.to_scale());max_scale_error=max(max_scale_error,scale_error)
                    if pb.name!=root_name:max_local_translation=max(max_local_translation,basis.translation.length)
                    if scale_error>1e-4 or (pb.name!=root_name and basis.translation.length>1e-5):
                        raise ValueError('Fitted arm cannot preserve the actual helper hierarchy without scaling/translation')
                    pb.rotation_mode='QUATERNION'
                    pb.rotation_quaternion=tracker.add(tuple(basis.to_quaternion().normalized()),frame)
                    pb.location=basis.translation if pb.name==root_name else Vector((0.,0.,0.))
                    pb.scale=(1.,1.,1.)
                    pb.keyframe_insert('rotation_quaternion',frame=frame)
                elif pb.name in mapped:
                    tracker.add(tuple(pb.rotation_quaternion),frame)
                else:pb.matrix_basis=Matrix.Identity(4)
                computed[pb.name]=bone.convert_local_to_pose(pb.matrix_basis,bone.matrix_local,**kw)
            bpy.context.view_layer.update()
            for name,wanted in expected.items():
                actual=rig.matrix_world@rig.pose.bones[name].matrix
                position=(actual.translation-wanted.translation).length
                rotation=max(abs(actual[i][j]-wanted[i][j]) for i in range(3) for j in range(3))
                if position>1e-5 or rotation>1e-4:raise ValueError('Actual fitted pose differs from its declared IK endpoint/rotation')
                maximum_residual=max(maximum_residual,position,rotation)
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        if len(curve.keyframe_points)!=baseline['source_frame_count']:raise ValueError('Incomplete native fitted bake')
                        for point in curve.keyframe_points:point.interpolation='LINEAR'
        bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
        check_scene(bpy,human,rig,baseline,profile,state)
        unchanged(root,options)
        if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=False,copy=True):
            raise ValueError('Blender did not save a new fitted Action scene')
        if not output.is_file() or not 10000<output.stat().st_size<=512*1024*1024:
            raise ValueError('Invalid fitted Action scene size')
        return {'status':'REAL_NATIVE_FIT_ACTION_STAGED','bindings':dict(options),
                'frames':baseline['source_frame_count'],'original_review_verification':reopened,
                'fitted_scene':{'name':output.name,'bytes':output.stat().st_size,'sha256':digest(output)},
                'target_rest_frames':state['rest'],'max_ik_residual':maximum_residual,
                'max_unkeyed_translation':max_local_translation,'max_scale_error':max_scale_error,
                'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    finally:unchanged(root,options)
