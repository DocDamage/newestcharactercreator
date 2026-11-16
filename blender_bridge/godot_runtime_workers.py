"""Stage and independently reopen actual native runtime inputs; never repairs a saved result."""
from pathlib import Path
from typing import Any
import math
import numpy as np

from blender_bridge.godot_runtime_source import (checked_recipe,admitted_source,character_state,
    source_profile,require_registered_material_state)
from blender_bridge.godot_runtime_geometry import sampled_mesh,capture_binding,write_binding,reconstruct
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh
from blender_bridge.godot_outputs import export_glb,write_json
from blender_bridge.godot_source import pose_values
from blender_bridge.godot_runtime_morphs import verify_morphs
from blender_bridge.godot_runtime_weights import original_weights,apply_weights,source_ids,verify_original_weights,verify_serialized_weights
from blender_bridge.godot_surface_uv import verify_source_surface_uv
from blender_bridge.native_corrective import NAME
from blender_bridge.native_review_reopen import digest,bound_scene
from blender_bridge.native_inputs import read_json
from ucc.export.godot_native_recipe import POLICY,REFERENCES
from ucc.export.godot_runtime_contract import FILES,CODE_FILES
from ucc.export.godot_skin_plan import build_skin_plan

OUTPUT_FILES=FILES | (REFERENCES-{'native_stage.json'})


def _raw(bpy: Any,human: Any) -> np.ndarray:
    modifier=human.modifiers[NAME];visible=modifier.show_viewport
    try:modifier.show_viewport=False;return sampled_mesh(bpy,human)[0]
    finally:modifier.show_viewport=visible;bpy.context.view_layer.update()


def _error(actual: np.ndarray,expected: np.ndarray,label: str) -> float:
    if actual.shape!=expected.shape or not np.isfinite(actual).all():raise ValueError('Incomplete/nonfinite '+label)
    value=float(np.max(np.linalg.norm(actual.astype(np.float64)-expected.astype(np.float64),axis=1)))
    if not math.isfinite(value) or value>1e-6:raise ValueError(label+' exceeds fixed 1um source limit: '+str(value))
    return value


def _write(root: Path,name: str,values: np.ndarray) -> None:
    with (root/name).open('xb') as stream:values.astype('<f4').tofile(stream)


def _loaded_binding(root: Path) -> dict:
    rows=np.fromfile(root/'corners.u32',dtype='<u4').reshape(-1,4)
    ranges=np.fromfile(root/'neighbor_ranges.u32',dtype='<u4').reshape(-1,2)
    neighbors=np.fromfile(root/'neighbors.u32',dtype='<u4')
    # Recover original ordered edges from the stage topology's incidence order
    # only for validation of structure; reconstruction uses stored rest edge IDs.
    edges=np.fromfile(root/'runtime_edges.u32',dtype='<u4').reshape(-1,2)
    if len(rows)!=53512 or len(ranges)!=13380 or len(neighbors)!=53512 or edges.shape!=(26756,2):
        raise ValueError('Incomplete saved runtime binding topology')
    offsets=np.fromfile(root/'offsets_vec4.f32',dtype='<f4').reshape(-1,4)
    if offsets.shape!=(53512,4) or not np.isfinite(offsets).all():raise ValueError('Invalid saved runtime offsets')
    return {'edges':edges,'previous':rows[:,0],'current':rows[:,1],'following':rows[:,2],'offsets':offsets[:,:3]}


