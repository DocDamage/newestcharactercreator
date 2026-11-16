"""Saved color-material candidate plus fresh original/saved-source verification."""
from pathlib import Path
import shutil
from typing import Any
import numpy as np

from blender_bridge.face_geometry import intake
from blender_bridge.neutral_master import animation_audit,neutral_pose_and_keys
from blender_bridge.skin_material_model import (material_name,checked_owned_material,nonmaterial_state,apply_material,shader_snapshot)
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest,read_json
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh,discard_godot_bind_mesh
from blender_bridge.godot_outputs import write_json,export_glb
from blender_bridge.godot_surface_uv import surface
from blender_bridge.godot_runtime_weights import original_weights,verify_serialized_weights
from ucc.core.skin_material import validate_material_job,validate_material_recipe,SkinMaterialSpec,RECIPE_POLICY
from ucc.export.skin_material_evidence import verify_material_glb
from ucc.export.godot_surface_uv import verify_glb_uvs
from ucc.export.godot_skin_evidence import _DenseSkin


def checked(root: Path,job: dict) -> tuple[dict,SkinMaterialSpec]:
    options=job['options'];validate_material_job(job['operation'],job['input_project'],options)
    recipe=validate_material_recipe(read_json(root/'material_recipe.json',options['recipe_sha256'],256*1024))
    if recipe['source_bindings']['master']!=options['master_sha256'] or digest(root/'candidate.blend')!=options['master_sha256']:
        raise ValueError('Body material source differs from its saved original')
    return recipe,SkinMaterialSpec.from_dict(recipe['spec'])


def reconstruct(bpy: Any,root: Path,job: dict) -> tuple:
    recipe,spec=checked(root,job);bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False)
    animation_audit(bpy);human,rig,_,targets=intake(bpy)
    if neutral_pose_and_keys(rig,human)!=12:raise ValueError('Material candidate requires complete neutral prepared expressions')
    previous=checked_owned_material(bpy,human)
    allowed={material_name(spec)}|({material_name(previous)} if previous else set())
    before=nonmaterial_state(bpy,human,rig,targets,allowed)
    material=apply_material(bpy,human,spec,previous)
    if checked_owned_material(bpy,human)!=spec:raise ValueError('New body material does not match its explicit parameters')
    after=nonmaterial_state(bpy,human,rig,targets,allowed)
    if after!=before:raise ValueError('Material edit changed geometry, keys, UVs, rig, scene or unrelated materials')
    return recipe,spec,human,rig,targets,allowed,before,material,previous!=spec


def exported_evidence(bpy: Any,root: Path,human: Any,rig: Any,spec: SkinMaterialSpec,*,export: bool) -> dict:
    candidate=build_godot_bind_mesh(bpy,human,rig)
    try:
        converted=candidate.object
        if export:export_glb(bpy,root,converted,rig,include_animation=False,dense_morphs=True)
        glb=root/'character.glb';bind=[(float(v.co.x),float(v.co.z),-float(v.co.y)) for v in converted.data.vertices]
        _,polygons,uvs,_,_=surface(converted.data)
        uv=verify_glb_uvs(glb,bind,polygons,uvs,check=lambda:None)
        weight=verify_serialized_weights(glb,np.asarray(bind,dtype=np.float32),original_weights(human,rig,candidate.source_vertex_ids))
        reader=_DenseSkin(glb);primitive=reader.document['meshes'][0]['primitives'][0]
        rows=reader.rows(primitive['attributes']['POSITION'],'VEC3',(5126,));lookup={tuple(point):i for i,point in enumerate(bind)}
        ids=[lookup[tuple(point)] for point in rows];names=reader.document['meshes'][0]['extras']['targetNames']
        maximum=0.;basis=converted.data.shape_keys.key_blocks['Basis']
        if len(names)!=12 or len(primitive.get('targets',[]))!=12:raise ValueError('Material export lost canonical morphs')
        for name,target in zip(names,primitive['targets']):
            key=converted.data.shape_keys.key_blocks.get(name)
            if key is None:raise ValueError('Material export changed expression identity')
            values=reader.rows(target['POSITION'],'VEC3',(5126,))
            if len(values)!=len(ids):raise ValueError('Material export morph is incomplete')
            for index,delta in zip(ids,values):
                expected=key.data[index].co-basis.data[index].co;point=(float(expected.x),float(expected.z),-float(expected.y))
                error=sum((a-b)**2 for a,b in zip(delta,point))**.5;maximum=max(maximum,error)
        if maximum>1e-6:raise ValueError('Material export changed canonical morph positions')
        return {'pbr':verify_material_glb(glb,spec),'uv':uv,'maximum_relative_weight_error':weight,'maximum_morph_delta_error_m':maximum}
    finally:discard_godot_bind_mesh(bpy,candidate)


