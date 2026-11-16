"""Original-source diagnostic coverage and independent native GPU comparisons."""
from hashlib import sha256
import math,struct
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256,validate_expression_parameters
from ucc.animations.native_math import inverse
from .unity_bind_evidence import closed,sequence,number
from .unity_runtime_source import POLICY,CASES,VERTICES,VECTOR_BYTES,BINARY_BYTES
from .unity_skin_precision import MAX_DEFORMATION_ERROR_M

NATIVE_VERTICES=14517
RECORD_BYTES=NATIVE_VERTICES*36
NATIVE_BINARY_BYTES=CASES*2*RECORD_BYTES
NORMAL_LIMIT_DEG=.5


def checked_plan(manifest: dict,*,request_sha256: str,master_sha256: str,bind_reference_sha256: str,
        native_mesh_sha256: str,topology_sha256: str,bone_names: tuple[str,...],shape_names: tuple[str,...]) -> dict:
    closed(manifest,{'schema_version','policy','request_sha256','master_sha256','recipe_sha256','bind_reference_sha256',
        'blender_version','blender_build','expression_parameters','coordinate_space','vector_format','source_vertices','case_count',
        'cases','binary_sha256','binary_bytes','nonmaterial_state_sha256','shader_sha256','original_state_preserved',
        'animation_clips_created','runtime_verified','visual_quality_approved'},'runtime source manifest')
    exact={'schema_version':1,'policy':POLICY,'request_sha256':request_sha256,'master_sha256':master_sha256,
        'bind_reference_sha256':bind_reference_sha256,'blender_version':'5.3.0','blender_build':'02f0899d78e3',
        'coordinate_space':'BLENDER_WORLD_METRES_Z_UP','vector_format':'FLOAT32_LE_XYZ','source_vertices':VERTICES,'case_count':CASES,
        'binary_bytes':BINARY_BYTES,'original_state_preserved':True,'animation_clips_created':False,'runtime_verified':False,'visual_quality_approved':False}
    for key,value in exact.items():
        if type(manifest[key]) is not type(value) or manifest[key]!=value:raise ValidationError('Runtime source changed its profile, scope or identity: '+key)
    if any(not is_sha256(manifest[k]) for k in ('recipe_sha256','binary_sha256','nonmaterial_state_sha256','shader_sha256')):
        raise ValidationError('Runtime source hashes are incomplete')
    validate_expression_parameters(manifest['expression_parameters'])
    if len(bone_names)!=163 or len(set(bone_names))!=163 or len(shape_names)!=12 or len(set(shape_names))!=12:
        raise ValidationError('Runtime source needs the complete admitted bone/control family')
    names=['neutral',*('bone-'+name for name in bone_names),*('shape-'+name for name in sorted(shape_names)),'saved-expression','neutral-end']
    cases=sequence(manifest['cases'],CASES,'runtime diagnostic cases');plan=[]
    for i,(case,name) in enumerate(zip(cases,names)):
        closed(case,{'name','bone','delta_blender_world','shapes','positions_offset','positions_sha256','normals_offset','normals_sha256'},'runtime source case')
        bone=bone_names[i-1] if 1<=i<=163 else None
        if case['name']!=name or case['bone']!=bone:raise ValidationError('Runtime source case coverage/order differs')
        for key,expected in [('positions_offset',i*VECTOR_BYTES*2),('normals_offset',(i*2+1)*VECTOR_BYTES)]:
            if type(case[key]) is not int or case[key]!=expected:raise ValidationError('Runtime source binary offsets overlap or omit data')
        if not is_sha256(case['positions_sha256']) or not is_sha256(case['normals_sha256']):raise ValidationError('Runtime source vector identity missing')
        delta=[number(v) for v in sequence(case['delta_blender_world'],16,'runtime bone delta')]
        if any(abs(v)>1000 for v in delta) or delta[12:]!=[0.,0.,0.,1.]:raise ValidationError('Runtime bone delta is not a bounded affine transform')
        if bone is None and delta!=[float(r==c) for r in range(4) for c in range(4)]:raise ValidationError('Facial diagnostics cannot alter the rig')
        controls=sequence(case['shapes'],12,'runtime facial control values');seen={}
        for control in controls:
            closed(control,{'name','value'},'runtime facial control');key=control['name'];value=number(control['value'])
            if type(key) is not str or key not in shape_names or key in seen or not 0<=value<=.5:raise ValidationError('Runtime facial control identity/value differs')
            seen[key]=value
        if name!='saved-expression':
            expected={k:(.5 if name=='shape-'+k else 0.) for k in shape_names}
            if seen!=expected:raise ValidationError('Runtime diagnostic changed an unrelated facial control')
        plan.append({k:case[k] for k in ('name','bone','delta_blender_world','shapes')})
    for key in ('positions_sha256','normals_sha256'):
        if cases[0][key]!=cases[-1][key]:raise ValidationError('Runtime source did not return to exact neutral geometry')
    return {'schema_version':1,'policy':'UCC_UNITY_RUNTIME_PLAN_V1','request_sha256':request_sha256,
        'source_manifest_sha256':'','native_mesh_sha256':native_mesh_sha256,'topology_sha256':topology_sha256,'cases':plan}


