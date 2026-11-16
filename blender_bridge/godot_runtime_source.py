"""Exact prepared-master state and native source admission inside Blender."""
from array import array
from hashlib import sha256
from pathlib import Path
from typing import Any
import numpy as np

from blender_bridge.face_geometry import key_state,rest_state,mesh_coordinates
from blender_bridge.face_operations import state_digest
from blender_bridge.face_materials import signature as material_signature
from blender_bridge.native_fit_scene import polygon_digest,exact_weights_digest
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.native_corrective import NAME,SETTINGS
from blender_bridge.native_review_reopen import reopen_native,scene_objects,digest,bound_scene
from blender_bridge.native_inputs import read_json
from blender_bridge.expression_policy import TARGETS,keyname
from ucc.export.godot_native_recipe import validate_native_job,validate_native_recipe,INPUTS
from ucc.export.godot_runtime_data import COUNTS,SMOOTHING
from ucc.export.godot_runtime_contract import PROFILE


def checked_recipe(root: Path,job: dict) -> dict:
    options=job['options'];validate_native_job(job['operation'],job['input_project'],options)
    recipe=validate_native_recipe(read_json(root/'native_recipe.json',options['native_recipe_sha256'],256*1024))
    bindings=recipe['source_bindings'];evidence=recipe['evidence_bindings']
    expected={'master_sha256':bindings['master'],'source_sha256':bindings[recipe['motion_asset_id']],
        'review_sha256':evidence['native_review'],'timeline_sha256':evidence['native_timeline'],
        'snapshot_sha256':evidence['source_snapshot'],'mapping_sha256':evidence['native_mapping']}
    if any(options[k]!=v for k,v in expected.items()):raise ValueError('Native worker sources differ from its closed recipe')
    for name,key in INPUTS.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or digest(path)!=options[key]:raise ValueError('Native worker input changed: '+name)
    for name,sha in recipe['implementation'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=256*1024 or digest(path)!=sha:
            raise ValueError('Private native implementation changed: '+name)
    return recipe


def character_state(bpy: Any,human: Any,rig: Any) -> str:
    mods=tuple(human.modifiers)
    if mods and mods[-1].type=='CORRECTIVE_SMOOTH':mods=mods[:-1]
    uv=sha256()
    for layer in human.data.uv_layers:
        uv.update(layer.name.encode()+b'\0');values=array('f',[0.])*(len(layer.data)*2)
        layer.data.foreach_get('uv',values);uv.update(values.tobytes())
    keys=human.data.shape_keys
    if (keys is None or not keys.use_relative or human.show_only_shape_key
            or any(keys.key_blocks.get(keyname(r,f)) is None or keys.key_blocks[keyname(r,f)].value!=0. for r,f,_ in TARGETS)):
        raise ValueError('Native runtime production requires the actual neutral canonical facial controls')
    state={'coordinates':mesh_coordinates(human),'topology':polygon_digest(human),'weights':exact_weights_digest(human),
        'key_order':[k.name for k in keys.key_blocks],'keys':{k.name:key_state(k) for k in keys.key_blocks},
        'rest':rest_state(rig),'stack':source_stack(human,rig,modifiers=mods),
        'bone_hierarchy':[(b.name,b.parent.name if b.parent else None,b.use_deform,b.inherit_scale,b.use_inherit_rotation,b.use_local_location,b.use_connect) for b in rig.data.bones],
        'uv':uv.hexdigest(),'active_uv':human.data.uv_layers.active_index,
        'polygon_material_smooth':[(p.material_index,p.use_smooth) for p in human.data.polygons],
        'materials':material_signature(bpy),'parent_inverse':[v for row in human.matrix_parent_inverse for v in row],
        'human_local':[v for row in human.matrix_basis for v in row],'rig_scale':list(rig.scale)}
    unrelated={}
    for obj in bpy.data.objects:
        if obj in (human,rig) or obj.name=='UCC_Godot_Private_Character':continue
        row={'type':obj.type,'parent':obj.parent.name if obj.parent else None,
            'world':[float(v) for line in obj.matrix_world for v in line],
            'parent_inverse':[float(v) for line in obj.matrix_parent_inverse for v in line]}
        if obj.type=='MESH':
            row.update(coordinates=mesh_coordinates(obj),topology=polygon_digest(obj),weights=exact_weights_digest(obj),
                keys={k.name:key_state(k) for k in obj.data.shape_keys.key_blocks} if obj.data.shape_keys else {})
        unrelated[obj.name]=row
    state['unrelated_objects']=unrelated
    return state_digest(state)


def admitted_source(bpy: Any,root: Path,job: dict,observer=None) -> tuple:
    options=job['options'];bound_scene(root/'candidate.blend',options['master_sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False)
    human,rig=scene_objects(bpy);master=character_state(bpy,human,rig)
    native_options={key:options[key] for key in INPUTS.values()}
    evidence=reopen_native(bpy,root,native_options,frame_observer=observer)
    human,rig=scene_objects(bpy)
    if character_state(bpy,human,rig)!=master:
        raise ValueError('Native review changed authoritative master shape keys, geometry, weights, UVs, materials or rest state')
    scene=bpy.context.scene
    if (scene.frame_start!=1 or scene.frame_end!=300 or scene.render.fps!=30 or scene.render.fps_base!=1.
            or scene.unit_settings.scale_length!=1. or len(rig.data.bones)!=163
            or any(float(human.matrix_world[i][j])!=float(i==j) for i in range(4) for j in range(4))):
        raise ValueError('Native runtime source differs from the admitted native300 metre/identity profile')
    if evidence['frames_verified']!=300 or evidence['skin_deformation_policy']!='BOUND_CORRECTIVE_SMOOTH_V1':
        raise ValueError('Runtime source requires complete independently reopened bound corrective skin')
    return human,rig,master,evidence


def source_profile(bpy: Any,human: Any,rig: Any,recipe: dict) -> dict:
    mods=tuple(human.modifiers)
    if [m.type for m in mods]!=['ARMATURE','MASK','CORRECTIVE_SMOOTH']:
        raise ValueError('Runtime source has an unsupported modifier stack')
    arm,mask,mod=mods
    if mod.name!=NAME or not mod.is_bind or any(getattr(mod,k)!=v for k,v in SETTINGS.items()):
        raise ValueError('Runtime source lost its bound corrective settings')
    if arm.use_deform_preserve_volume or arm.use_bone_envelopes or arm.use_multi_modifier or not arm.use_vertex_groups:
        raise ValueError('Runtime source requires original linear vertex-group skinning')
    obj=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
    try:
        bones={b.name for b in rig.data.bones};groups={g.index:g.name for g in human.vertex_groups}
        counts={'source_vertices':len(human.data.vertices),'vertices':len(mesh.vertices),'faces':len(mesh.polygons),'corners':len(mesh.loops),
            'bones':len(bones),'max_influences':max(sum(g.weight>0 and groups[g.group] in bones for g in v.groups) for v in human.data.vertices)}
        if (counts!=COUNTS or any(not p.use_smooth for p in mesh.polygons) or any(e.use_edge_sharp for e in mesh.edges)
                or any('normal' in a.name.lower() for a in mesh.attributes)):
            raise ValueError('Runtime source differs from the exact smooth family profile')
    finally:obj.to_mesh_clear()
    return {'schema_version':1,'profile':PROFILE,'counts':counts,
        'source_review_sha256':recipe['evidence_bindings']['native_review'],
        'source_timeline_sha256':recipe['evidence_bindings']['native_timeline'],'master_sha256':recipe['source_bindings']['master'],
        'smoothing':{k:getattr(mod,k) for k in SMOOTHING},'is_bound':True,'linear_skin':True,'static_masks_baked':True,
        'model_world':[float(v) for row in human.matrix_world for v in row],
        'flat_faces':0,'sharp_edges':0,'custom_normals':False,'source_production_verified':False,'engine_import_verified':False}