def stage_material(bpy: Any,root: Path,job: dict) -> dict:
    for name in ('material_human.blend','character.glb','material_stage.json'):
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Material worker refuses existing outputs')
    recipe,spec,human,rig,targets,allowed,before,material,changed=reconstruct(bpy,root,job)
    shader=state_digest(shader_snapshot(material));count=len(human.data.shape_keys.key_blocks)
    glb=exported_evidence(bpy,root,human,rig,spec,export=True)
    if nonmaterial_state(bpy,human,rig,targets,allowed)!=before:raise ValueError('Material export changed the editable source')
    if changed:bpy.ops.wm.save_as_mainfile(filepath=str(root/'material_human.blend'),compress=False)
    else:shutil.copy2(root/'candidate.blend',root/'material_human.blend')
    checked(root,job)
    report={'schema_version':1,'policy':RECIPE_POLICY,'recipe_sha256':job['options']['recipe_sha256'],
        'source_master_sha256':job['options']['master_sha256'],'material_master_sha256':digest(root/'material_human.blend'),
        'glb_sha256':digest(root/'character.glb'),'spec_sha256':spec.sha256,'nonmaterial_state_sha256':before,
        'shader_sha256':shader,'shape_key_count':count,'full_vertices':19158,'visible_vertices':13380,'bones':163,
        'changed':changed,'blender_version':bpy.app.version_string,'export':glb,'project_pointer_changed':False,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    write_json(root/'material_stage.json',report)
    return {'policy':RECIPE_POLICY,'stage_report_sha256':digest(root/'material_stage.json'),
        'material_master_sha256':report['material_master_sha256'],'glb_sha256':report['glb_sha256'],'engine_import_verified':False}


def verify_material(bpy: Any,root: Path,job: dict) -> dict:
    options=job['options'];recipe,spec,human,rig,targets,allowed,before,material,changed=reconstruct(bpy,root,job)
    stage=read_json(root/'material_stage.json',options['stage_report_sha256'],4*1024*1024)
    if (digest(root/'material_human.blend')!=options['material_master_sha256'] or digest(root/'character.glb')!=options['glb_sha256']
            or stage.get('source_master_sha256')!=options['master_sha256'] or stage.get('recipe_sha256')!=options['recipe_sha256']
            or stage.get('material_master_sha256')!=options['material_master_sha256'] or stage.get('glb_sha256')!=options['glb_sha256']
            or stage.get('spec_sha256')!=spec.sha256 or stage.get('nonmaterial_state_sha256')!=before or stage.get('changed') is not changed
            or stage.get('shader_sha256')!=state_digest(shader_snapshot(material))):raise ValueError('Material stage differs from independent original reconstruction')
    expected_export=exported_evidence(bpy,root,human,rig,spec,export=False)
    if stage.get('export')!=expected_export:raise ValueError('Material GLB evidence differs from fresh original reconstruction')
    bpy.ops.wm.open_mainfile(filepath=str(root/'material_human.blend'),load_ui=False)
    animation_audit(bpy);human,rig,_,targets=intake(bpy)
    if neutral_pose_and_keys(rig,human)!=12 or checked_owned_material(bpy,human)!=spec:
        raise ValueError('Saved material master changed neutral canonical controls or material parameters')
    if (nonmaterial_state(bpy,human,rig,targets,allowed)!=before
            or state_digest(shader_snapshot(human.data.materials[0]))!=stage['shader_sha256']
            or len(human.data.shape_keys.key_blocks)!=stage['shape_key_count']):
        raise ValueError('Saved material master changed original nonmaterial state or shader definition')
    checked(root,job)
    for name,key in [('material_human.blend','material_master_sha256'),('character.glb','glb_sha256')]:
        if digest(root/name)!=options[key]:raise ValueError('Fresh material verification changed output bytes')
    report={'schema_version':1,'policy':RECIPE_POLICY,'stage_report_sha256':options['stage_report_sha256'],
        'recipe_sha256':options['recipe_sha256'],'source_master_sha256':options['master_sha256'],
        'material_master_sha256':options['material_master_sha256'],'glb_sha256':options['glb_sha256'],'spec_sha256':spec.sha256,
        'nonmaterial_state_sha256':before,'shader_sha256':stage['shader_sha256'],'export':expected_export,
        'verified_reopen':True,'saved_output_rebuilt_or_repaired':False,'project_pointer_changed':False,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    write_json(root/'material_verification.json',report)
    return {'policy':RECIPE_POLICY,'verification_sha256':digest(root/'material_verification.json'),
        'material_master_sha256':options['material_master_sha256'],'glb_sha256':options['glb_sha256'],'engine_import_verified':False}
