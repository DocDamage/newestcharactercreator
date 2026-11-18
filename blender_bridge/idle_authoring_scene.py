"""Solve measured relaxed FK, bake exactly 300 original samples, export armature only."""
import math
import re

from blender_bridge.idle_authoring_math import (
    cross, periodic_amplitudes, relaxed_directions, sign_continuous, sub, unit,
)
from blender_bridge.idle_authoring_measure import values
from blender_bridge.idle_authoring_policy import ACTION_NAME, require, canonical_path
from blender_bridge.idle_authoring_policy import finite_vector


def digit_flex_degrees(name: str, baseline: dict) -> float | None:
    """Only specified phalanges rotate; metacarpals/helpers remain identity."""
    match = re.fullmatch(r'finger([1-5])-([1-3])\.([LR])',name)
    if match is None:
        return None
    digit,joint,_=match.groups()
    return baseline['thumb_flex_from_rest_deg'] if digit=='1' else baseline['finger_flex_from_rest_deg'][int(joint)-1]


def matrix(items):
    from mathutils import Matrix
    return Matrix([items[i:i+4] for i in range(0,16,4)])


def _frame(direction, normal):
    from mathutils import Matrix, Vector
    d = Vector(direction).normalized()
    n = Vector(normal); n = (n-d*n.dot(d)).normalized()
    require(n.length > .99 and d.cross(n).length > .99, 'Degenerate measured palm frame')
    return Matrix((d.cross(n), d, n)).transposed()


def solve_baseline(rig, frame, request):
    from mathutils import Matrix, Quaternion, Vector
    rows = frame['anatomy']['bones']; by_name = {r['name']: r for r in rows}
    axes = frame['anatomy']['axes']; baseline = request.to_dict()['baseline']
    desired = {s: relaxed_directions(axes,s,baseline) for s in ('L','R')}
    baseline_quats = {}; computed = {}; maximum_residual = 0.
    world_inverse = rig.matrix_world.inverted()
    segment_local = {}
    for side in ('L','R'):
        for name,tip in [('upperarm01','lowerarm01'),('lowerarm01','wrist')]:
            bone = name+'.'+side
            rest = matrix(by_name[bone]['rest_world']).to_quaternion()
            segment = Vector(sub(by_name[tip+'.'+side]['head_world'],by_name[bone]['head_world'])).normalized()
            segment_local[bone] = rest.inverted() @ segment
    for row in rows:
        pb = rig.pose.bones[row['name']]; bone = pb.bone
        parent = {'parent_matrix':computed[row['parent']], 'parent_matrix_local':pb.parent.bone.matrix_local} if pb.parent else {}
        natural = bone.convert_local_to_pose(Matrix.Identity(4),bone.matrix_local,**parent)
        world = rig.matrix_world @ natural
        basis = Matrix.Identity(4)
        name = pb.name; side = name[-1] if name.endswith(('.L','.R')) else None
        wanted_rotation = None
        if name.startswith(('upperarm01.','lowerarm01.')):
            key = 'upper' if name.startswith('upperarm') else 'lower'
            current = world.to_quaternion() @ segment_local[name]
            wanted_rotation = current.rotation_difference(Vector(desired[side][key])) @ world.to_quaternion()
        elif name.startswith('wrist.'):
            hand = frame['anatomy']['hands'][side]
            rest_q = matrix(row['rest_world']).to_quaternion()
            local_hand = _frame(rest_q.inverted() @ Vector(hand['direction']),rest_q.inverted() @ Vector(hand['normal']))
            wanted_rotation = (_frame(desired[side]['hand'],desired[side]['palm']) @ local_hand.transposed()).to_quaternion()
        elif (degrees := digit_flex_degrees(name,baseline)) is not None:
            hand = frame['anatomy']['hands'][side]
            direction = unit(sub(row['tail_world'],row['head_world']))
            axis = Vector(unit(cross(direction,hand['normal'])))
            local_axis = matrix(row['rest_world']).to_quaternion().inverted() @ axis
            basis = Quaternion(local_axis,math.radians(degrees)).to_matrix().to_4x4()
        if wanted_rotation is not None:
            desired_world = wanted_rotation.to_matrix().to_4x4()
            desired_world.translation = world.translation
            basis = bone.convert_local_to_pose(world_inverse@desired_world,bone.matrix_local,invert=True,**parent)
        values(basis);finite_vector(basis.translation);finite_vector(basis.to_scale())
        require(basis.translation.length < 1e-5 and max(abs(x-1) for x in basis.to_scale()) < 1e-4,
                'Relaxed FK requires unsupported child translation/scale; no T-pose fallback')
        q = basis.to_quaternion().normalized()
        sign_continuous(q)
        baseline_quats[name] = list(q)
        computed[name] = bone.convert_local_to_pose(q.to_matrix().to_4x4(),bone.matrix_local,**parent)
        if name in segment_local:
            key = 'upper' if name.startswith('upperarm') else 'lower'
            actual = (rig.matrix_world@computed[name]).to_quaternion() @ segment_local[name]
            residual = (actual-Vector(desired[side][key])).length
            require(residual < 1e-4, 'Relaxed baseline did not solve the measured anatomical direction')
            maximum_residual = max(maximum_residual,residual)
    periodic_axes = {}
    for name,kind in [('spine03','torso'),('head','head'),('lowerarm01.L','elbow'),('lowerarm01.R','elbow')]:
        axis = Vector(unit(cross(desired[name[-1]]['lower'],axes['forward']))) if kind=='elbow' else Vector(axes['right'])
        local = (rig.matrix_world@computed[name]).to_quaternion().inverted() @ axis
        periodic_axes[name] = {'kind':kind,'axis':list(local.normalized())}
    return {'baseline_quaternions':baseline_quats,'periodic_axes':periodic_axes,
            'baseline_max_anatomical_direction_residual':maximum_residual}


