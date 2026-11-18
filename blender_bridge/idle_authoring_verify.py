"""Independent full-clock observations of generated review and armature-only FBX."""
import json
import math

from blender_bridge.face_geometry import evaluated, rest_state
from blender_bridge.face_operations import state_digest
from blender_bridge.fbx_source import inspect_fbx_source
from blender_bridge.idle_authoring_measure import reopened_objects, stable_state, values
from blender_bridge.idle_authoring_math import periodic_derivatives
from blender_bridge.idle_authoring_policy import canonical_path, require, finite_matrix, finite_vector, payload
from blender_bridge.idle_authoring_scene import apply_sample, check_action, matrix, sample_quaternions, world_poses


def _max_difference(a,b):
    require(set(a)==set(b), 'Idle full-bone observation membership differs')
    for row in [*a.values(),*b.values()]:finite_matrix(row)
    return max(abs(x-y) for n in a for x,y in zip(a[n],b[n]))


def wrapped_velocity_residual(first,last,reference_first,reference_last):
    """Compare the identical one-sample wrapped interval, never against zero."""
    positions=(3,7,11);rotations=(0,1,2,4,5,6,8,9,10)
    require(set(first)==set(last)==set(reference_first)==set(reference_last),'Idle wrapped velocity membership differs')
    for collection in (first,last,reference_first,reference_last):
        for row in collection.values():finite_matrix(row)
    result={}
    for label,indices in [('position_m_s',positions),('rotation_matrix_s',rotations)]:
        result[label]=max(abs((first[n][i]-last[n][i])-
                             (reference_first[n][i]-reference_last[n][i]))*30
                          for n in reference_first for i in indices)
    return result


def pose_contract(rig, frame):
    require(max(abs(a-b) for a,b in zip(values(rig.matrix_world),frame['neutral']['rig_world'])) <= 1e-6,
            'Idle moved the actual neutral armature root')
    fixed = {r['name']:r['rest_world'] for r in frame['anatomy']['bones'] if
             r['name']=='root' or r['name'].startswith(('pelvis.','upperleg','lowerleg','foot.','toe'))}
    actual = world_poses(rig)
    require(_max_difference({n:actual[n] for n in fixed},fixed)<=1e-6,
            'Idle moved an actual neutral root/lower-chain helper')
    for bone in rig.pose.bones:
        finite_vector(bone.location);finite_vector(bone.scale);values(bone.matrix_basis)
        q=list(bone.rotation_quaternion)
        require(len(q)==4 and all(math.isfinite(x) for x in q)
                and abs(sum(x*x for x in q)-1)<=1e-5 and bone.rotation_mode=='QUATERNION',
                'Idle quaternion is nonfinite, nonunit or inactive')
        require(bone.location.length<=1e-6 and max(abs(x-1) for x in bone.scale)<=1e-6,
                'Idle requires zero child translations and unit local scales at every sample')
    return actual


def sole_drift(bpy,human,frame):
    points=evaluated(bpy,human,full=True)
    require(len(points)==frame['neutral']['full_vertex_count'], 'Idle changed complete skin indexing')
    for point in points:finite_vector(point)
    for patch in frame['sole_patches'].values():
        require(len(patch['indices'])==len(patch['neutral_world']) and len(patch['indices'])>=3,
                'Idle sole patch coverage differs')
        require(all(type(i) is int and 0<=i<len(points) for i in patch['indices']),'Invalid idle sole indexing')
        for point in patch['neutral_world']:finite_vector(point)
    return max(math.dist(points[i],p) for patch in frame['sole_patches'].values()
               for i,p in zip(patch['indices'],patch['neutral_world']))


def expected_timeline(bpy,human,rig,targets,frame,recipe,request):
    """Direct procedural evaluation, independent of saved F-curves and FBX import."""
    result=[];maximum_drift=0.
    for index in range(1,301):
        apply_sample(bpy,rig,recipe,request,index)
        result.append(pose_contract(rig,frame))
        maximum_drift=max(maximum_drift,sole_drift(bpy,human,frame))
    require(maximum_drift<=request.to_dict()['required_quality']['max_sole_world_drift_m'],
            'Original relaxed recipe moved measured neutral sole patches beyond its bound')
    require(state_digest(rest_state(rig))==frame['target']['rest_sha256']
            and stable_state(bpy,human,rig,targets)==frame['neutral']['stable_invariants_sha256'],
            'Procedural evaluation changed source rest/skin/keys/weights/materials')
    first=sample_quaternions(recipe,request,1);virtual=sample_quaternions(recipe,request,301)
    seam=max(min(sum((a-b)**2 for a,b in zip(first[n],virtual[n]))**.5,
                 sum((a+b)**2 for a,b in zip(first[n],virtual[n]))**.5) for n in first)
    require(seam<=1e-6, 'Original analytic period does not close at its virtual seam')
    periodic=request.to_dict()['periodic_motion']
    a,b=periodic_derivatives(1,periodic),periodic_derivatives(301,periodic)
    derivative=max(abs(a[k]-b[k]) for k in a)
    require(derivative<=1e-12,'Original analytic first derivative does not close')
    return result, {'direct_samples':300,'maximum_neutral_sole_drift_m':maximum_drift,
                    'analytic_virtual_seam_quaternion_residual':seam,
                    'analytic_virtual_seam_first_derivative_residual_rad_s':derivative,
                    'virtual_seam_was_stored':False,'human_review_approved':False}


