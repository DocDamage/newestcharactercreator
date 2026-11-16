"""Private engine-side admission metadata and const capture; no source vectors."""
from pathlib import Path
from hashlib import sha256
import json
import os
import sys
import unreal
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FLAGS = {'engine_import_verified', 'source_parity_verified', 'shader_compilation_verified', 'runtime_gpu_verified', 'pie_verified', 'player_build_verified', 'visual_quality_approved', 'distribution_license_review_complete', 'cloud_transmission_authorized', 'export_published'}

def digest(path):
    result = sha256()
    with Path(path).open('rb') as stream:
        while (block := stream.read(4 * 1024 * 1024)):
            result.update(block)
    return result.hexdigest()

def read(path, expected=None):
    path = Path(path)
    if not (path.is_absolute() and path.resolve() == path and (not path.is_symlink()) and path.is_file()):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    data = path.read_bytes()
    if not len(data) <= 2 * 1024 * 1024:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if expected is not None:
        if not sha256(data).hexdigest() == expected:
            raise RuntimeError('Unreal fixed recipe or source binding rejected')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate control JSON key')
            result[key] = value
        return result

    def finite(value):
        raise ValueError('Nonfinite control JSON number')
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_constant=finite)

def write(path, record):
    path = Path(path)
    if not (not path.exists() and (not path.is_symlink())):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    with path.open('xb') as stream:
        stream.write((json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())

def identity(mode):
    path = Path(unreal.Paths.project_dir()).resolve() / '.ucc-job.json'
    control = read(path)
    fields = {'schema_version', 'policy', 'mode', 'export_request', 'request_sha256', 'toolchain_identity_sha256', 'engine_identity', 'engine_profile_path', 'engine_profile_sha256', 'source_descriptor_path', 'source_descriptor_sha256', 'source_fbx_path', 'source_fbx_sha256', 'output_directory', 'material_spec', 'stage_receipt_path', 'stage_receipt_sha256'}
    if not (set(control) == fields and control['schema_version'] == 1):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not (control['policy'] == 'UCC_UNREAL_EDITOR_JOB_V1' and control['mode'] == mode):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    request = control['export_request']
    if not all((request[name] is False for name in FLAGS)):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    canonical = (json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if not sha256(canonical).hexdigest() == control['request_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not control['toolchain_identity_sha256'] == request['toolchain_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    profile = read(control['engine_profile_path'], control['engine_profile_sha256'])
    if not digest(profile['observer_dll']) == profile['observer_dll_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not unreal.SystemLibrary.get_engine_version() == request['engine_version']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not digest(control['source_fbx_path']) == control['source_fbx_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    descriptor = read(control['source_descriptor_path'], control['source_descriptor_sha256'])
    if not descriptor['request_sha256'] == control['request_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not descriptor['files']['character.fbx'] == control['source_fbx_sha256']:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not descriptor['source_reference_supplied_to_engine'] is False:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if mode == 'STAGE':
        if not (control['stage_receipt_path'] is None and control['stage_receipt_sha256'] is None):
            raise RuntimeError('Unreal fixed recipe or source binding rejected')
    else:
        stage = read(control['stage_receipt_path'], control['stage_receipt_sha256'])
        if not (stage['mode'] == 'STAGE' and stage['state'] == 'CAPTURED_UNVERIFIED'):
            raise RuntimeError('Unreal fixed recipe or source binding rejected')
        if not stage['request_sha256'] == control['request_sha256']:
            raise RuntimeError('Unreal fixed recipe or source binding rejected')
        if not stage['source_fbx_sha256'] == control['source_fbx_sha256']:
            raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not unreal.SystemLibrary.get_console_variable_int_value('r.TriangleOrderOptimization') == 2:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    root = {'job_id': request['job_id'], 'material_spec': control['material_spec'], 'unreal': control['engine_identity']}
    return (control, root, profile)

def typed(value, name):
    if isinstance(value, str) and '.' in value:
        enum, member = value.split('.', 1)
        return getattr(getattr(unreal, enum), member)
    if name == 'import_translation':
        return unreal.Vector(*value)
    if name == 'import_rotation':
        return unreal.Rotator(*value)
    return value

def apply(obj, values):
    for name, value in values.items():
        expected = typed(value, name)
        obj.set_editor_property(name, expected)
        if not obj.get_editor_property(name) == expected:
            raise RuntimeError('Unreal fixed recipe or source binding rejected')

def simple(value):
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, unreal.Vector):
        return [value.x, value.y, value.z]
    if isinstance(value, unreal.Rotator):
        return [value.pitch, value.yaw, value.roll]
    return str(value)

def observed(obj, values):
    return {name: simple(obj.get_editor_property(name)) for name in values}

def material_graph(material):
    methods = ('get_material_expressions', 'get_material_property_input_node')
    if not all((hasattr(unreal.MaterialEditingLibrary, name) for name in methods)):
        return {'status': 'HOLD_READONLY_GRAPH_API_UNAVAILABLE', 'source_graph_verified': False}
    expressions = unreal.MaterialEditingLibrary.get_material_expressions(material)
    rows = []
    for expression in expressions:
        row = {'path': expression.get_path_name(), 'class': expression.get_class().get_name()}
        if isinstance(expression, (unreal.MaterialExpressionVectorParameter, unreal.MaterialExpressionScalarParameter)):
            row['parameter_name'] = str(expression.get_editor_property('parameter_name'))
        rows.append(row)
    inputs = {}
    for name in ('MP_BASE_COLOR', 'MP_ROUGHNESS', 'MP_METALLIC'):
        node = unreal.MaterialEditingLibrary.get_material_property_input_node(material, getattr(unreal.MaterialProperty, name))
        inputs[name] = None if node is None else {'path': node.get_path_name(), 'class': node.get_class().get_name(), 'parameter_name': str(node.get_editor_property('parameter_name')) if isinstance(node, (unreal.MaterialExpressionVectorParameter, unreal.MaterialExpressionScalarParameter)) else None}
    return {'status': 'ACTUAL_READONLY_MATERIAL_GRAPH_CAPTURED', 'source_graph_verified': False, 'expressions': rows, 'property_inputs': inputs, 'texture_expression_count': sum(('Texture' in row['class'] for row in rows))}

def capture(mode, control, root, profile, mesh):
    output = Path(control['output_directory'])
    if not mesh.get_path_name() == '/Game/UCC/Character.Character':
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    raw = unreal.UccNativeObservationLibrary.observe_skeletal_mesh(mesh)
    native = json.loads(raw)
    write(output / 'native-observation.json', native)
    if native['status'] != 'CAPTURED_UNVERIFIED' or not native['native_data_observed']:
        raise RuntimeError('Native const observer rejected: ' + str(native['reason']))
    if not (native['schema_version'] == 2 and native['policy'] == 'UCC_PRIVATE_UNREAL_CONST_OBSERVATION_V2'):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    if not all((native[name] is False for name in ('source_parity_verified', 'runtime_gpu_verified', 'asset_modified_or_saved'))):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    settings = subsystem.get_lod_build_settings(mesh, 0)
    material = unreal.load_asset('/Game/UCC/SkinMaterial')
    skeleton = mesh.get_editor_property('skeleton')
    if not (material is not None and skeleton is not None):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    nanite = mesh.get_editor_property('nanite_settings')
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    skel_actors = [actor for actor in actors if isinstance(actor, unreal.SkeletalMeshActor)]
    if not len(skel_actors) == 1:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    component = skel_actors[0].get_editor_property('skeletal_mesh_component')
    if not component.get_skeletal_mesh_asset() == mesh:
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
    envelope = {'schema_version': 1, 'policy': 'UCC_UNREAL_NATIVE_BIND_CAPTURE_V1', 'mode': mode, 'state': 'CAPTURED_UNVERIFIED', 'job_id': root['job_id'], 'request_sha256': control['request_sha256'], 'toolchain_identity_sha256': control['toolchain_identity_sha256'], 'engine_profile_sha256': control['engine_profile_sha256'], 'source_fbx_path': control['source_fbx_path'], 'source_descriptor_path': control['source_descriptor_path'], 'source_fbx_sha256': control['source_fbx_sha256'], 'source_descriptor_sha256': control['source_descriptor_sha256'], 'observer_dll_sha256': profile['observer_dll_sha256'], 'observer_source_files': profile['observer_source_sha256'], 'engine_exe_sha256': root['unreal']['editor_executable_sha256'], 'engine_build_sha256': root['unreal']['build_version_sha256'], 'native_observation_path': str(output / 'native-observation.json'), 'native_observation_sha256': digest(output / 'native-observation.json'), 'actual_import_settings': observed(mesh.get_editor_property('asset_import_data'), profile['skeletal_mesh_import_data']), 'actual_lod_build_settings': observed(settings, profile['stage_owned_lod0_build_settings']), 'actual_mesh_settings': {'nanite_settings.enabled': nanite.get_editor_property('enabled'), 'positive_bounds_extension': simple(mesh.get_editor_property('positive_bounds_extension')), 'negative_bounds_extension': simple(mesh.get_editor_property('negative_bounds_extension'))}, 'actual_triangle_order_optimization': unreal.SystemLibrary.get_console_variable_int_value('r.TriangleOrderOptimization'), 'actual_assets': {'mesh': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'material': material.get_path_name(), 'scene': '/Game/UCC/CharacterScene'}, 'actual_material_graph': material_graph(material), 'scene_actor_class': skel_actors[0].get_class().get_name(), 'scene_actor_location': simple(skel_actors[0].get_actor_location()), 'scene_actor_rotation': simple(skel_actors[0].get_actor_rotation()), 'scene_actor_scale': simple(skel_actors[0].get_actor_scale3d()), 'native_observation_captured': True, **{name: False for name in FLAGS}}
    write(output / 'capture-receipt.json', envelope)
    unreal.log('UCC_PRIVATE_NATIVE_CAPTURE_UNVERIFIED_' + mode)
