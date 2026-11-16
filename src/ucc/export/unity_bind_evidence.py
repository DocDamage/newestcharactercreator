"""Independent native bind-surface admission; no Blender/Unity/runtime imports."""
from collections import Counter,defaultdict
from itertools import product
import math,struct
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from .godot_candidate_contract import canonical_bytes
from .unity_skin_precision import validate_native_weights,MAX_DEFORMATION_ERROR_M
from .unity_topology import UnityQuadSource



POLICY='UCC_UNITY_NATIVE_BIND_OBSERVATION_V1'
SOURCE_POLICY='UCC_UNITY_ORIGINAL_BIND_REFERENCE_V1'


def closed(value: object,fields: set[str],label: str) -> dict:
    if type(value) is not dict or set(value)!=fields:raise ValidationError('Malformed Unity '+label)
    return value


def number(value: object) -> float:
    if type(value) not in (int,float):raise ValidationError('Unity observation needs finite numeric values')
    try:valid=math.isfinite(value)
    except OverflowError:valid=False
    if not valid:raise ValidationError('Unity observation needs finite numeric values')
    return float(value)


def sequence(value: object,count: int,label: str) -> list:
    if type(value) is not list or len(value)!=count:raise ValidationError('Incomplete Unity '+label)
    return value


def vector(value: object,axes: str='xyz') -> tuple[float,...]:
    return tuple(number(closed(value,set(axes),'vector')[k]) for k in axes)


def source_vector(value: object) -> tuple[float,float,float]:
    p=tuple(number(v) for v in sequence(value,3,'source coordinate'))
    return (-p[0],p[2],-p[1])


def triangle(value: object,count: int) -> tuple[int,int,int]:
    if (type(value) not in (list,tuple) or len(value)!=3
            or any(type(v) is not int or not 0<=v<count for v in value) or len(set(value))!=3):
        raise ValidationError('Unity triangle has invalid or repeated vertex identities')
    return tuple(value)


def cyclic(value: tuple[int,int,int]) -> tuple[int,int,int]:
    """Preserve orientation while admitting an equivalent starting corner."""
    return min(value[i:]+value[:i] for i in range(3))


def correspondence(points: list[tuple[float,...]],native: list[tuple[float,...]]) -> tuple[tuple[int,...],float]:
    buckets=defaultdict(list)
    def cell(p):return tuple(math.floor(v*10000) for v in p)
    if any(len(p)!=3 or any(not math.isfinite(v) or abs(v)>100 for v in p) for p in (*points,*native)):
        raise ValidationError('Unity bind correspondence needs finite three-dimensional points within 100 metres')
    for i,p in enumerate(points):buckets[cell(p)].append(i)
    ids=[];maximum=0.
    for p in native:
        key=cell(p)
        matches=[i for d in product((-1,0,1),repeat=3)
                 for i in buckets.get(tuple(key[k]+d[k] for k in range(3)),()) if math.dist(p,points[i])<2e-6]
        if len(matches)!=1:raise ValidationError('Missing or ambiguous exact Unity source/native vertex correspondence')
        ids.append(matches[0]);maximum=max(maximum,math.dist(p,points[matches[0]]))
    if set(ids)!=set(range(len(points))):raise ValidationError('Unity native surface omits original source vertices')
    return tuple(ids),maximum