def verify_review(bpy,root,frame,recipe,request,targets,expected):
    bpy.ops.wm.open_mainfile(filepath=str(canonical_path(root,'authored_idle_review.blend')),load_ui=False)
    human,rig,action=reopened_objects(bpy,frame,targets)
    scene=bpy.context.scene
    require((scene.frame_start,scene.frame_end,scene.render.fps,scene.render.fps_base)==(1,300,30,1.),
            'Saved original idle clock differs')
    check_action(rig,action)
    maximum_error=maximum_drift=0.;first=last=None
    for index,row in enumerate(expected,1):
        scene.frame_set(index);bpy.context.view_layer.update()
        actual=pose_contract(rig,frame)
        if index==1:first=actual
        if index==300:last=actual
        error=_max_difference(actual,row);maximum_error=max(maximum_error,error)
        require(error<=1e-5, 'Saved idle F-curve evaluation differs from independently generated recipe')
        maximum_drift=max(maximum_drift,sole_drift(bpy,human,frame))
    require(maximum_drift<=request.to_dict()['required_quality']['max_sole_world_drift_m'],
            'Saved idle moved measured sole patches beyond its bound')
    require(state_digest(rest_state(rig))==frame['target']['rest_sha256']
            and stable_state(bpy,human,rig,targets)==frame['neutral']['stable_invariants_sha256'],
            'Saved idle evaluation changed source invariants')
    return {'saved_review_samples':300,'maximum_recipe_world_matrix_residual':maximum_error,
            'maximum_saved_neutral_sole_drift_m':maximum_drift,'actual_stored_review_frames':[1,300],
            'wrapped_same_interval_velocity_residual':wrapped_velocity_residual(first,last,expected[0],expected[-1])}


def verify_fbx(bpy,root,frame,expected,source_sha):
    path=canonical_path(root,'authored_idle_source_snapshot.json')
    result=inspect_fbx_source(bpy,canonical_path(root,'original_idle.fbx'),path,source_sha)
    # The existing importer denies external images and independently loads static bind and animation.
    snapshot=json.loads(payload(root,path.name,result['snapshot']['sha256'],64*1024*1024))
    require((snapshot['first_frame'],snapshot['last_frame'],snapshot['fps'])==(2,301,30.)
            and len(snapshot['frames'])==300,'Original FBX did not preserve all300 source2..301/fps30')
    require(all(o.type=='ARMATURE' for o in bpy.context.scene.objects),
            'Original idle FBX redistributed mesh or other non-armature objects')
    bones=snapshot['bones'];wanted={r['name']:r for r in frame['anatomy']['bones']}
    require(len(bones)==len(wanted) and len({b['name'] for b in bones})==len(wanted)
            and all(b['name'] in wanted and b['parent']==wanted[b['name']]['parent'] for b in bones),
            'Original FBX source hierarchy differs from its actual measured MPFB family')
    rest_world=matrix(snapshot['armature_rest_world'])
    rest={b['name']:values(rest_world@matrix(b['matrix'])) for b in bones}
    require(_max_difference(rest,{n:r['rest_world'] for n,r in wanted.items()})<=1e-4,
            'Original FBX changed actual complete world rest frames')
    maximum_error=0.;first=last=None
    for sample,row in zip(snapshot['frames'],expected):
        world=matrix(sample['armature_world'])
        actual={b['name']:values(world@matrix(pose)) for b,pose in zip(bones,sample['poses'])}
        if sample['frame']==2:first=actual
        if sample['frame']==301:last=actual
        error=_max_difference(actual,row);maximum_error=max(maximum_error,error)
        require(error<=1e-4,'Actual imported FBX full timeline differs from original generated recipe')
    return {'source_samples':300,'actual_source_frames':[2,301],'fps':30,
            'maximum_source_recipe_world_matrix_residual':maximum_error,
            'wrapped_same_interval_velocity_residual':wrapped_velocity_residual(first,last,expected[0],expected[-1]),
            'source_bone_count':len(bones),'source_snapshot':result['snapshot'],
            'armature_only':True,'automatic_retarget_family_admission':False}
