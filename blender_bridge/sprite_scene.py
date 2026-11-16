"""Blender-only neutral render scene, separate from the original scene."""
import math
from typing import Any
from mathutils import Vector
from ucc.core.sprite_render import SpriteSettings

SCENE='UCC_SPRITE_SCENE_V1'
PREFIX='UCC_SPRITE_'


def visible_points(bpy: Any,human: Any) -> list:
    evaluated=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    try:
        points=[human.matrix_world@v.co for v in mesh.vertices]
        if not 1<=len(points)<=250000 or any(not math.isfinite(c) for p in points for c in p):raise ValueError('Unsupported sprite surface bounds')
        return points
    finally:evaluated.to_mesh_clear()


def setup(bpy: Any,human: Any,rig: Any,settings: SpriteSettings) -> tuple:
    if any(o.name.startswith(PREFIX) for o in bpy.data.objects) or bpy.data.scenes.get(SCENE) is not None:
        raise ValueError('Reserved sprite staging names already exist')
    points=visible_points(bpy,human);low=Vector([min(p[i] for p in points) for i in range(3)]);high=Vector([max(p[i] for p in points) for i in range(3)])
    center=(low+high)*.5;height=high.z-low.z
    if not .1<=height<=10:raise ValueError('Sprite source needs supported meter-scale geometry')
    original=bpy.context.scene;scene=bpy.data.scenes.new(SCENE)
    scene.collection.objects.link(human);scene.collection.objects.link(rig)
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    world=bpy.data.worlds.new(PREFIX+'WORLD');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(1.,1.,1.,1.)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.15;scene.world=world
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32
    scene.cycles.use_denoising=False;scene.cycles.use_adaptive_sampling=False;scene.cycles.seed=0;scene.cycles.use_animated_seed=False
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.render.resolution_x=scene.render.resolution_y=settings.resolution;scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1.;scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8'
    scene.render.image_settings.compression=15;scene.render.dither_intensity=0.
    scene.render.use_compositing=False;scene.render.use_sequencer=False
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=0.;scene.view_settings.gamma=1.
    scene.view_settings.use_curve_mapping=False
    scene.frame_set(1);cameras=[];maximum=0.
    for i,yaw in enumerate(settings.angles()):
        angle=math.radians(yaw);pitch=math.radians(settings.pitch_deg)
        offset=Vector((math.sin(angle)*math.cos(pitch),-math.cos(angle)*math.cos(pitch),math.sin(pitch)))*height*3
        data=bpy.data.cameras.new(PREFIX+f'CAMERA_{i:02d}');data.type='ORTHO';data.clip_start=.01;data.clip_end=100.
        camera=bpy.data.objects.new(data.name,data);scene.collection.objects.link(camera)
        camera.location=center+offset;camera.rotation_euler=(-offset).to_track_quat('-Z','Y').to_euler()
        bpy.context.window.scene=scene;bpy.context.view_layer.update();inverse=camera.matrix_world.inverted()
        projected=[inverse@p for p in points]
        maximum=max(maximum,max(p.x for p in projected)-min(p.x for p in projected),max(p.y for p in projected)-min(p.y for p in projected))
        cameras.append(camera)
    for camera in cameras:camera.data.ortho_scale=maximum/.8
    for i,offset in enumerate(((2,-3,4),(-3,-1,2),(1,3,3))):
        data=bpy.data.lights.new(PREFIX+f'LIGHT_{i:02d}','AREA');data.energy=300*height*height;data.shape='DISK';data.size=height*2
        light=bpy.data.objects.new(data.name,data);scene.collection.objects.link(light);light.location=center+Vector(offset)*height
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    scene.camera=cameras[0];bpy.context.view_layer.update()
    foot=Vector((center.x,center.y,low.z));camera=cameras[0];projected=camera.matrix_world.inverted()@foot
    pivot=[.5+projected.x/camera.data.ortho_scale,.5-projected.y/camera.data.ortho_scale]
    if any(not 0<=v<=1 for v in pivot):raise ValueError('Sprite origin projected outside the canvas')
    return scene,original,pivot


def snapshot(scene: Any) -> dict:
    render=scene.render;cycles=scene.cycles;view=scene.view_settings;objects={}
    for obj in scene.objects:
        record={'type':obj.type,'world':[float(v) for row in obj.matrix_world for v in row]}
        if obj.type=='CAMERA':record['camera']={k:getattr(obj.data,k) for k in ('type','ortho_scale','clip_start','clip_end')};record['dof']=obj.data.dof.use_dof
        elif obj.type=='LIGHT':record['light']={k:getattr(obj.data,k) for k in ('type','energy','shape','size')};record['color']=list(obj.data.color)
        objects[obj.name]=record
    background=scene.world.node_tree.nodes.get('Background') if scene.world and scene.world.use_nodes else None
    return {'objects':objects,'frame':scene.frame_current,'engine':render.engine,'device':cycles.device,'samples':cycles.samples,
        'denoising':cycles.use_denoising,'adaptive_sampling':cycles.use_adaptive_sampling,'seed':cycles.seed,'animated_seed':cycles.use_animated_seed,
        'threads':[render.threads_mode,render.threads],'resolution':[render.resolution_x,render.resolution_y,render.resolution_percentage],
        'pixel_aspect':[render.pixel_aspect_x,render.pixel_aspect_y],'transparent':render.film_transparent,
        'format':[render.image_settings.file_format,render.image_settings.color_mode,render.image_settings.color_depth,render.image_settings.compression],
        'dither':render.dither_intensity,'compositor':render.use_compositing,'sequencer':render.use_sequencer,
        'view':[view.view_transform,view.look,view.exposure,view.gamma,view.use_curve_mapping],
        'world_nodes':[] if background is None else [list(background.inputs['Color'].default_value),background.inputs['Strength'].default_value],
        'world_node_types':[] if not scene.world or not scene.world.use_nodes else sorted(n.bl_idname for n in scene.world.node_tree.nodes),
        'units':[scene.unit_settings.system,scene.unit_settings.scale_length]}


def cleanup(bpy: Any,scene: Any,original: Any) -> None:
    bpy.context.window.scene=original
    for obj in list(scene.objects):
        if obj.name.startswith(PREFIX):
            data=obj.data;kind=obj.type;bpy.data.objects.remove(obj,do_unlink=True)
            (bpy.data.cameras if kind=='CAMERA' else bpy.data.lights).remove(data)
    world=scene.world;bpy.data.scenes.remove(scene)
    if world and world.users==0:bpy.data.worlds.remove(world)