def stage_native_runtime(bpy: Any,root: Path,job: dict) -> dict:
    recipe=checked_recipe(root,job)
    policy=recipe['policy']
    for name in (OUTPUT_FILES-CODE_FILES)|{'native_stage.json','runtime_edges.u32'}:
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Refuse to overwrite native runtime output: '+name)
    positions=[];normals=[];bones=[]
    def observe(api,human,rig,frame,skin_sha):
        p,n=sampled_mesh(api,human);positions.append(p);normals.append(n)
        bones.append(np.asarray(pose_values(rig,human,[b.name for b in rig.data.bones]),dtype=np.float32))
    human,rig,master,native=admitted_source(bpy,root,job,observe)
    if len(positions)!=300:raise ValueError('Native source did not expose every source frame')
    binding=capture_binding(bpy,human,rig,human.modifiers[NAME]);write_binding(root,binding)
    with (root/'runtime_edges.u32').open('xb') as stream:binding['edges'].astype('<u4').tofile(stream)
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update();profile=source_profile(bpy,human,rig,recipe)
    donor=human.copy();donor.data=human.data.copy();bpy.context.scene.collection.objects.link(donor)
    donor.modifiers.remove(donor.modifiers[NAME])
    candidate=build_godot_bind_mesh(bpy,donor,rig);converted=candidate.object
    require_registered_material_state(bpy,converted,recipe)
    data=donor.data;bpy.data.objects.remove(donor,do_unlink=True);bpy.data.meshes.remove(data)
    weights=original_weights(human,rig,candidate.source_vertex_ids)
    apply_weights(converted,weights,serialized=False)
    with (root/'source_vertex_ids.u32').open('xb') as stream:np.asarray(candidate.source_vertex_ids,dtype='<u4').tofile(stream)
    morphs=verify_morphs(bpy,human,rig,converted)
    bind=np.asarray([(v.co.x,v.co.z,-v.co.y) for v in converted.data.vertices],dtype=np.float32)
    _write(root,'bind_positions.bin',bind)
    from struct import pack
    indices={pack('<3f',*(0. if v==0 else v for v in row)).hex():i for i,row in enumerate(bind)}
    if len(indices)!=13380:raise ValueError('Native bind correspondence is ambiguous')
    write_json(root/'bind_source_indices.json',indices);write_json(root/'source_profile.json',profile)
    rows=[]
    for frame in range(1,301):
        bpy.context.scene.frame_set(frame);raw=sampled_mesh(bpy,converted)[0]
        reference=_raw(bpy,human)
        raw_error=_error(raw,reference,'Native converted raw skin')
        result=reconstruct(raw,**{k:binding[k] for k in ('edges','previous','current','following','offsets')})
        error=_error(result,positions[frame-1],'Native reconstructed skin')
        rows.append({'frame':frame,'raw_error_m':raw_error,'reconstruction_error_m':error})
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    if character_state(bpy,human,rig)!=master:raise ValueError('Runtime staging changed source character state')
    _write(root,'native_positions.bin',np.asarray(positions));_write(root,'native_normals.bin',np.asarray(normals));_write(root,'native_bones.bin',np.asarray(bones))
    serialized=converted.copy();serialized.data=converted.data.copy();serialized.name='UCC_Godot_Private_Export_Copy'
    bpy.context.scene.collection.objects.link(serialized)
    try:
        apply_weights(serialized,weights,serialized=True)
        exported=export_glb(bpy,root,serialized,rig,optimize_animation=False)
    finally:
        data=serialized.data;bpy.data.objects.remove(serialized,do_unlink=True);bpy.data.meshes.remove(data)
    weight_error=verify_serialized_weights(root/'character.glb',bind,weights)
    print('NATIVE_SOURCE_UV_VERIFIED',verify_source_surface_uv(bpy,human,rig,converted,root/'character.glb'),flush=True)
    write_json(root/'skin_plan.json',build_skin_plan(root/'character.glb').to_dict())
    bpy.context.scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(root/'runtime_source.blend'),compress=False)
    checked_recipe(root,job)
    files={name:{'sha256':digest(root/name),'bytes':(root/name).stat().st_size} for name in sorted(OUTPUT_FILES|{'runtime_edges.u32'})}
    report={'schema_version':1,'policy':policy,'status':'REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED',
        'recipe_sha256':job['options']['native_recipe_sha256'],'master_state_sha256':master,
        'native_reopen':native,'source_names':{'human':human.name,'rig':rig.name,'converted':converted.name},
        'frames':rows,'fps':30,'frame_count':300,'morphs':morphs,'blender_version':bpy.app.version_string,
        'numpy_version':np.__version__,'files':files,'export_optimize_animation_size':False,
        'raw_copy_weight_policy':'EXACT_ORIGINAL_SOURCE_WEIGHTS_V1','max_serialized_weight_error':weight_error,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    write_json(root/'native_stage.json',report)
    return {'policy':policy,'status':report['status'],'native_stage_sha256':digest(root/'native_stage.json'),
            'frame_count':300,'engine_import_verified':False}


def verify_native_runtime(bpy: Any,root: Path,job: dict,*,save_report: bool=True) -> dict:
    recipe=checked_recipe(root,job);options=job['options'];policy=recipe['policy']
    stage=read_json(root/'native_stage.json',options['native_stage_sha256'],4*1024*1024)
    if stage.get('policy')!=policy or stage.get('recipe_sha256')!=options['native_recipe_sha256']:
        raise ValueError('Native saved producer report differs from the source recipe')
    for name,record in stage['files'].items():
        if name not in OUTPUT_FILES|{'runtime_edges.u32'} or (root/name).is_symlink() or (root/name).stat().st_size!=record['bytes'] or digest(root/name)!=record['sha256']:
            raise ValueError('Native saved producer output changed: '+name)
    if set(stage['files'])!=OUTPUT_FILES|{'runtime_edges.u32'}:raise ValueError('Native saved output closure is incomplete')
    human,rig,master,native=admitted_source(bpy,root,job)
    if master!=stage['master_state_sha256']:raise ValueError('Fresh authoritative master differs from staging')
    source_action=rig.animation_data.action.name;source_objects=set(bpy.data.objects.keys())
    bound_scene(root/'runtime_source.blend',stage['files']['runtime_source.blend']['sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'runtime_source.blend'),load_ui=False)
    names=stage['source_names'];human=bpy.data.objects[names['human']];rig=bpy.data.objects[names['rig']];converted=bpy.data.objects[names['converted']]
    require_registered_material_state(bpy,human,recipe)
    require_registered_material_state(bpy,converted,recipe)
    if set(bpy.data.objects.keys())!=source_objects|{names['converted']}:
        raise ValueError('Saved native runtime scene has unexpected character objects')
    if character_state(bpy,human,rig)!=master or rig.animation_data.action.name!=source_action:
        raise ValueError('Saved runtime scene changed the master or native Action')
    if (len(converted.data.shape_keys.key_blocks)!=13 or any(k.value!=0. for k in converted.data.shape_keys.key_blocks)
            or converted.data.shape_keys.animation_data or [m.type for m in converted.modifiers]!=['ARMATURE']
            or converted.modifiers[0].object!=rig or converted.modifiers[0].use_deform_preserve_volume):
        raise ValueError('Saved raw runtime mesh changed skin or canonical neutral state')
    morphs=verify_morphs(bpy,human,rig,converted)
    ids=source_ids(bpy,human,rig)
    if tuple(np.fromfile(root/'source_vertex_ids.u32',dtype='<u4'))!=ids:raise ValueError('Saved source IDs changed')
    weights=original_weights(human,rig,ids);verify_original_weights(converted,rig,weights)
    bind=np.fromfile(root/'bind_positions.bin',dtype='<f4').reshape(13380,3)
    weight_error=verify_serialized_weights(root/'character.glb',bind,weights)
    print('NATIVE_SOURCE_UV_VERIFIED',verify_source_surface_uv(bpy,human,rig,converted,root/'character.glb'),flush=True)
    expected=np.fromfile(root/'native_positions.bin',dtype='<f4').reshape(300,13380,3)
    normals=np.fromfile(root/'native_normals.bin',dtype='<f4').reshape(300,13380,3)
    bone_reference=np.fromfile(root/'native_bones.bin',dtype='<f4').reshape(300,163*16)
    binding=_loaded_binding(root);rows=[]
    for frame in range(1,301):
        bpy.context.scene.frame_set(frame);p,n=sampled_mesh(bpy,human);raw=sampled_mesh(bpy,converted)[0]
        source_error=_error(p,expected[frame-1],'Fresh native corrected source')
        normal_error=_error(n,normals[frame-1],'Fresh native normal reference')
        raw_error=_error(raw,_raw(bpy,human),'Fresh saved raw skin')
        reconstructed=reconstruct(raw,**binding);error=_error(reconstructed,p,'Fresh saved runtime reconstruction')
        values=np.asarray(pose_values(rig,human,[b.name for b in rig.data.bones]),dtype=np.float64)
        bone_error=float(np.max(np.abs(values-bone_reference[frame-1])))
        if not math.isfinite(bone_error) or bone_error>1e-6:raise ValueError('Fresh saved family bone transforms changed')
        rows.append({'frame':frame,'source_error_m':source_error,'normal_vector_error':normal_error,'raw_error_m':raw_error,
            'reconstruction_error_m':error,'bone_world_error':bone_error})
    checked_recipe(root,job)
    for name,record in stage['files'].items():
        if digest(root/name)!=record['sha256']:raise ValueError('Fresh reopening changed staged output bytes')
    report={'schema_version':1,'policy':policy,'status':'FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED',
        'native_stage_sha256':options['native_stage_sha256'],'recipe_sha256':options['native_recipe_sha256'],
        'master_state_sha256':master,'native_reopen':native,'frames':rows,'frame_count':300,'morphs':morphs,
        'raw_copy_weight_policy':'EXACT_ORIGINAL_SOURCE_WEIGHTS_V1','max_serialized_weight_error':weight_error,
        'blender_version':bpy.app.version_string,'engine_import_verified':False,'visual_quality_approved':False,
        'distribution_license_review_complete':False,'saved_output_rebuilt_or_repaired':False}
    if not save_report:return report
    write_json(root/'native_verification.json',report)
    return {'policy':policy,'status':report['status'],'native_verification_sha256':digest(root/'native_verification.json'),
        'frame_count':300,'engine_import_verified':False}