def validate_bind_observation(reference: dict,actual: dict,*,request_sha256: str,master_sha256: str,mode: str) -> tuple[UnityQuadSource,dict]:
    if not is_sha256(request_sha256) or not is_sha256(master_sha256) or mode not in ('stage','reopen'):
        raise ValidationError('Unity bind evidence needs explicit source/request/mode bindings')
    closed(reference,{'schema_version','policy','master_sha256','request_sha256','blender_version','blender_build','material_spec',
        'vertices','quads','triangles','corners','weights','morphs','bones','candidate_observation','engine_import_verified'},'source reference')
    closed(actual,{'schema_version','policy','request_sha256','master_sha256','mode','native_mesh_sha256','profile','vertices','baked','uv',
        'triangles','influences','weights','skin_bones','bones','shapes','material','runtime_component_present','runtime_verified','visual_quality_approved'},'native observation')
    for raw,policy in ((reference,SOURCE_POLICY),(actual,POLICY)):
        if (type(raw['schema_version']) is not int or raw['schema_version']!=1 or raw['policy']!=policy
                or raw['request_sha256']!=request_sha256 or raw['master_sha256']!=master_sha256):
            raise ValidationError('Unity bind observation changed its source/version/request bindings')
    if (reference['engine_import_verified'] is not False or actual['runtime_verified'] is not False
            or actual['visual_quality_approved'] is not False or actual['mode']!=mode
            or type(actual['runtime_component_present']) is not bool or not is_sha256(actual['native_mesh_sha256'])
            or reference['blender_version']!='5.3.0' or reference['blender_build']!='02f0899d78e3'):
        raise ValidationError('Unity bind evidence changed its capabilities or admitted build')
    profile=closed(actual['profile'],{'unity','color_space','skin_weights','renderer_quality','max_influences','animation_clips',
        'readable','offscreen','force_matrix_recalculation','import_animation','optimize_bones','bake_axis','minimum_weight'},'native profile')
    expected={'unity':'6000.4.5f1','color_space':'Linear','skin_weights':'Unlimited','renderer_quality':'Auto','max_influences':8,
        'animation_clips':0,'readable':True,'offscreen':True,'force_matrix_recalculation':False,'import_animation':False,
        'optimize_bones':False,'bake_axis':True,'minimum_weight':struct.unpack('<f',struct.pack('<f',.001))[0]}
    if canonical_bytes(profile)!=canonical_bytes(expected):raise ValidationError('Unity native import profile differs from the admitted settings')
    points=[source_vector(v) for v in sequence(reference['vertices'],13380,'original bind points')]
    native=[vector(v) for v in sequence(actual['vertices'],14517,'native bind points')]
    ids,position_error=correspondence(points,native)
    baked=[vector(v) for v in sequence(actual['baked'],len(native),'evaluated native rest points')]
    rest_error=max(math.dist(p,points[ids[i]]) for i,p in enumerate(baked))
    if rest_error>MAX_DEFORMATION_ERROR_M:raise ValidationError('Unity evaluated rest surface exceeds the fixed source-position quality cap')
    source_triangles=[triangle(t,len(points)) for t in sequence(reference['triangles'],26756,'original triangles')]
    flat=sequence(actual['triangles'],26756*3,'native triangle indices')
    native_triangles=[triangle(flat[k:k+3],len(native)) for k in range(0,len(flat),3)]
    expected_triangles=Counter(cyclic((a,c,b)) for a,b,c in source_triangles)
    observed_triangles=Counter(cyclic(tuple(ids[v] for v in t)) for t in native_triangles)
    if expected_triangles!=observed_triangles:raise ValidationError('Unity triangle identities, winding or multiplicity differ from the reflected source')
    corners={}
    for row in sequence(reference['corners'],len(source_triangles),'original UV corners'):
        closed(row,{'vertices','uv'},'original UV triangle')
        t=triangle(row['vertices'],len(points));key=cyclic(t)
        if key in corners:raise ValidationError('Duplicate original UV triangle')
        uvs=[tuple(number(c) for c in sequence(v,2,'source UV')) for v in sequence(row['uv'],3,'triangle UV corners')]
        corners[key]=dict(zip(t,uvs))
    if Counter(corners.keys())!=Counter(cyclic(t) for t in source_triangles):raise ValidationError('Original triangle/UV identity coverage differs')
    uv=[vector(v,'xy') for v in sequence(actual['uv'],len(native),'native UVs')]
    for t in native_triangles:
        a,b,c=(ids[v] for v in t);row=corners[cyclic((a,c,b))]
        if any(uv[v]!=row[ids[v]] for v in t):raise ValidationError('Unity UV corner differs from its exact original triangle corner')
    bones=sequence(actual['skin_bones'],163,'skin bones')
    if any(type(n) is not str or not n for n in bones) or len(set(bones))!=163:raise ValidationError('Unity native bone identities are ambiguous')
    source_weights=[]
    for row in sequence(reference['weights'],len(points),'source influences'):
        if type(row) is not list or not 1<=len(row)<=8:raise ValidationError('Unsupported original influence count')
        entries=[sequence(v,2,'named source influence') for v in row]
        if any(not 0<number(w)<=1 for _,w in entries):raise ValidationError('Original skin influence is not a positive bounded weight')
        total=math.fsum(number(w) for _,w in entries)
        if total<=.0001:raise ValidationError('Original skin has no usable positive influences')
        source_weights.append(tuple((name,number(w)/total) for name,w in entries))
    counts=sequence(actual['influences'],len(native),'native influence counts');weights=actual['weights']
    if type(weights) is not list or not len(native)<=len(weights)<=8*len(native):raise ValidationError('Native positive influence storage exceeds profile')
    offset=0;weight_error=0.
    for i,count in enumerate(counts):
        if type(count) is not int or not 1<=count<=8:raise ValidationError('Native influence count is unsupported')
        row=[]
        for entry in weights[offset:offset+count]:
            closed(entry,{'bone','weight'},'native influence');bone=entry['bone']
            if type(bone) is not int or not 0<=bone<163:raise ValidationError('Native influence references a missing bone')
            row.append((bones[bone],number(entry['weight'])))
        if len(row)!=count:raise ValidationError('Native influence storage truncated')
        observed=validate_native_weights(source_weights[ids[i]],tuple(row));weight_error=max(weight_error,observed.maximum_error);offset+=count
    if offset!=len(weights):raise ValidationError('Native influence storage has trailing rows')
    source_morphs=reference['morphs'];shapes=sequence(actual['shapes'],12,'facial shapes')
    if type(source_morphs) is not dict or len(source_morphs)!=12:raise ValidationError('Original canonical shape coverage differs')
    morph_errors={}
    for shape in shapes:
        closed(shape,{'name','frame_weight','deltas'},'native facial shape');name=shape['name']
        if type(name) is not str or name not in source_morphs or name in morph_errors or number(shape['frame_weight'])!=100:
            raise ValidationError('Native facial identity/frame differs')
        expected_delta=[source_vector(v) for v in sequence(source_morphs[name],len(points),'original shape deltas')]
        delta=[vector(v) for v in sequence(shape['deltas'],len(native),'native shape deltas')]
        error=max(math.dist(p,expected_delta[ids[i]]) for i,p in enumerate(delta));morph_errors[name]=error
        if error>1e-6:raise ValidationError('Native facial delta differs from the source')
    actual_bones={}
    if type(actual['bones']) is not list or not 163<=len(actual['bones'])<=180:raise ValidationError('Native hierarchy exceeds the admitted family')
    for bone in actual['bones']:
        closed(bone,{'name','parent','position'},'native hierarchy bone');name=bone['name']
        if type(name) is not str or name in actual_bones or not name or (bone['parent'] is not None and type(bone['parent']) is not str):
            raise ValidationError('Native hierarchy has missing/duplicate identities')
        actual_bones[name]=bone;vector(bone['position'])
    source_names=set();bone_error=0.
    for bone in sequence(reference['bones'],163,'original bone hierarchy'):
        closed(bone,{'name','parent','world'},'original hierarchy bone');name=bone['name']
        if type(name) is not str or name in source_names or name not in actual_bones:raise ValidationError('Original/native hierarchy bone missing or duplicated')
        source_names.add(name);native_bone=actual_bones[name]
        if bone['parent'] is not None and bone['parent']!=native_bone['parent']:raise ValidationError('Native family bone parent differs')
        matrix=[number(v) for v in sequence(bone['world'],16,'original bone matrix')]
        error=math.dist(source_vector([matrix[3],matrix[7],matrix[11]]),vector(native_bone['position']));bone_error=max(bone_error,error)
        if error>2e-6:raise ValidationError('Native family bind head differs from source')
    if source_names!=set(bones):raise ValidationError('Native skin family differs from the original bone set')
    material=closed(actual['material'],{'shader','color','smoothness','metallic','textures','property_block','mode'},'material')
    spec=SkinMaterialSpec.from_dict(reference['material_spec']);color=vector(material['color'],'rgba')
    if (material['shader']!='Standard' or material['textures'] is not False or material['property_block'] is not False
            or number(material['mode'])!=0 or number(material['metallic'])!=0
            or abs(number(material['smoothness'])-(1-spec.roughness))>1e-6
            or any(abs(a-b)>1e-6 for a,b in zip(color,spec.linear_rgba))):
        raise ValidationError('Native opaque material differs from the reviewed saved source')
    topology=UnityQuadSource(master_sha256,actual['native_mesh_sha256'],len(points),ids,
        tuple(tuple(sequence(q,4,'original quad')) for q in sequence(reference['quads'],13378,'original quads')),tuple(bones),tuple(s['name'] for s in shapes))
    evidence={'policy':'UCC_UNITY_NATIVE_BIND_PARITY_V1','request_sha256':request_sha256,'master_sha256':master_sha256,
        'native_mesh_sha256':actual['native_mesh_sha256'],'topology_sha256':topology.sha256,'source_vertices':len(points),
        'native_vertices':len(native),'triangles':len(native_triangles),'bones':len(bones),'morphs':len(shapes),
        'source_correspondence_complete':True,'exact_triangle_winding_and_multiplicity':True,'exact_uv_corners':True,
        'positive_influences_retained':True,'maximum_weight_error':weight_error,'maximum_bind_position_error_m':position_error,
        'maximum_evaluated_rest_error_m':rest_error,'maximum_bone_head_error_m':bone_error,'maximum_morph_error_m':max(morph_errors.values()),
        'runtime_verified':False,'visual_quality_approved':False}
    return topology,evidence


def compare_saved_bind(stage: dict,reopened: dict) -> None:
    """Evaluated rest output has its own source gate; saved native data is exact."""
    excluded={'mode','baked','runtime_component_present'}
    if ({k:v for k,v in stage.items() if k not in excluded}!={k:v for k,v in reopened.items() if k not in excluded}
            or reopened.get('runtime_component_present') is not True):
        raise ValidationError('Saved Unity native data changed or runtime component is absent')
