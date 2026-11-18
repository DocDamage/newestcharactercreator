"""Actual native skin/Action and selected-frame raster measurements on private copies."""
from array import array
from hashlib import sha256
from pathlib import Path
from typing import Any
import math,struct,sys
import re

from blender_bridge.face_operations import state_digest
from blender_bridge.fbx_source import pose_digest
from blender_bridge.native_corrective import NAME
from blender_bridge.expression_normals import corners
from blender_bridge.skin_material_model import checked_owned_material
from blender_bridge.body_sprite_scene import PREFIX
from blender_bridge.face_policy import digest
from ucc.jobs.private_render_evidence import png_measurements
from ucc.core.target_action_format import canonical_bytes


def validate_clock(scene: Any) -> None:
    if (scene.frame_start!=1 or scene.frame_end!=300 or scene.render.fps!=30
            or scene.render.fps_base!=1. or scene.use_preview_range):
        raise ValueError('Body sprite saved scene must retain the complete native1-300 clock at30fps')


def action_state(bpy: Any,rig: Any) -> str:
    animation=rig.animation_data;action=animation.action if animation else None
    if (action is None or len(animation.drivers) or len(animation.nla_tracks)
            or set(bpy.data.actions.keys())!={action.name}):
        raise ValueError('Body sprites require only the original complete rig Action, without drivers or NLA')
    curves=[c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    rows=[]
    for curve in curves:
        if curve.modifiers or curve.mute or len(curve.keyframe_points)!=300:
            raise ValueError('Body sprite Action has modifiers, muted or incomplete channels')
        rows.append({'path':curve.data_path,'index':curve.array_index,'extrapolation':curve.extrapolation,
            'points':[{'co':list(p.co),'left':list(p.handle_left),'right':list(p.handle_right),
                'left_type':p.handle_left_type,'right_type':p.handle_right_type,
                'interpolation':p.interpolation,'easing':p.easing,'type':p.type,
                'amplitude':p.amplitude,'back':p.back,'period':p.period} for p in curve.keyframe_points]})
    return state_digest({'name':action.name,'range':list(action.frame_range),
        'slots':[(slot.identifier,slot.target_id_type) for slot in action.slots],
        'curves':sorted(rows,key=lambda row:(row['path'],row['index']))})


def surface(bpy: Any,human: Any) -> dict:
    bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
    evaluated=human.evaluated_get(graph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles();n=len(mesh.vertices);t=len(mesh.loop_triangles)
        if (n,t)!=(13380,26756):raise ValueError('Body sprites require the complete admitted visible MPFB surface')
        positions=array('f',[0.])*(3*n);triangles=array('I',[0])*(3*t)
        mesh.vertices.foreach_get('co',positions);mesh.loop_triangles.foreach_get('vertices',triangles)
        if any(not math.isfinite(v) or abs(v)>10000 for v in positions):raise ValueError('Invalid body-sprite skin coordinates')
        quantized=sha256()
        for index in range(0,len(positions),3):quantized.update(struct.pack('<qqq',*(round(v*1000000) for v in positions[index:index+3])))
        if sys.byteorder!='little':positions.byteswap();triangles.byteswap()
        return {'evaluated_sha256':quantized.hexdigest(),'positions_sha256':sha256(positions.tobytes()).hexdigest(),
            'triangles_sha256':sha256(triangles.tobytes()).hexdigest(),'vertex_count':n,'triangle_count':t}
    finally:evaluated.to_mesh_clear()


def geometry(bpy: Any,human: Any,rig: Any,pairs: list[dict]) -> dict:
    result=surface(bpy,human)
    world=[float(v) for row in rig.matrix_world for v in row]
    matrices=[[float(v) for row in rig.matrix_world@rig.pose.bones[pair['target']].matrix for v in row] for pair in pairs]
    result['pose_sha256']=pose_digest(world,matrices)
    modifier=human.modifiers.get(NAME)
    if modifier is None or not modifier.show_viewport:raise ValueError('Body sprites lost the original visible corrective skin')
    try:
        modifier.show_viewport=False
        result['raw_skin_sha256']=surface(bpy,human)['positions_sha256']
    finally:modifier.show_viewport=True;bpy.context.view_layer.update()
    return result


def all_frames(bpy: Any,human: Any,rig: Any,pairs: list[dict],timeline: dict) -> list[dict]:
    validate_clock(bpy.context.scene)
    rows=timeline.get('full_timeline_frames')
    if type(rows) is not list or len(rows)!=300:raise ValueError('Body sprites need every retained native frame')
    actual=[]
    for frame,row in enumerate(rows,1):
        bpy.context.scene.frame_set(frame);measured=geometry(bpy,human,rig,pairs)
        if measured['evaluated_sha256']!=row['evaluated_sha256'] or measured['pose_sha256']!=row['target_pose_sha256']:
            raise ValueError('Body sprite native skin or pose differs on absolute target frame '+str(frame))
        actual.append(measured)
    return actual


def compare_complete(actual: list[dict],expected: list[dict]) -> None:
    if len(actual)!=300 or canonical_bytes(actual)!=canonical_bytes(expected):
        raise ValueError('Saved body sprite scene differs from complete original-source native skin/poses')


def render_frames(bpy: Any,root: Path,scene: Any,request: Any,human: Any,rig: Any,
                  pairs: list[dict],reference: list[dict],*,prefix: str='') -> list[dict]:
    from blender_bridge.sprite_scene import snapshot
    validate_clock(scene)
    if any(layer.material_override is not None for layer in scene.view_layers):raise ValueError('Body sprite scene cannot override its reviewed matte material')
    rows=[];settings=request.settings;first=request.window.target_first_frame
    scene.frame_set(first);scene.camera=bpy.data.objects[PREFIX+'CAMERA_00'];configuration=snapshot(scene)
    action=action_state(bpy,rig)
    for direction,yaw in enumerate(settings.angles()):
        scene.camera=bpy.data.objects[PREFIX+f'CAMERA_{direction:02d}']
        for frame in request.window.target_frames:
            scene.frame_set(frame);bpy.context.view_layer.update()
            measured=geometry(bpy,human,rig,pairs)
            if measured!=reference[frame-1]:raise ValueError('Selected body sprite pose differs from complete native reference')
            normals=sha256(corners(bpy,human)).hexdigest()
            if checked_owned_material(bpy,human)!=request.temporary_matte:raise ValueError('Body-sprite temporary shader changed')
            name=f'body-{direction:02d}-{frame:04d}.png';path=root/(prefix+name)
            if path.exists() or path.is_symlink():raise ValueError('Refuse to replace body-sprite output')
            scene.render.filepath=str(path);bpy.ops.render.render(scene=scene.name,write_still=True)
            observed=snapshot(scene);observed['frame']=first
            if observed!=configuration or action_state(bpy,rig)!=action:raise ValueError('Body rendering changed camera, lighting, settings or Action')
            stats=png_measurements(path.read_bytes(),include_pixel_hash=True,expected_size=(settings.resolution,settings.resolution))
            rows.append({'file':name,'direction_index':direction,'yaw_deg':yaw,'target_frame':frame,'source_frame':frame+1,
                'geometry':measured,'normals_sha256':normals,'sha256':digest(path),**stats})
    scene.frame_set(first);scene.camera=bpy.data.objects[PREFIX+'CAMERA_00'];bpy.context.view_layer.update()
    return rows


def compare_frames(root: Path,actual: list[dict],expected: list[dict]) -> None:
    if type(actual) is not list or type(expected) is not list or len(actual)!=len(expected):raise ValueError('Body sprite selected raster coverage differs')
    for observed,want in zip(actual,expected):
        if (type(observed) is not dict or type(want) is not dict or set(observed)!=set(want)
                or type(observed.get('file')) is not str or re.fullmatch(r'body-[0-9]{2}-[0-9]{4}\.png',observed['file']) is None
                or want.get('file')!=observed['file']):
            raise ValueError('Body sprite frame names or fields differ before raster read')
        path=root/want['file']
        if (not path.is_file() or path.is_symlink() or digest(path)!=want.get('sha256')
                or canonical_bytes({k:v for k,v in observed.items() if k!='sha256'})!=canonical_bytes({k:v for k,v in want.items() if k!='sha256'})):
            raise ValueError('Body sprite original-source/saved-scene geometry, normals or pixels differ')
