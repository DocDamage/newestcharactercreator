"""Generated nonshipping analytic octahedron; never engine-integration evidence."""
import copy
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import base64

from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.unreal_contract import ENGINE_VERSION, PROFILE, READINESS_FLAGS
from ucc.export.unreal_engine_profile import FBX_IMPORT, LOD_BUILD, MESH_SETTINGS

REQUEST_SHA = '2'*64
TOOLCHAIN_SHA = '3'*64


def packed(rows, fmt, encoding):
    raw=b''.join(struct.pack('<'+fmt,*row) for row in rows)
    return {'encoding':encoding,'count':len(rows),'bytes':len(raw),'base64':base64.b64encode(raw).decode()}


def f32(value): return struct.unpack('<f',struct.pack('<f',value))[0]


def fixture_data():
    spec=SkinMaterialSpec((.5,.5,.5),.5)
    material='UCC_BODY_MAT_V1_'+spec.sha256[:24]
    points=[[.01,0,0],[-.01,0,0],[0,.01,0],[0,-.01,0],[0,0,.01],[0,0,-.01]]
    faces=[[0,2,4],[2,1,4],[1,3,4],[3,0,4],[2,0,5],[1,2,5],[3,1,5],[0,3,5]]
    identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
    # Analytic source basis .01*Rz(-90) maps to the native identity basis.
    root=[0,.01,0,0,-.01,0,0,0,0,0,.01,0,0,0,0,1]
    child=root.copy();child[7]=-.01
    source={'schema_version':1,'policy':'UCC_UNREAL_ORIGINAL_BIND_REFERENCE_V1','profile':PROFILE,
        'master_sha256':'1'*64,'request_sha256':REQUEST_SHA,'blender_version':'5.3.0','blender_build':'0'*12,
        'material_spec':spec.to_dict(),'vertices':points,'quads':[],'triangles':faces,
        'corners':[{'vertices':face,'uv':[[.25,.75]]*3} for face in faces],
        'weights':[[['child.L',.375],['root',.25]] for _ in points],
        'morphs':{'UCC_TestControl':[[0,0,.00001] for _ in points]},
        'bones':[{'name':'root','parent':None,'world':root},{'name':'child.L','parent':'root','world':child}],
        'candidate_observation':{'nonshipping_synthetic_logic_fixture':True},
        'source_bind_local_vertices':copy.deepcopy(points),'source_bind_object_world':identity,
        'source_to_unreal_bone_names':{'root':'root','child.L':'child_L'},'original_rig_world':identity,
        'original_rig_object_scale':[1,1,1],'source_material_name':material,
        'rig_basis_policy':'ORIGINAL_OBJECT_AND_REST_DATA_NO_TRANSFORM_APPLICATION_OR_BONE_NORMALIZATION',
        'engine_import_verified':False,'expected_unreal_bone_order':['root','child_L']}
    native_points=[(-100*y,-100*x,100*z) for x,y,z in points]
    normals=[tuple(value/math.sqrt(sum(v*v for v in point)) for value in point) for point in points]
    native_normals=[(-y,-x,z) for x,y,z in normals]
    normal_bytes=b''.join(struct.pack('<3f',*normals[index]) for face in faces for index in face)
    inverse_child=identity.copy();inverse_child[12]=-1  # native matrices use row vectors
    raw_weights=b''.join(bytes([0,1])+struct.pack('<HH',26214,39321) for _ in points)
    rb={'mesh_package':'/Game/UCC/Character','mesh_object':'/Game/UCC/Character.Character','unit':'native_unreal_centimeter',
        'positions':packed(native_points,'fff','float32x3_le'),
        'normals':packed(native_normals,'fff','float32x3_le'),
        'uv0':packed([(.25,.25)]*6,'ff','float32x2_le'),
        'triangle_indices':packed([(index,) for face in faces for index in face],'I','uint32_le'),
        'positive_influence_counts':packed([(2,)]*6,'I','uint32_le'),
        'positive_influences':packed([(v,b,w) for v in range(6) for b,w in [(0,26214),(1,39321)]],
                                     'IIH','uint32_vertex_uint32_bone_uint16_apiweight_le'),
        'inverse_bind_matrices':packed([identity,inverse_child],'16f','float32x16_rowmajor_le'),
        'bones':[{'name':'root','parent':-1,'local_trs_float64_quaternion_xyzw_translation_scale':[0,0,0,1,0,0,0,1,1,1]},
                 {'name':'child_L','parent':0,'local_trs_float64_quaternion_xyzw_translation_scale':[0,0,0,1,1,0,0,1,1,1]}],
        'morphs':[{'name':'UCC_TestControl','deltas':packed([(i,0,0,.001,0,0,0) for i in range(6)],
                         'I6f','uint32_native_index_float32x3_position_float32x3_tangent_le')}],
        'native_weight_storage_bytes':2,'native_bone_index_storage_bytes':1,'native_variable_influences':False,
        'native_unified_bone_map':False,'api_weight_normalization':'uint16_div65535; stored8bit_expands257_per_engine_accessor',
        'native_uv_storage_full_precision':True,'native_high_precision_tangent_basis':True,
        'native_max_bone_influences':2,'native_constant_influences_stride':6,
        'native_constant_influences_bone_weights_offset':2,
        'native_weight_data':packed([(value,) for value in raw_weights],'B','uint8_native_skin_weight_storage'),
        'native_weight_lookup':packed([],'B','uint8_native_skin_weight_lookup_storage'),'unified_bone_map':[],
        'sections':[{'material_index':0,'base_index':0,'num_triangles':8,'base_vertex_index':0,'num_vertices':6,
                     'max_bone_influences':2,'bone_map':[0,1],'has_unified_bone_map':False}],
        'materials':[{'slot_name':material,'imported_slot_name':material,'material_path':'/Game/UCC/SkinMaterial.SkinMaterial',
                     'material_class':'Material','blend_mode':0,'is_two_sided':False,'base_color_linear_present':True,
                     'base_color_linear_rgba':[f32(v) for v in spec.linear_rgba],
                     'roughness_present':True,'roughness':.5,'metallic_present':True,'metallic':0}],
        'bounds':{'origin_cm':[0,0,0],'box_extent_cm':[1,1,1],'sphere_radius_cm':math.sqrt(3),
                  'imported_origin_cm':[0,0,0],'imported_box_extent_cm':[1,1,1],'imported_sphere_radius_cm':1,
                  'nanite_enabled':False,'nanite_settings_enabled':False,'nanite_valid_data':False,
                  'positive_extension_cm':[0,0,0],'negative_extension_cm':[0,0,0]}}
    observation={'schema_version':2,'policy':'UCC_PRIVATE_UNREAL_CONST_OBSERVATION_V2','engine_version':ENGINE_VERSION,
        'observer_module':'nonshipping-generated-observer.dll','status':'CAPTURED_UNVERIFIED',
        'reason':'HOST_SOURCE_PARITY_REQUIRED','native_data_observed':True,'source_parity_verified':False,
        'runtime_gpu_verified':False,'asset_modified_or_saved':False,'readback':rb}
    return source,normal_bytes,observation,spec