def verify_source_binary(data: bytes,manifest: dict) -> None:
    if len(data)!=BINARY_BYTES or sha256(data).hexdigest()!=manifest['binary_sha256']:raise ValidationError('Runtime source binary changed or is incomplete')
    for case in manifest['cases']:
        for kind in ('positions','normals'):
            block=data[case[kind+'_offset']:case[kind+'_offset']+VECTOR_BYTES]
            if sha256(block).hexdigest()!=case[kind+'_sha256']:raise ValidationError('Runtime source case vector hash differs')
            for vector in struct.iter_unpack('<fff',block):
                if any(not math.isfinite(v) for v in vector) or (kind=='normals' and abs(math.hypot(*vector)-1)>1e-4):
                    raise ValidationError('Runtime source has a nonfinite or nonunit diagnostic vector')


def compare_gpu_record(native: bytes,positions: bytes,normals: bytes,source_ids: tuple[int,...],world: dict) -> dict:
    if len(native)!=RECORD_BYTES or len(positions)!=VECTOR_BYTES or len(normals)!=VECTOR_BYTES or len(source_ids)!=NATIVE_VERTICES:
        raise ValidationError('Incomplete native/source runtime vector coverage')
    closed(world,{'e'+str(r)+str(c) for r in range(4) for c in range(4)},'native runtime root matrix')
    matrix=[[number(world['e'+str(r)+str(c)]) for c in range(4)] for r in range(4)]
    if matrix[3]!=[0.,0.,0.,1.]:raise ValidationError('Native runtime root is not affine')
    inv=inverse(matrix);maximum_position=0.;maximum_angle=0.
    for i,(bx,by,bz,x,y,z,nx,ny,nz) in enumerate(struct.iter_unpack('<fffffffff',native)):
        start=i*36
        if native[start:start+12]!=native[start+12:start+24]:raise ValidationError('Normal adapter modified actual native position bytes')
        if any(not math.isfinite(v) for v in (bx,by,bz,x,y,z,nx,ny,nz)) or not .9<math.hypot(nx,ny,nz)<1.1:
            raise ValidationError('Native GPU position/normal is nonfinite or nonunit')
        source=source_ids[i]
        if type(source) is not int or not 0<=source<VERTICES:raise ValidationError('Native runtime source point mapping is invalid')
        px,py,pz=struct.unpack_from('<fff',positions,source*12);sx,sy,sz=struct.unpack_from('<fff',normals,source*12)
        wx=matrix[0][0]*x+matrix[0][1]*y+matrix[0][2]*z+matrix[0][3]
        wy=matrix[1][0]*x+matrix[1][1]*y+matrix[1][2]*z+matrix[1][3]
        wz=matrix[2][0]*x+matrix[2][1]*y+matrix[2][2]*z+matrix[2][3]
        error=math.hypot(wx+px,wy-pz,wz+py);maximum_position=max(maximum_position,error)
        if error>MAX_DEFORMATION_ERROR_M:raise ValidationError('Native runtime position exceeds the fixed 50 micrometre source cap')
        ax=inv[0][0]*nx+inv[1][0]*ny+inv[2][0]*nz
        ay=inv[0][1]*nx+inv[1][1]*ny+inv[2][1]*nz
        az=inv[0][2]*nx+inv[1][2]*ny+inv[2][2]*nz
        tx,ty,tz=-sx,sz,-sy;dot=ax*tx+ay*ty+az*tz
        cross=math.hypot(ay*tz-az*ty,az*tx-ax*tz,ax*ty-ay*tx)
        angle=math.degrees(math.atan2(cross,dot));maximum_angle=max(maximum_angle,angle)
        if not math.isfinite(angle) or angle>NORMAL_LIMIT_DEG:raise ValidationError('Native runtime normal exceeds the fixed half-degree source cap')
    return {'vertices':NATIVE_VERTICES,'native_position_bytes_exact':True,'maximum_source_position_error_m':maximum_position,
        'maximum_normal_angle_deg':maximum_angle}
