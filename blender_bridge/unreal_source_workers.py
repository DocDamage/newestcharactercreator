"""Source-only Unreal staging and independent original-master recomputation."""
from pathlib import Path
import math
from blender_bridge.face_geometry import intake
from blender_bridge.neutral_master import animation_audit, neutral_pose_and_keys
from blender_bridge.skin_material_model import checked_owned_material, nonmaterial_state, material_name, shader_snapshot
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest, read_json
from blender_bridge.godot_outputs import write_json
from blender_bridge.unreal_source_reference import reference, export_character
from blender_bridge.unreal_fbx_metadata import fbx_metadata
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import PROFILE, READINESS_FLAGS
from ucc.export.unreal_blender_recipe import POLICY, STAGE, VERIFY, FILES, NORMAL_BYTES, VERIFICATION_FILE
from ucc.export.unreal_blender_recipe import EXPORT_OPTIONS, validate_job, validate_recipe


def source(bpy, root: Path, job: dict):
    options = job['options']; validate_job(job['operation'], job['input_project'], options)
    request, spec = validate_recipe(read_json(root/'unreal_source_recipe.json', options['recipe_sha256'], 256*1024))
    if dict(request.source_bindings)['master'] != options['master_sha256'] or digest(root/'candidate.blend') != options['master_sha256']:
        raise ValueError('Unreal source differs from the exact reviewed master')
    if bpy.app.version_string != '5.3.0' or bpy.app.build_hash.decode() != '02f0899d78e3':
        raise ValueError('Unreal source profile requires the admitted Blender 5.3 build')
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False); animation_audit(bpy)
    human, rig, _, targets = intake(bpy)
    if neutral_pose_and_keys(rig, human) != 12 or checked_owned_material(bpy, human) != spec:
        raise ValueError('Unreal source needs saved neutral canonical controls and its exact owned material')
    from io_scene_fbx.fbx_utils import units_blender_to_fbx_factor
    if units_blender_to_fbx_factor(bpy.context.scene) != 100.:
        raise ValueError('Unreal source scene does not use the declared one-metre Blender unit')
    if rig.matrix_world.determinant() <= 0 or any(not math.isfinite(float(v)) or v <= 0 for v in rig.scale):
        raise ValueError('Unreal source rejects nonfinite, reflected or zero rig transforms')
    state = nonmaterial_state(bpy, human, rig, targets, {material_name(spec)})
    shader = state_digest(shader_snapshot(human.data.materials[0]))
    return request, spec, human, rig, targets, state, shader


def unchanged(bpy, root, job, spec, human, rig, targets, state, shader):
    if (digest(root/'candidate.blend') != job['options']['master_sha256']
            or nonmaterial_state(bpy, human, rig, targets, {material_name(spec)}) != state
            or state_digest(shader_snapshot(human.data.materials[0])) != shader):
        raise ValueError('Unreal source operation changed its original master, rig, controls, UVs or material')


def common(request, job, state, shader, bpy, metadata):
    return {'schema_version':1, 'policy':POLICY, 'profile':PROFILE, 'request_sha256':request.sha256,
        'recipe_sha256':job['options']['recipe_sha256'], 'master_sha256':job['options']['master_sha256'],
        'nonmaterial_state_sha256':state, 'shader_sha256':shader,
        'blender_version':bpy.app.version_string, 'blender_build':bpy.app.build_hash.decode(),
        'export_options':EXPORT_OPTIONS, 'fbx_metadata':metadata,
        'original_master_file_unchanged':True, 'source_reference_recomputed':True,
        'project_pointer_changed':False, 'runtime_deformation_verified':False,
        **{name:False for name in READINESS_FLAGS}}


