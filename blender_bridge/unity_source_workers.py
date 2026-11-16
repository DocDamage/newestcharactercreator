"""Fresh source-reference staging/reopening; Unity must verify FBX semantics."""
from pathlib import Path
from blender_bridge.face_geometry import intake
from blender_bridge.neutral_master import animation_audit,neutral_pose_and_keys
from blender_bridge.skin_material_model import checked_owned_material,nonmaterial_state,material_name,shader_snapshot
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest,read_json
from blender_bridge.godot_outputs import write_json
from blender_bridge.unity_source_reference import reference,export_fbx
from ucc.export.unity_blender_recipe import POLICY,STAGE,VERIFY,FILES,validate_job,validate_recipe
from ucc.export.godot_candidate_contract import canonical_bytes


def source(bpy,root: Path,job: dict):
    options=job['options'];validate_job(job['operation'],job['input_project'],options)
    request,spec=validate_recipe(read_json(root/'unity_source_recipe.json',options['recipe_sha256'],256*1024))
    if dict(request.source_bindings)['master']!=options['master_sha256'] or digest(root/'candidate.blend')!=options['master_sha256']:
        raise ValueError('Unity source differs from the exact reviewed master')
    if bpy.app.version[:2]!=(5,3):raise ValueError('Unity source profile requires Blender 5.3')
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False);animation_audit(bpy)
    human,rig,_,targets=intake(bpy)
    if neutral_pose_and_keys(rig,human)!=12 or checked_owned_material(bpy,human)!=spec:
        raise ValueError('Unity source requires saved neutral canonical controls and the exact owned material')
    state=nonmaterial_state(bpy,human,rig,targets,{material_name(spec)})
    shader=state_digest(shader_snapshot(human.data.materials[0]))
    return request,spec,human,rig,targets,state,shader


def unchanged(bpy,root,job,spec,human,rig,targets,state,shader):
    if (digest(root/'candidate.blend')!=job['options']['master_sha256']
            or nonmaterial_state(bpy,human,rig,targets,{material_name(spec)})!=state
            or state_digest(shader_snapshot(human.data.materials[0]))!=shader):
        raise ValueError('Unity source export changed the original master, rig, controls, UVs or material')


def stage(bpy,root: Path,job: dict) -> dict:
    for name in FILES:
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Unity source refuses existing outputs')
    request,spec,human,rig,targets,state,shader=source(bpy,root,job)
    expected,weights=reference(bpy,human,rig,master_sha=job['options']['master_sha256'],request_sha=request.sha256,spec=spec)
    write_json(root/'source_reference.json',expected);write_json(root/'source_weights.json',weights)
    export_fbx(bpy,human,rig,root/'character.fbx')
    unchanged(bpy,root,job,spec,human,rig,targets,state,shader)
    paths={name:digest(root/name) for name in FILES if name!='unity_source_stage.json'}
    if not (root/'character.fbx').read_bytes()[:23].startswith(b'Kaydara FBX Binary'):raise ValueError('Binary FBX output missing')
    report={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'recipe_sha256':job['options']['recipe_sha256'],
        'master_sha256':job['options']['master_sha256'],'files':paths,'nonmaterial_state_sha256':state,'shader_sha256':shader,
        'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),
        'original_state_preserved':True,'engine_import_verified':False,'project_pointer_changed':False}
    write_json(root/'unity_source_stage.json',report)
    return {'policy':POLICY,'request_sha256':request.sha256,'files':{name:digest(root/name) for name in FILES},'engine_import_verified':False}


def verify(bpy,root: Path,job: dict) -> dict:
    if (root/'unity_source_verification.json').exists() or (root/'unity_source_verification.json').is_symlink():
        raise ValueError('Unity source verification refuses existing output')
    request,spec,human,rig,targets,state,shader=source(bpy,root,job);options=job['options']
    hashes={name:options[name.replace('.','_')+'_sha256'] for name in FILES}
    for name,maximum in FILES.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum or digest(path)!=hashes[name]:
            raise ValueError('Unity staged source artifact changed: '+name)
    expected,weights=reference(bpy,human,rig,master_sha=options['master_sha256'],request_sha=request.sha256,spec=spec)
    actual=read_json(root/'source_reference.json',hashes['source_reference.json'],FILES['source_reference.json'])
    actual_weights=read_json(root/'source_weights.json',hashes['source_weights.json'],FILES['source_weights.json'])
    if canonical_bytes(expected)!=canonical_bytes(actual) or canonical_bytes(weights)!=canonical_bytes(actual_weights):
        raise ValueError('Unity staged geometry/skin/morph/UV reference differs from a fresh original master')
    stage_report=read_json(root/'unity_source_stage.json',hashes['unity_source_stage.json'],FILES['unity_source_stage.json'])
    expected_stage={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'recipe_sha256':options['recipe_sha256'],
        'master_sha256':options['master_sha256'],'files':{name:value for name,value in hashes.items() if name!='unity_source_stage.json'},
        'nonmaterial_state_sha256':state,'shader_sha256':shader,'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),
        'original_state_preserved':True,'engine_import_verified':False,'project_pointer_changed':False}
    if canonical_bytes(stage_report)!=canonical_bytes(expected_stage):raise ValueError('Unity source stage lacks exact source/state binding')
    unchanged(bpy,root,job,spec,human,rig,targets,state,shader)
    report={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'recipe_sha256':options['recipe_sha256'],
        'master_sha256':options['master_sha256'],'files':hashes,'original_state_preserved':True,
        'source_reference_recomputed':True,'exported_fbx_rebuilt':False,'engine_import_verified':False,'project_pointer_changed':False}
    write_json(root/'unity_source_verification.json',report)
    return {'policy':POLICY,'request_sha256':request.sha256,'verification_sha256':digest(root/'unity_source_verification.json'),
            'files':hashes,'engine_import_verified':False}