def sample_quaternions(recipe, request, frame):
    from mathutils import Quaternion, Vector
    amplitudes = periodic_amplitudes(frame,request.to_dict()['periodic_motion'])
    result = {}
    for name,values_ in recipe['baseline_quaternions'].items():
        q = Quaternion(values_)
        if name in recipe['periodic_axes']:
            row = recipe['periodic_axes'][name]
            angle = amplitudes[row['kind']] * (-1 if row['kind'] in ('torso','head') else 1)
            q = q @ Quaternion(Vector(row['axis']),angle)
        result[name] = q.normalized()
        sign_continuous(result[name])
    return result


def apply_sample(bpy, rig, recipe, request, frame):
    quaternions = sample_quaternions(recipe,request,frame)
    for pb in rig.pose.bones:
        pb.rotation_mode='QUATERNION';pb.rotation_quaternion=quaternions[pb.name]
        pb.location=(0.,0.,0.);pb.scale=(1.,1.,1.)
    bpy.context.view_layer.update()


def world_poses(rig):
    return {b.name:values(rig.matrix_world@b.matrix) for b in rig.pose.bones}


def action_curves(action):
    return [curve for layer in action.layers for strip in layer.strips
            for bag in strip.channelbags for curve in bag.fcurves]


def check_action(rig, action):
    require(action.name == ACTION_NAME and tuple(action.frame_range)==(1.,300.)
            and len(action.slots)==1 and rig.animation_data.action_slot==action.slots[0],
            'Idle Action slot/name/full stored clock differs')
    expected={(b.path_from_id('rotation_quaternion'),i) for b in rig.pose.bones for i in range(4)}
    curves=action_curves(action)
    require(len(curves)==len(expected) and {(c.data_path,c.array_index) for c in curves}==expected,
            'Idle Action contains missing/extra/duplicate/nonrotation channels')
    for curve in curves:
        points=curve.keyframe_points
        require(len(points)==300 and all(float(p.co.x)==i and math.isfinite(float(p.co.y))
            and p.interpolation=='LINEAR' for i,p in enumerate(points,1)),
            'Idle Action did not preserve all 300 unsimplified samples without virtual sample')


def bake_and_save(bpy, root, human, rig, recipe, request):
    from mathutils import Quaternion
    require(not len(bpy.data.actions) and (not rig.animation_data or not rig.animation_data.action),
            'Idle author refuses to replace inherited Actions')
    scene=bpy.context.scene;scene.render.fps=30;scene.render.fps_base=1.
    scene.frame_start=1;scene.frame_end=300
    previous={}
    for frame in range(1,301):
        scene.frame_set(frame)
        apply_sample(bpy,rig,recipe,request,frame)
        for pb in rig.pose.bones:
            q=sign_continuous(pb.rotation_quaternion,previous.get(pb.name));previous[pb.name]=q
            pb.rotation_quaternion=Quaternion(q)
            require(pb.keyframe_insert('rotation_quaternion',frame=frame) is True,
                    'Blender did not insert original idle quaternion keys')
    action=rig.animation_data.action;action.name=ACTION_NAME
    for curve in action_curves(action):
        for point in curve.keyframe_points:point.interpolation='LINEAR'
    check_action(rig,action)
    scene.frame_set(1);bpy.context.view_layer.update()
    output=canonical_path(root,'authored_idle_review.blend')
    require(not output.exists(), 'Refuse to overwrite an idle review scene')
    require(bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=False,copy=True)=={'FINISHED'},
            'Blender did not save the actual owned idle review')
    for obj in bpy.context.view_layer.objects:obj.select_set(False)
    rig.hide_set(False);rig.select_set(True);bpy.context.view_layer.objects.active=rig
    fbx=canonical_path(root,'original_idle.fbx')
    require(not fbx.exists(), 'Refuse to overwrite an original idle source')
    options={'check_existing':False,'use_selection':True,'object_types':{'ARMATURE'},'global_scale':1.,
        'apply_unit_scale':True,'apply_scale_options':'FBX_SCALE_NONE','use_space_transform':True,
        'bake_space_transform':False,'use_custom_props':False,'add_leaf_bones':False,
        'primary_bone_axis':'Y','secondary_bone_axis':'X','use_armature_deform_only':False,
        'armature_nodetype':'NULL','bake_anim':True,'bake_anim_use_all_bones':True,
        'bake_anim_use_nla_strips':False,'bake_anim_use_all_actions':False,
        'bake_anim_force_startend_keying':True,'bake_anim_step':1.,'bake_anim_simplify_factor':0.,
        'path_mode':'STRIP','embed_textures':False,'batch_mode':'OFF','axis_forward':'-Z','axis_up':'Y'}
    require(bpy.ops.export_scene.fbx(filepath=str(fbx),**options)=={'FINISHED'},
            'Blender did not export the actual original armature-only FBX')
    require(not any(o.select_get() for o in bpy.context.view_layer.objects if o.type=='MESH'),
            'Idle source unexpectedly selected mesh geometry for export')
