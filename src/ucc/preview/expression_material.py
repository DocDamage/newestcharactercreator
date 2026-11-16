"""Bounded immutable corner-expanded PBR buffers over verified V1 geometry."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import math,struct
from ucc.core.errors import ValidationError
from ucc.core.expression_material import POLICY,BASE_FIELDS
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.expression_library import canonical_digest
from ucc.jobs.native_evidence import bound_file
from .expression_cache import read_json
from .motion_cache import MotionCache,unpack_frame

MAX_BYTES=32*1024*1024


@dataclass(frozen=True,slots=True)
class MaterialExpressionCache:
    geometry: MotionCache
    vertices: tuple[bytes,...]
    normals: tuple[bytes,...]
    indices: bytes
    material: SkinMaterialSpec
    hips: tuple[tuple[float,float,float],...]
    world_matrix: tuple[float,...]
    radius: float
    fps: float
    source_first_frame: int=1
    surface_review: None=None

    @property
    def frame_count(self):return self.geometry.frame_count

    @property
    def vertex_count(self):return self.geometry.triangle_count*3

    @property
    def triangle_count(self):return self.geometry.triangle_count

    def frame(self,index: int) -> tuple[bytes,bytes]:
        self._check(index);return self.vertices[index],self.indices

    def frame_normals(self,index: int) -> bytes:
        self._check(index);return self.normals[index]

    def _check(self,index: int) -> None:
        if type(index) is not int or not 0<=index<self.frame_count:raise ValidationError('Material expression frame is outside the verified clip')


def read_material_expression(folder: Path,geometry: MotionCache,options: dict,proof: dict,report: dict,
        *,cancel_check=lambda:None) -> MaterialExpressionCache:
    expected={'schema_version':1,'policy':POLICY,'bindings':options,'verified_reopen':True,
        'reference_frames':25,'saved_frames':25,'normal_frames':25,'exact_neutral_endpoints':True,
        'visual_quality_approved':False,'engine_import_verified':False}
    if canonical_digest(proof)!=canonical_digest(expected):raise ValidationError('Material expression lacks independent full-frame normal verification')
    spec=SkinMaterialSpec.from_dict(options['owned_material_spec']);base={k:options[k] for k in BASE_FIELDS}
    manifest=read_json(folder/'expression_normals.json',options['normals_manifest_sha256'],4*1024*1024)
    fields={'schema_version','policy','bindings','material_spec','coordinate_space','frame_count','normals_per_frame','frames','geometry','visual_quality_approved','engine_import_verified'}
    if (set(manifest)!=fields or type(manifest['schema_version']) is not int or manifest['schema_version']!=1
            or manifest['policy']!=POLICY or manifest['bindings']!=base or manifest['material_spec']!=spec.to_dict()
            or manifest['coordinate_space']!='BLENDER_LOCAL_Z_UP' or type(manifest['frame_count']) is not int or manifest['frame_count']!=25
            or geometry.frame_count!=25 or geometry.vertex_count!=13380 or geometry.triangle_count!=26756
            or type(manifest['normals_per_frame']) is not int or manifest['normals_per_frame']!=80268
            or type(manifest['frames']) is not list or len(manifest['frames'])!=25
            or manifest['visual_quality_approved'] is not False or manifest['engine_import_verified'] is not False):
        raise ValidationError('Material normal manifest differs from its complete saved source profile')
    path=bound_file(folder,manifest['geometry'],'expression_normals.bin',MAX_BYTES,cancel_check=cancel_check)
    packed=path.read_bytes()
    if sha256(packed).hexdigest()!=options['normals_sha256'] or packed[:8]!=b'UCCNRM1\0':raise ValidationError('Material normals changed or have an invalid header')
    vertices=[];normals=[];offset=8;framebytes=80268*12
    if framebytes*25*2>64*1024*1024:raise ValidationError('Material expression GPU buffer budget exceeded')
    for index,row in enumerate(manifest['frames']):
        cancel_check();frame=index+1;original=report['frames'][index]
        if (type(row) is not dict or set(row)!={'frame','offset','compressed_bytes','normal_sha256','triangles_sha256','local_vertices_sha256'}
                or type(row['frame']) is not int or row['frame']!=frame or type(row['offset']) is not int or row['offset']!=offset
                or type(row['compressed_bytes']) is not int or not 0<row['compressed_bytes']<=len(packed)-offset
                or row['triangles_sha256']!=original['triangles_sha256'] or row['local_vertices_sha256']!=original['local_vertices_sha256']):
            raise ValidationError('Material normals do not match exact frame order/geometry or chunk bounds')
        size=row['compressed_bytes'];raw=unpack_frame(packed[offset:offset+size],framebytes)
        if sha256(raw).hexdigest()!=row['normal_sha256']:raise ValidationError('Material normal frame SHA differs')
        for n in struct.iter_unpack('<3f',raw):
            if any(not math.isfinite(v) for v in n) or abs(math.sqrt(sum(v*v for v in n))-1.)>1e-4:
                raise ValidationError('Material expression normals must be finite and unit length')
        vb,ib=geometry.frame(index)
        # One vertex per corner retains hard edges and split normals without
        # changing or replacing the original verified geometry/indices cache.
        expanded=b''.join(vb[i[0]*12:(i[0]+1)*12] for i in struct.iter_unpack('<I',ib))
        if len(expanded)!=framebytes:raise ValidationError('Material corner expansion lost complete geometry')
        vertices.append(expanded);normals.append(raw);offset+=size
    if offset!=len(packed) or normals[0]!=normals[-1]:raise ValidationError('Material normal stream has trailing data or nonneutral endpoints')
    indices=struct.pack('<'+'I'*80268,*range(80268))
    return MaterialExpressionCache(geometry,tuple(vertices),tuple(normals),indices,spec,geometry.hips,
        geometry.world_matrix,geometry.radius,geometry.fps,geometry.source_first_frame)
