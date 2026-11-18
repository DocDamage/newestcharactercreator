"""Fixed-world selected-window framing and strictly temporary matte material."""
from typing import Any
import math

from blender_bridge.skin_material_model import create_material,checked_owned_material,material_name
from blender_bridge.face_geometry import key_state,rest_state,mesh_coordinates
from blender_bridge.face_materials import signature
from blender_bridge.face_operations import state_digest
from blender_bridge.native_fit_scene import polygon_digest,exact_weights_digest,bone_controls
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.native_corrective import NAME,SETTINGS
from array import array
from hashlib import sha256

# The existing sprite helper is imported only inside Blender. Its module uses
# mathutils; framing/contract unit checks remain usable without that runtime.
PREFIX='UCC_SPRITE_'


def _properties(owner: Any) -> dict:
    remaining=[100000]
    def plain(value,depth=0):
        remaining[0]-=1
        if depth>32 or remaining[0]<0:raise ValueError('Body character metadata exceeds its preservation bound')
        if value is None or type(value) in (str,int,bool):return value
        if type(value) is float:
            if not math.isfinite(value):raise ValueError('Nonfinite character metadata')
            return value
        if hasattr(value,'to_dict'):value=value.to_dict()
        elif hasattr(value,'to_list'):value=value.to_list()
        if type(value) is dict:return {key:plain(item,depth+1) for key,item in value.items()}
        if type(value) in (list,tuple):return [plain(item,depth+1) for item in value]
        raise ValueError('Unsupported body character metadata property')
    return {key:plain(value) for key,value in owner.items()}


def _animation_environment(bpy: Any,rig: Any) -> None:
    if any(len(obj.constraints) for obj in bpy.data.objects) or any(len(bone.constraints) for bone in rig.pose.bones):
        raise ValueError('Body sprite source has unsupported constraints, including muted constraints')
    blocks=[]
    for prop in bpy.data.bl_rna.properties:
        if prop.type=='COLLECTION':blocks.extend(block for block in getattr(bpy.data,prop.identifier) if isinstance(block,bpy.types.ID))
    blocks.extend(block.node_tree for block in list(blocks) if getattr(block,'node_tree',None) is not None)
    for block in {block.as_pointer():block for block in blocks}.values():
        if block.library or block.override_library:raise ValueError('Body sprites reject linked or overridden loaded data')
        animation=getattr(block,'animation_data',None)
        if animation and (len(animation.drivers) or len(animation.nla_tracks) or (animation.action is not None and block!=rig)):
            raise ValueError('Body sprites permit only the original rig Action; no other animation/driver/NLA')


def union_bounds(samples: list[tuple]) -> tuple:
    if not samples or len(samples)>32:raise ValueError('Body framing requires the complete bounded selected window')
    if any(len(row)!=2 or len(row[0])!=3 or len(row[1])!=3 for row in samples):raise ValueError('Incomplete body framing bounds')
    low=tuple(min(row[0][i] for row in samples) for i in range(3))
    high=tuple(max(row[1][i] for row in samples) for i in range(3))
    if any(not math.isfinite(v) or abs(v)>10000 for v in (*low,*high)) or any(a>=b for a,b in zip(low,high)):
        raise ValueError('Degenerate/nonfinite body motion framing')
    return low,high


def source_state(bpy: Any,human: Any,rig: Any,targets: Any,request: Any,*,temporary: bool=False) -> str:
    """Exact source intent/rest/weights/keys, excluding only admitted render helpers."""
    _animation_environment(bpy,rig)
    modifiers=tuple(human.modifiers)
    if (not modifiers or modifiers[-1].name!=NAME or not modifiers[-1].is_bind
            or not modifiers[-1].show_viewport or not modifiers[-1].show_render
            or any(getattr(modifiers[-1],key)!=value for key,value in SETTINGS.items())):
        raise ValueError('Body sprite source lost canonical corrective skin settings')
    uv=sha256()
    for layer in human.data.uv_layers:
        uv.update(layer.name.encode()+b'\0');values=array('f',[0.])*(len(layer.data)*2)
        layer.data.foreach_get('uv',values);uv.update(values.tobytes())
    state={'topology':polygon_digest(human),'weights':exact_weights_digest(human),
        'bone_controls':bone_controls(rig),'stack':source_stack(human,rig,modifiers=modifiers[:-1]),
        'macro':targets.get_macro_info_dict_from_basemesh(human),'uv_sha256':uv.hexdigest(),
        'active_uv_index':human.data.uv_layers.active_index,
        'source_properties':{label:_properties(owner) for label,owner in (('human',human),('mesh',human.data),('rig',rig),('rig_data',rig.data),('keys',human.data.shape_keys))},
        'polygon_material_smooth':[(p.material_index,p.use_smooth) for p in human.data.polygons],
        'pose_channels':{bone.name:{'mode':bone.rotation_mode,'basis':[float(v) for row in bone.matrix_basis for v in row],
            'location':list(bone.location),'scale':list(bone.scale),'quaternion':list(bone.rotation_quaternion)} for bone in rig.pose.bones},
        'objects':{obj.name:{'type':obj.type,'parent':obj.parent.name if obj.parent else None,
            'world':[float(v) for row in obj.matrix_world for v in row],
            'parent_inverse':[float(v) for row in obj.matrix_parent_inverse for v in row]} for obj in bpy.data.objects},
        'unrelated_meshes':{obj.name:{'coordinates':mesh_coordinates(obj),'topology':polygon_digest(obj),'weights':exact_weights_digest(obj),
            'keys':{key.name:key_state(key) for key in obj.data.shape_keys.key_blocks} if obj.data.shape_keys else {}}
            for obj in bpy.data.objects if obj.type=='MESH' and obj!=human}}
    materials=signature(bpy)
    if temporary:
        if checked_owned_material(bpy,human)!=request.temporary_matte:raise ValueError('Unexpected body render material')
        name=material_name(request.temporary_matte)
        materials['materials']={key:value for key,value in materials['materials'].items() if key!=name}
    elif checked_owned_material(bpy,human) is not None:raise ValueError('Original body source must have no assigned material')
    helpers={PREFIX+f'CAMERA_{i:02d}' for i in range(request.settings.directions)}|{PREFIX+f'LIGHT_{i:02d}' for i in range(3)} if temporary else set()
    state['objects']={key:value for key,value in state['objects'].items() if key not in helpers}
    state.update(coordinates=mesh_coordinates(human),rest=rest_state(rig),
        all_keys={key.name:key_state(key) for key in human.data.shape_keys.key_blocks},
        all_key_order=[key.name for key in human.data.shape_keys.key_blocks],
        active_key=human.active_shape_key_index,unrelated_materials_images=materials,
        object_flags={obj.name:{'hide_render':obj.hide_render,'hide_viewport':obj.hide_viewport,'hide':obj.hide_get(),
            'data':obj.data.name if obj.data else None,'materials':[] if obj==human else [slot.material.name if slot.material else None for slot in obj.material_slots]}
            for obj in bpy.data.objects if obj.name not in helpers})
    return state_digest(state)


