"""Read-only original/fitted scene invariants for private target-arm fitting."""
from hashlib import sha256
import struct
import math

from blender_bridge.native_review_reopen import reopen_native,scene_objects,bound_scene,digest,same_world
from blender_bridge.native_inputs import read_json,validate_profile
from blender_bridge.native_fit_policy import BASE_HASHES,load_fit
from blender_bridge.native_rest_frames import capture_rest_frames,same_rest_frames
from blender_bridge.refit_revision import rig_fingerprint
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.native_corrective import NAME,SETTINGS
from blender_bridge.pose_deformation import _evaluated_vertices
from blender_bridge.pose_environment import validate_pose_environment


def input_hashes(options):
    names={'candidate.blend':'master_sha256','review_motion.blend':'review_sha256',
           'source_snapshot.json':'snapshot_sha256','native_mapping.json':'mapping_sha256',
           'target_timeline.json':'timeline_sha256','contact_fit.json':'fit_sha256'}
    if 'fitted_sha256' in options:names['fitted_motion.blend']='fitted_sha256'
    if 'fit_report_sha256' in options:names['fitted_timeline.json']='fit_report_sha256'
    return {name:options[key] for name,key in names.items()}


def unchanged(root,options):
    for name,expected in input_hashes(options).items():
        path=root/name
        if path.is_symlink() or not path.is_file() or digest(path)!=expected:
            raise ValueError('Native fitting changed a bound staged input: '+name)


def polygon_digest(human):
    h=sha256();h.update(struct.pack('<II',len(human.data.vertices),len(human.data.polygons)))
    for polygon in human.data.polygons:
        h.update(struct.pack('<I',len(polygon.vertices)))
        for v in polygon.vertices:h.update(struct.pack('<I',v))
    return h.hexdigest()


def exact_weights_digest(human):
    """Preserve actual float32 memberships, including static mask groups."""
    h=sha256();h.update(struct.pack('<II',len(human.vertex_groups),len(human.data.vertices)))
    for group in human.vertex_groups:
        name=group.name.encode('utf-8');h.update(struct.pack('<II',group.index,len(name)));h.update(name)
    for vertex in human.data.vertices:
        groups=sorted(vertex.groups,key=lambda g:g.group)
        h.update(struct.pack('<II',vertex.index,len(groups)))
        for group in groups:h.update(struct.pack('<If',group.group,float(group.weight)))
    return h.hexdigest()


def bone_controls(rig):
    fields=('use_deform','use_connect','use_inherit_rotation','use_local_location','inherit_scale','bbone_segments')
    return {bone.name:tuple(getattr(bone,key) for key in fields) for bone in rig.data.bones}


def original_context(bpy,root,options):
    unchanged(root,options)
    base={k:options[k] for k in BASE_HASHES}
    reopened=reopen_native(bpy,root,base)
    baseline=read_json(root/'target_timeline.json',base['timeline_sha256'],64*1024*1024)
    profile=validate_profile(read_json(root/'native_mapping.json',base['mapping_sha256'],64*1024),
                             base['source_sha256'],base['snapshot_sha256'],base['master_sha256'])
    human,rig=scene_objects(bpy)
    rest=capture_rest_frames(rig)
    plan=load_fit(root,options,baseline,profile,{n:r['parent'] for n,r in rest.items()})
    state={'rest':rest,'fingerprint':rig_fingerprint(bpy,human),'polygons':polygon_digest(human),'weights':exact_weights_digest(human),'bone_controls':bone_controls(rig),
           'rig_world':[float(v) for row in rig.matrix_world for v in row],
           'mesh_world':[float(v) for row in human.matrix_world for v in row]}
    state.update(original_skin_references(bpy,human,rig,baseline))
    return baseline,profile,plan,state,reopened


def original_skin_references(bpy,human,rig,baseline):
    """Read the same verified bound/original neutral skin without changing poses."""
    state={};mod=human.modifiers[-1];old_position=rig.data.pose_position
    try:
        rig.data.pose_position='REST'
        state['neutral'],state['neutral_sha']=_evaluated_vertices(bpy,human)
        mod.show_viewport=False
        state['original'],state['original_sha']=_evaluated_vertices(bpy,human)
    finally:
        mod.show_viewport=True;rig.data.pose_position=old_position;bpy.context.view_layer.update()
    proof=baseline['skin_deformation']
    if state['neutral_sha']!=proof['bound_neutral_sha256'] or state['original_sha']!=proof['source_neutral_sha256']:
        raise ValueError('Native fitting neutral original/bound skin differs from verified master')
    if max(math.dist(a,b) for a,b in zip(state['original'],state['neutral']))>1e-6:
        raise ValueError('Native fitting neutral references no longer describe the original master')
    return state


