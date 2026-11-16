"""Versioned original-source runtime stage and independent fresh recomputation."""
from pathlib import Path
from hashlib import sha256
from blender_bridge.face_geometry import intake
from blender_bridge.neutral_master import animation_audit,neutral_pose_and_keys
from blender_bridge.face_policy import digest,read_json
from blender_bridge.skin_material_model import checked_owned_material,nonmaterial_state,material_name,shader_snapshot
from blender_bridge.face_operations import state_digest
from blender_bridge.unity_source_reference import reference
from blender_bridge.unity_source_workers import unchanged
from blender_bridge.unity_runtime_samples import samples
from blender_bridge.godot_outputs import write_json
from ucc.export.unity_runtime_source import POLICY,FILES,CASES,VERTICES,BINARY_BYTES,validate_job,validate_recipe
from ucc.export.godot_candidate_contract import canonical_bytes


def context(bpy,root: Path,job: dict):
    options=job['options'];validate_job(job['operation'],job['input_project'],options)
    request,spec,parameters=validate_recipe(read_json(root/'unity_runtime_recipe.json',options['recipe_sha256'],256*1024))
    if (dict(request.source_bindings)['master']!=options['master_sha256'] or digest(root/'candidate.blend')!=options['master_sha256']
            or bpy.app.version_string!='5.3.0' or bpy.app.build_hash.decode()!='02f0899d78e3'):
        raise ValueError('Runtime source requires its exact reviewed master and admitted Blender build')
    raw_recipe=read_json(root/'unity_runtime_recipe.json',options['recipe_sha256'],256*1024)
    if raw_recipe['bind_reference_sha256']!=options['bind_reference_sha256']:raise ValueError('Runtime source bind-reference recipe changed')
    bind=read_json(root/'source_reference.json',options['bind_reference_sha256'],64*1024*1024)
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False);animation_audit(bpy)
    human,rig,_,targets=intake(bpy)
    if neutral_pose_and_keys(rig,human)!=12 or checked_owned_material(bpy,human)!=spec:raise ValueError('Runtime source requires the original neutral rig/controls/material')
    state=nonmaterial_state(bpy,human,rig,targets,{material_name(spec)});shader=state_digest(shader_snapshot(human.data.materials[0]))
    actual,_=reference(bpy,human,rig,master_sha=options['master_sha256'],request_sha=request.sha256,spec=spec)
    if canonical_bytes(bind)!=canonical_bytes(actual):raise ValueError('Runtime bind reference differs from the actual original master')
    return request,spec,parameters,bind,human,rig,targets,state,shader


def manifest(bpy,job,request,parameters,rows,binary_sha,state,shader):
    return {'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'master_sha256':job['options']['master_sha256'],
        'recipe_sha256':job['options']['recipe_sha256'],'bind_reference_sha256':job['options']['bind_reference_sha256'],
        'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),'expression_parameters':parameters,
        'coordinate_space':'BLENDER_WORLD_METRES_Z_UP','vector_format':'FLOAT32_LE_XYZ','source_vertices':VERTICES,'case_count':CASES,
        'cases':rows,'binary_sha256':binary_sha,'binary_bytes':BINARY_BYTES,'nonmaterial_state_sha256':state,'shader_sha256':shader,
        'original_state_preserved':True,'animation_clips_created':False,'runtime_verified':False,'visual_quality_approved':False}


def stage(bpy,root: Path,job: dict) -> dict:
    for name in FILES:
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Runtime source refuses existing outputs')
    request,spec,parameters,bind,human,rig,targets,state,shader=context(bpy,root,job);rows=[]
    with (root/'unity_runtime_source.bin').open('xb') as stream:
        for row,positions,normals in samples(bpy,human,rig,targets,parameters,bind):
            rows.append(row);stream.write(positions);stream.write(normals)
    unchanged(bpy,root,job,spec,human,rig,targets,state,shader)
    binary=root/'unity_runtime_source.bin'
    if len(rows)!=CASES or binary.stat().st_size!=BINARY_BYTES:raise ValueError('Runtime source binary coverage differs')
    write_json(root/'unity_runtime_source.json',manifest(bpy,job,request,parameters,rows,digest(binary),state,shader))
    return {'policy':POLICY,'request_sha256':request.sha256,'files':{n:digest(root/n) for n in FILES},'runtime_verified':False}


def verify(bpy,root: Path,job: dict) -> dict:
    path=root/'unity_runtime_verification.json'
    if path.exists() or path.is_symlink():raise ValueError('Runtime verification refuses existing output')
    request,spec,parameters,bind,human,rig,targets,state,shader=context(bpy,root,job);options=job['options'];hashes={}
    for name,maximum in FILES.items():
        value=root/name;expected=options[name.replace('.','_')+'_sha256']
        if value.is_symlink() or not value.is_file() or not 0<value.stat().st_size<=maximum or digest(value)!=expected:
            raise ValueError('Runtime source output changed: '+name)
        hashes[name]=expected
    rows=[];binary=root/'unity_runtime_source.bin'
    with binary.open('rb') as stream:
        for row,positions,normals in samples(bpy,human,rig,targets,parameters,bind):
            if stream.read(len(positions))!=positions or stream.read(len(normals))!=normals:
                raise ValueError('Runtime source vectors differ from fresh original-master deformation')
            rows.append(row)
        if stream.read(1):raise ValueError('Runtime source binary has trailing bytes')
    expected=manifest(bpy,job,request,parameters,rows,hashes['unity_runtime_source.bin'],state,shader)
    actual=read_json(root/'unity_runtime_source.json',hashes['unity_runtime_source.json'],FILES['unity_runtime_source.json'])
    if canonical_bytes(expected)!=canonical_bytes(actual):raise ValueError('Runtime source manifest differs from fresh source recomputation')
    unchanged(bpy,root,job,spec,human,rig,targets,state,shader)
    if any(digest(root/name)!=value for name,value in hashes.items()):raise ValueError('Fresh runtime verification changed source outputs')
    report={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'master_sha256':options['master_sha256'],
        'recipe_sha256':options['recipe_sha256'],'bind_reference_sha256':options['bind_reference_sha256'],'files':hashes,
        'case_count':CASES,'source_recomputed_without_rewriting_outputs':True,'original_state_preserved':True,'runtime_verified':False}
    write_json(path,report)
    return {'policy':POLICY,'request_sha256':request.sha256,'files':hashes,'verification_sha256':digest(path),'runtime_verified':False}
