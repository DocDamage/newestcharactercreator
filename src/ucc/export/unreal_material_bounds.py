"""Source-derived material and centimeter bounds for the fixed bind profile."""
import math
from ucc.core.skin_material import SkinMaterialSpec
from .unreal_native_data import f32,finite,require
from .unreal_bind_math import expected_position_cm

MATERIAL_FIELDS={'slot_name','imported_slot_name','material_path','material_class','blend_mode','is_two_sided',
                 'base_color_linear_present','base_color_linear_rgba','roughness_present','roughness',
                 'metallic_present','metallic'}


BOUNDS_FIELDS={'origin_cm','box_extent_cm','sphere_radius_cm','imported_origin_cm','imported_box_extent_cm',
               'imported_sphere_radius_cm','nanite_enabled','nanite_settings_enabled','nanite_valid_data',
               'positive_extension_cm','negative_extension_cm'}


def linear(value):
    value=finite(value)
    require(0<=value<=1,'source material sRGB channel outside unit interval')
    return f32(value/12.92 if value<=0.04045 else ((value+0.055)/1.055)**2.4)


def verify_material(source: dict, native: dict, declared_slot: str, declared_imported_slot: str, *, check=None) -> dict:
    if check is not None: check()
    canonical = "UCC_BODY_MAT_V1_" + SkinMaterialSpec.from_dict(source["material_spec"]).sha256[:24]
    require(source["source_material_name"] == canonical and declared_slot == canonical
            and declared_imported_slot == canonical, "material slot expectation must derive from original source material")
    rows=native['readback']['materials']
    require(type(rows) is list and len(rows)==1,'native authored material slot count differs')
    row=rows[0]
    require(set(row)==MATERIAL_FIELDS,'native material fields differ')
    require(row['slot_name']==declared_slot and row['imported_slot_name']==declared_imported_slot,
            'native material slot identity differs from predeclared source/stage recipe')
    require(row['material_path']=='/Game/UCC/SkinMaterial.SkinMaterial' and row['material_class']=='Material',
            'native authored material package/class differs')
    require(type(row['blend_mode']) is int and row['blend_mode']==0 and row['is_two_sided'] is False,
            'native authored material opaque/single-sided policy differs')
    for field in ('base_color_linear_present','roughness_present','metallic_present'):
        require(row[field] is True,'native authored material parameter getter missing')
    spec=source['material_spec']
    require(spec['alpha']==1 and spec['metallic']==0 and not spec['textures'],
            'source authored material scope differs')
    expected=[linear(channel) for channel in spec['base_color_srgb']]+[f32(spec['alpha'])]
    require(len(expected)==4 and len(row['base_color_linear_rgba'])==4,'native material color dimensions differ')
    require([f32(channel) for channel in row['base_color_linear_rgba']]==expected,
            'native authored material linear color differs from source')
    for field in ('roughness','metallic'):
        require(f32(row[field])==f32(spec[field]),'native authored material scalar differs from source')
    require(all(section['material_index']==0 for section in native['readback']['sections']),
            'native section uses an unsolicited material slot')
    return {'single_declared_material_slot_and_sections_exact':True,'source_material_scalars_float32_exact':True,
            'opaque_single_sided_texture_free_metadata_verified':True,'render_or_shader_visual_quality_verified':False}


def verify_bounds(source: dict, native: dict, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    bounds=native['readback']['bounds']
    require(set(bounds)==BOUNDS_FIELDS,'native bounds fields differ')
    for field in ('nanite_enabled','nanite_settings_enabled','nanite_valid_data'):
        require(bounds[field] is False,'native Nanite scope differs from predeclared ordinary LOD0 profile')
    for field in ('positive_extension_cm','negative_extension_cm'):
        require(type(bounds[field]) is list and len(bounds[field])==3
                and all(finite(value)==0 for value in bounds[field]),'native bounds extension differs')
    points=[]
    for index,row in enumerate(source['vertices']):
        if index % 256 == 0: guard()
        points.append(expected_position_cm(row))
    lower=[min(row[i] for row in points) for i in range(3)]
    upper=[max(row[i] for row in points) for i in range(3)]
    origin=[(lo+hi)/2 for lo,hi in zip(lower,upper)]
    extent=[(hi-lo)/2 for lo,hi in zip(lower,upper)]
    radius=math.sqrt(sum(value*value for value in extent))
    imported_radius=max(math.dist(row,origin) for row in points)
    maximum=0.0
    for prefix in ('','imported_'):
        for field,target in [('origin_cm',origin),('box_extent_cm',extent)]:
            actual=bounds[prefix+field]
            require(type(actual) is list and len(actual)==3,'native bounds vector dimensions differ')
            error=max(abs(finite(a)-b) for a,b in zip(actual,target))
            maximum=max(maximum,error)
            require(error<=0.0002,'native centimeter bounds exceed predeclared2um position cap')
        target_radius=imported_radius if prefix=='imported_' else radius
        error=abs(finite(bounds[prefix+'sphere_radius_cm'])-target_radius)
        require(error<=math.sqrt(3)*0.0002,'native centimeter sphere bound exceeds derived coordinate cap')
    return {'source_derived_centimeter_bounds_verified':True,'nanite_disabled_zero_extensions':True,
            'maximum_source_bound_component_error_cm':maximum,'position_component_cap_cm':0.0002}


def verify_graph(stage: dict, reopened: dict) -> dict:
    """Direct readonly expression inputs; shader compilation is a separate gate."""
    expected = {'MP_BASE_COLOR': ('MaterialExpressionVectorParameter', 'UccBaseColorLinear'),
                'MP_ROUGHNESS': ('MaterialExpressionScalarParameter', 'UccRoughness'),
                'MP_METALLIC': ('MaterialExpressionScalarParameter', 'UccMetallic')}
    fields = {'status', 'source_graph_verified', 'expressions', 'property_inputs', 'texture_expression_count'}
    require(type(stage) is dict and set(stage) == fields and stage == reopened,
            'saved/reopened material graph metadata differ or are malformed')
    require(stage['status'] == 'ACTUAL_READONLY_MATERIAL_GRAPH_CAPTURED'
            and stage['source_graph_verified'] is False, 'readonly native material graph unavailable')
    expressions = stage['expressions']; inputs = stage['property_inputs']
    require(type(expressions) is list and len(expressions) == 3 and type(inputs) is dict
            and set(inputs) == set(expected) and type(stage['texture_expression_count']) is int
            and stage['texture_expression_count'] == 0, 'material expression/property domain differs')
    paths = set()
    for name, (kind, parameter) in expected.items():
        row = inputs[name]
        require(type(row) is dict and set(row) == {'path', 'class', 'parameter_name'}
                and row['class'] == kind and row['parameter_name'] == parameter
                and type(row['path']) is str and 0 < len(row['path']) <= 4096,
                'native direct material parameter connection differs')
        paths.add(row['path'])
    require(len(paths) == 3 and all(type(row) is dict and set(row) == {'path', 'class', 'parameter_name'}
                for row in expressions) and {row['path'] for row in expressions} == paths,
            'native material expression path closure differs')
    require({(row['class'], row['parameter_name']) for row in expressions} == set(expected.values()),
            'native material expression identity differs')
    return {'direct_parameter_property_inputs_exact': True, 'zero_texture_expressions': True,
            'shader_compilation_verified': False, 'runtime_visual_quality_verified': False}