def setup(bpy: Any,human: Any,rig: Any,request: Any) -> tuple:
    from mathutils import Vector
    from blender_bridge.sprite_scene import setup as neutral_setup,visible_points
    if checked_owned_material(bpy,human) is not None:raise ValueError('Body sprites require zero source Human material slots')
    source_scene=bpy.context.scene;samples=[]
    for frame in request.window.target_frames:
        source_scene.frame_set(frame);points=visible_points(bpy,human)
        samples.append((tuple(min(p[i] for p in points) for i in range(3)),tuple(max(p[i] for p in points) for i in range(3))))
    low,high=union_bounds(samples);low,high=Vector(low),Vector(high);center=(low+high)*.5;height=high.z-low.z
    if not .1<=height<=10:raise ValueError('Body sample world motion exceeds supported camera bounds')
    source_scene.frame_set(request.window.target_first_frame)
    scene,original,_=neutral_setup(bpy,human,rig,request.settings)
    scene.frame_start=1;scene.frame_end=300;scene.render.fps=30;scene.render.fps_base=1.;scene.use_preview_range=False
    corners=[Vector((x,y,z)) for x in (low.x,high.x) for y in (low.y,high.y) for z in (low.z,high.z)]
    maximum=0.;cameras=[]
    for index,yaw in enumerate(request.settings.angles()):
        angle=math.radians(yaw);pitch=math.radians(request.settings.pitch_deg)
        offset=Vector((math.sin(angle)*math.cos(pitch),-math.cos(angle)*math.cos(pitch),math.sin(pitch)))*height*3
        camera=bpy.data.objects[PREFIX+f'CAMERA_{index:02d}'];camera.location=center+offset
        camera.rotation_euler=(-offset).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
        projected=[camera.matrix_world.inverted()@p for p in corners]
        maximum=max(maximum,max(p.x for p in projected)-min(p.x for p in projected),max(p.y for p in projected)-min(p.y for p in projected));cameras.append(camera)
    for camera in cameras:camera.data.ortho_scale=maximum/.8
    for index,offset in enumerate(((2,-3,4),(-3,-1,2),(1,3,3))):
        lamp=bpy.data.objects[PREFIX+f'LIGHT_{index:02d}'];lamp.location=center+Vector(offset)*height
        lamp.rotation_euler=(center-lamp.location).to_track_quat('-Z','Y').to_euler();lamp.data.energy=300*height*height;lamp.data.size=height*2
    scene.camera=cameras[0];scene.frame_set(request.window.target_first_frame);bpy.context.view_layer.update()
    foot=Vector((center.x,center.y,low.z));point=cameras[0].matrix_world.inverted()@foot
    pivot=[.5+point.x/cameras[0].data.ortho_scale,.5-point.y/cameras[0].data.ortho_scale]
    if any(not 0<=v<=1 for v in pivot):raise ValueError('Body-sprite pivot projects outside its fixed canvas')
    material=create_material(bpy,request.temporary_matte);human.data.materials.append(material)
    if checked_owned_material(bpy,human)!=request.temporary_matte:raise ValueError('Body sprite matte construction differs')
    return scene,original,pivot


def restore(bpy: Any,scene: Any,original: Any,human: Any,request: Any) -> None:
    from blender_bridge.sprite_scene import cleanup
    if checked_owned_material(bpy,human)!=request.temporary_matte:raise ValueError('Body sprite temporary material changed before cleanup')
    material=human.data.materials[0]
    if material.name!=material_name(request.temporary_matte):raise ValueError('Body sprite temporary material identity changed')
    human.data.materials.clear();bpy.data.materials.remove(material)
    cleanup(bpy,scene,original);original.frame_set(request.window.target_first_frame);bpy.context.view_layer.update()
    if checked_owned_material(bpy,human) is not None:raise ValueError('Body sprite cleanup adopted a material')