def stage(bpy, root: Path, job: dict) -> dict:
    for name in FILES:
        if (root/name).exists() or (root/name).is_symlink():
            raise ValueError('Unreal source refuses existing output paths')
    request, spec, human, rig, targets, state, shader = source(bpy, root, job)
    expected, normals, normal_info = reference(bpy, human, rig,
        master_sha=job['options']['master_sha256'], request_sha=request.sha256, spec=spec)
    export_character(bpy, root, human, rig)
    metadata, order = fbx_metadata(root/'character.fbx', expected)
    expected['expected_unreal_bone_order'] = order
    unchanged(bpy, root, job, spec, human, rig, targets, state, shader)
    write_json(root/'source_reference.json', expected)
    with (root/'source_corner_normals.bin').open('xb') as stream:
        stream.write(normals)
    write_json(root/'source_corner_normals.json', normal_info)
    report = common(request, job, state, shader, bpy, metadata)
    report['files'] = {name:digest(root/name) for name in FILES if name != 'unreal_source_stage.json'}
    write_json(root/'unreal_source_stage.json', report)
    return {'policy':POLICY, 'request_sha256':request.sha256,
        'files':{name:digest(root/name) for name in FILES}, 'engine_import_verified':False}


def verify(bpy, root: Path, job: dict) -> dict:
    if (root/VERIFICATION_FILE).exists() or (root/VERIFICATION_FILE).is_symlink():
        raise ValueError('Fresh Unreal source proof already exists')
    options = job['options']; validate_job(job['operation'], job['input_project'], options)
    hashes = {name:options[name.replace('.', '_')+'_sha256'] for name in FILES}
    for name, maximum in FILES.items():
        path = root/name
        if (path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= maximum
                or path.resolve() != path or digest(path) != hashes[name]):
            raise ValueError('Sealed Unreal source artifact changed: '+name)
    if (root/'source_corner_normals.bin').stat().st_size != NORMAL_BYTES:
        raise ValueError('Sealed Unreal normals have incomplete byte coverage')
    request, spec, human, rig, targets, state, shader = source(bpy, root, job)
    expected, normals, normal_info = reference(bpy, human, rig,
        master_sha=options['master_sha256'], request_sha=request.sha256, spec=spec)
    metadata, order = fbx_metadata(root/'character.fbx', expected)
    expected['expected_unreal_bone_order'] = order
    if (canonical_bytes(read_json(root/'source_reference.json', hashes['source_reference.json'], FILES['source_reference.json'])) != canonical_bytes(expected)
            or (root/'source_corner_normals.bin').read_bytes() != normals
            or canonical_bytes(read_json(root/'source_corner_normals.json', hashes['source_corner_normals.json'], FILES['source_corner_normals.json'])) != canonical_bytes(normal_info)):
        raise ValueError('Unreal stage reference or normals differ from a fresh original master')
    expected_stage = common(request, job, state, shader, bpy, metadata)
    expected_stage['files'] = {name:value for name,value in hashes.items() if name != 'unreal_source_stage.json'}
    staged = read_json(root/'unreal_source_stage.json', hashes['unreal_source_stage.json'], FILES['unreal_source_stage.json'])
    if canonical_bytes(staged) != canonical_bytes(expected_stage):
        raise ValueError('Unreal stage proof differs from independent original-source recomputation')
    unchanged(bpy, root, job, spec, human, rig, targets, state, shader)
    if any(digest(root/name) != sha for name,sha in hashes.items()):
        raise ValueError('Unreal source verification changed a sealed source artifact')
    report = {'schema_version':1, 'policy':POLICY, 'profile':PROFILE,
        'request_sha256':request.sha256, 'recipe_sha256':options['recipe_sha256'],
        'master_sha256':options['master_sha256'], 'files':hashes,
        'original_state_preserved':True, 'source_reference_recomputed':True,
        'fresh_original_master_reopened':True, 'exported_fbx_rebuilt':False,
        'project_pointer_changed':False, 'runtime_deformation_verified':False,
        **{name:False for name in READINESS_FLAGS}}
    write_json(root/VERIFICATION_FILE, report)
    return {'policy':POLICY, 'request_sha256':request.sha256,
        'verification_sha256':digest(root/VERIFICATION_FILE), 'files':hashes, 'engine_import_verified':False}