def check_scene(bpy,human,rig,baseline,profile,state):
    from mathutils import Matrix
    if (rig.data.pose_position!='POSE' or not same_rest_frames(state['rest'],capture_rest_frames(rig)) or
        rig_fingerprint(bpy,human)!=state['fingerprint'] or polygon_digest(human)!=state['polygons'] or exact_weights_digest(human)!=state['weights'] or bone_controls(rig)!=state['bone_controls'] or
        not same_world(rig,state['rig_world']) or not same_world(human,state['mesh_world'])):
        raise ValueError('Fitted scene changed original rest/roll, bone controls, exact weights, source topology or object transforms')
    mods=tuple(human.modifiers);proof=baseline['skin_deformation']
    if len(mods)!=proof['review_modifier_count']:raise ValueError('Fitted modifier stack differs')
    mod=mods[-1]
    if (mod.name!=NAME or mod.type!='CORRECTIVE_SMOOTH' or not mod.is_bind or
        any(type(getattr(mod,k)) is not type(v) or getattr(mod,k)!=v for k,v in SETTINGS.items()) or
        source_stack(human,rig,modifiers=mods[:-1])!=proof['source_modifiers']):
        raise ValueError('Fitted scene changed source skin stack or corrective binding/settings')
    for data in (human,human.data.shape_keys):
        animation=getattr(data,'animation_data',None)
        if animation and (animation.action or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError('Fitted geometry has unsupported animation or drivers')
    animation=rig.animation_data;action=animation.action if animation else None
    if action is None or len(animation.nla_tracks) or len(animation.drivers):
        raise ValueError('Fitted rig needs one complete Action without NLA/drivers')
    if list(action.frame_range)!=[1.,float(baseline['source_frame_count'])]:raise ValueError('Fitted Action range differs')
    curves=[c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    allowed={(rig.pose.bones[p['target']].path_from_id('rotation_quaternion'),i) for p in profile['pairs'] for i in range(4)}
    allowed|={(rig.pose.bones[profile['pairs'][0]['target']].path_from_id('location'),i) for i in range(3)}
    if len(curves)!=len(allowed) or {(c.data_path,c.array_index) for c in curves}!=allowed:
        raise ValueError('Fitted Action has missing/unrequested helper, scale or translation channels')
    for curve in curves:
        if len(curve.keyframe_points)!=baseline['source_frame_count'] or any(p.interpolation!='LINEAR' or abs(p.co.x-i)>1e-6 for i,p in enumerate(curve.keyframe_points,1)):
            raise ValueError('Fitted Action is not a complete linear bake')
    if abs(bpy.context.scene.render.fps/bpy.context.scene.render.fps_base-baseline['fps'])>1e-6:
        raise ValueError('Fitted Action changed source frame rate')
    # Assigning matrix_basis back decomposes/recomposes rotation and scale. That
    # round trip can alter unkeyed float32 scale and make later rendered skin
    # differ from the canonical measurement. Preserve the exact active channels.
    slot=animation.action_slot
    preserved=[(b,tuple(b.location),tuple(b.scale),b.rotation_mode,
                tuple(b.rotation_quaternion) if b.rotation_mode=='QUATERNION' else
                tuple(b.rotation_axis_angle) if b.rotation_mode=='AXIS_ANGLE' else tuple(b.rotation_euler))
               for b in rig.pose.bones]
    try:
        animation.action=None
        for bone,*_ in preserved:bone.matrix_basis=Matrix.Identity(4)
        validate_pose_environment(rig,human,[b.name for b in rig.pose.bones])
        if _evaluated_vertices(bpy,human)[1]!=state['neutral_sha']:
            raise ValueError('Fitted scene changed neutral bound geometry')
        mod.show_viewport=False
        if _evaluated_vertices(bpy,human)[1]!=state['original_sha']:
            raise ValueError('Fitted scene changed neutral original geometry')
    finally:
        mod.show_viewport=True;animation.action=action;animation.action_slot=slot
        for bone,location,scale,mode,rotation in preserved:
            bone.location=location;bone.scale=scale
            if mode=='QUATERNION':bone.rotation_quaternion=rotation
            elif mode=='AXIS_ANGLE':bone.rotation_axis_angle=rotation
            else:bone.rotation_euler=rotation
        bpy.context.view_layer.update()


def open_fitted(bpy,root,options,baseline,profile,state):
    bound_scene(root/'fitted_motion.blend',options['fitted_sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'fitted_motion.blend'),load_ui=False)
    human,rig=scene_objects(bpy);check_scene(bpy,human,rig,baseline,profile,state)
    return human,rig