def graph():
    inputs={}
    for name,kind,parameter in [('MP_BASE_COLOR','MaterialExpressionVectorParameter','UccBaseColorLinear'),
                               ('MP_ROUGHNESS','MaterialExpressionScalarParameter','UccRoughness'),
                               ('MP_METALLIC','MaterialExpressionScalarParameter','UccMetallic')]:
        inputs[name]={'path':'/Game/UCC/SkinMaterial.SkinMaterial:'+parameter,'class':kind,'parameter_name':parameter}
    return {'status':'ACTUAL_READONLY_MATERIAL_GRAPH_CAPTURED','source_graph_verified':False,
            'expressions':list(inputs.values()),'property_inputs':inputs,'texture_expression_count':0}


def receipt(mode,observation_path,observation_sha):
    return {'schema_version':1,'policy':'UCC_UNREAL_NATIVE_BIND_CAPTURE_V1','mode':mode,'state':'CAPTURED_UNVERIFIED',
        'job_id':'00000000-0000-0000-0000-000000000001','request_sha256':REQUEST_SHA,
        'toolchain_identity_sha256':TOOLCHAIN_SHA,'engine_profile_sha256':'4'*64,
        'source_descriptor_path':str(observation_path.parent.parent/'source-descriptor.json'),'source_descriptor_sha256':'5'*64,
        'source_fbx_path':str(observation_path.parent.parent/'character.fbx'),'source_fbx_sha256':'6'*64,
        'observer_dll_sha256':'7'*64,'observer_source_files':{'Source/GeneratedObserver.cpp':'8'*64},
        'engine_exe_sha256':'9'*64,'engine_build_sha256':'a'*64,
        'native_observation_path':str(observation_path),'native_observation_sha256':observation_sha,
        'actual_import_settings':copy.deepcopy(FBX_IMPORT),'actual_lod_build_settings':copy.deepcopy(LOD_BUILD),
        'actual_mesh_settings':copy.deepcopy(MESH_SETTINGS),'actual_triangle_order_optimization':2,
        'actual_assets':{'mesh':'/Game/UCC/Character.Character','skeleton':'/Game/UCC/Character_Skeleton.Character_Skeleton',
                         'material':'/Game/UCC/SkinMaterial.SkinMaterial','scene':'/Game/UCC/CharacterScene'},
        'actual_material_graph':graph(),'scene_actor_class':'SkeletalMeshActor',
        'scene_actor_location':[0,0,0],'scene_actor_rotation':[0,0,0],'scene_actor_scale':[1,1,1],
        'native_observation_captured':True,**{name:False for name in READINESS_FLAGS}}


def write_json(path,value):
    path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
    return sha256(path.read_bytes()).hexdigest()


def write_inputs(directory: Path):
    directory=Path(directory).resolve()
    source,normals,observation,spec=fixture_data()
    paths={name:directory/name for name in ['reference.json','normals.bin','native.json','reopened.json','stage.json','fresh.json']}
    source_sha=write_json(paths['reference.json'],source);paths['normals.bin'].write_bytes(normals)
    native_sha=write_json(paths['native.json'],observation)
    reopened=copy.deepcopy(observation);reopened['observer_module']='another-generated-copy.dll'
    fresh_sha=write_json(paths['reopened.json'],reopened)
    stage_sha=write_json(paths['stage.json'],receipt('STAGE',paths['native.json'],native_sha))
    reopened_sha=write_json(paths['fresh.json'],receipt('FRESH',paths['reopened.json'],fresh_sha))
    material=source['source_material_name']
    return {'source_reference':paths['reference.json'],'source_normals':paths['normals.bin'],
        'native_observation':paths['native.json'],'reopened_native_observation':paths['reopened.json'],
        'stage_receipt':paths['stage.json'],'stage_receipt_sha256':stage_sha,
        'reopened_receipt':paths['fresh.json'],'reopened_receipt_sha256':reopened_sha,
        'request_sha256':REQUEST_SHA,'toolchain_identity_sha256':TOOLCHAIN_SHA,
        'source_reference_sha256':source_sha,'source_normals_sha256':sha256(normals).hexdigest(),
        'native_observation_sha256':native_sha,'reopened_native_observation_sha256':fresh_sha,
        'engine_version':ENGINE_VERSION,'material_spec':spec,'material_slot_name':material,'imported_material_slot_name':material}
