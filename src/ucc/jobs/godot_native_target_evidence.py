"""Independent bounded readback/pixel verification for actual native target jobs."""
from array import array
from contextlib import ExitStack
from hashlib import sha256
import math
from pathlib import Path
import struct
from typing import Callable

from ucc.core.errors import ValidationError
from ucc.export.godot_native_samples import COUNT,VERTICES,REFERENCE_BYTES
from ucc.export.godot_surface_uv import read_glb_uvs,glb_corner_reference,verify_corner_uvs
from .godot_candidate_inputs import read_json,regular_file
from .private_render_evidence import png_measurements
from .master_preview import _digest
from ucc.export.godot_candidate_contract import _hash


def verify_uv_readback(folder: Path,hashes: dict,check: Callable[[],None],*,input_hashes:dict|None=None) -> dict:
    required={'bind_positions.bin','face_vertices.u32','face_ranges.u32','character.glb'}
    if input_hashes is not None and (type(input_hashes) is not dict or not required<=set(input_hashes)
            or any(not _hash(input_hashes[name]) for name in required)):
        raise ValidationError('Source UV readback requires all four exact input SHA bindings')
    sizes={'imported_uv.f32':14517*8,'imported_uv_source_ids.u32':14517*4,'imported_uv_triangles.u32':26756*3*4}
    if type(hashes) is not dict or set(hashes)!=set(sizes):raise ValidationError('Incomplete imported UV readback closure')
    data={}
    for name,size in sizes.items():
        check();path=regular_file(folder/name,folder,size)
        with path.open('rb') as stream:data[name]=stream.read(size+1)
        if len(data[name])!=size or sha256(data[name]).hexdigest()!=hashes[name]:
            raise ValidationError('Imported UV readback changed or is incomplete')
    inputs={}
    for name,size in {'bind_positions.bin':13380*12,'face_vertices.u32':53512*4,'face_ranges.u32':13378*8}.items():
        check();path=regular_file(folder/name,folder,size)
        with path.open('rb') as stream:raw=stream.read(size+1)
        if len(raw)!=size or input_hashes is not None and sha256(raw).hexdigest()!=input_hashes.get(name):
            raise ValidationError('Source UV topology input differs from captured source bytes')
        inputs[name]=raw
    bind=list(struct.iter_unpack('<3f',inputs['bind_positions.bin']))
    vertices=[row[0] for row in struct.iter_unpack('<I',inputs['face_vertices.u32'])]
    polygons=[tuple(vertices[start:start+count]) for start,count in struct.iter_unpack('<2I',inputs['face_ranges.u32'])]
    ids,uvs,triangles=read_glb_uvs(folder/'character.glb',bind,
        expected_sha256=None if input_hashes is None else input_hashes.get('character.glb'))
    reference=glb_corner_reference(polygons,ids,uvs,triangles,check=check)
    result=verify_corner_uvs(polygons,reference,[row[0] for row in struct.iter_unpack('<I',data['imported_uv_source_ids.u32'])],
        list(struct.iter_unpack('<2f',data['imported_uv.f32'])),[row[0] for row in struct.iter_unpack('<I',data['imported_uv_triangles.u32'])],check=check)
    return {**result,'reference':'ADMITTED_GLB_SOURCE_CORNERS','material_appearance_verified':False}


def compare_outputs(folder: Path,*,samples: int,vertices: int,check: Callable[[],None]) -> dict:
    if type(samples) is not int or type(vertices) is not int or not 1<=samples<=COUNT or not 1<=vertices<=VERTICES:
        raise ValidationError('Unbounded native target comparison profile')
    names=('actual_corrected_world.f32','expected_vec4.f32','actual_normals_vec4.f32','expected_normals_vec4.f32')
    expected_bytes=samples*vertices*16
    paths=[regular_file(folder/name,folder,expected_bytes) for name in names]
    if any(p.stat().st_size!=expected_bytes for p in paths):raise ValidationError('Incomplete native target readback')
    maximum_position=0.;maximum_vector=0.;minimum_cosine=1.;limit=math.cos(math.radians(.1))
    with ExitStack() as opened:
        streams=[opened.enter_context(p.open('rb')) for p in paths]
        for sample in range(samples):
            check();data=[stream.read(vertices*16) for stream in streams]
            if any(len(block)!=vertices*16 for block in data):
                raise ValidationError('Incomplete native target frame readback')
            rows=[struct.iter_unpack('<4f',block) for block in data]
            for actual,expected,normal,reference in zip(*rows):
                if (any(not math.isfinite(v) for row in (actual,expected,normal,reference) for v in row)
                        or actual[3]!=1. or expected[3]!=1. or normal[3]!=0. or reference[3]!=0.):
                    raise ValidationError('Nonfinite or invalid homogeneous native target readback')
                distance=sum((actual[i]-expected[i])**2 for i in range(3))
                vector=sum((normal[i]-reference[i])**2 for i in range(3))
                a=sum(v*v for v in normal[:3]);b=sum(v*v for v in reference[:3])
                if abs(a-1)>2e-5 or abs(b-1)>2e-5:raise ValidationError('Nonunit native target/source normal')
                cosine=sum(normal[i]*reference[i] for i in range(3))/math.sqrt(a*b)
                if distance>1e-10 or vector>4e-6 or cosine<limit:
                    raise ValidationError('Independent native target geometry/normal readback exceeds fixed limits')
                maximum_position=max(maximum_position,distance);maximum_vector=max(maximum_vector,vector);minimum_cosine=min(minimum_cosine,cosine)
        check()
        if any(stream.read(1) for stream in streams):raise ValidationError('Trailing native target readback records')
    return {'samples':samples,'vertices':vertices,'maximum_position_error_m':math.sqrt(maximum_position),
        'maximum_normal_vector_error':math.sqrt(maximum_vector),'maximum_normal_angle_degrees':math.degrees(math.acos(max(-1.,min(1.,minimum_cosine))))}


def verify_native_target_evidence(folder: Path,source_report: dict,*,check: Callable[[],None]) -> dict:
    report=read_json(regular_file(folder/'measurement.json',folder,8*1024*1024),8*1024*1024)
    version=report.get('godot_version')
    if (report.get('status')!='ACTUAL_IMPORTED_GODOT_RUNTIME_CS_AND_FACE_SAMPLES_VERIFIED'
            or type(report.get('samples')) is not list or len(report['samples'])!=COUNT
            or report.get('source_vertices')!=VERTICES or report.get('imported_vertices')!=14517
            or report.get('bones')!=163 or report.get('canonical_morphs')!=12
            or report.get('GPU_runtime_correction_applied') is not True or report.get('runtime_corrected_geometry_rendered') is not True
            or report.get('uv_runtime_meshes_checked')!=COUNT
            or type(version) is not dict or version.get('major')!=4 or version.get('minor')!=7
            or any(report.get(k) is not False for k in ('engine_import_verified','visual_quality_approved','material_appearance_verified',
                'vertex_shader_positions_directly_verified','shipping_runtime_implemented'))):
        raise ValidationError('Native target evidence lacks complete actual supported rig/renderer coverage')
    uv=verify_uv_readback(folder,report.get('uv_readback_sha256'),check)
    hashes=set()
    for index,row in enumerate(report['samples']):
        check()
        if (type(row) is not dict or row.get('sample')!=index or row.get('case')!=source_report['cases'][index]
                or type(row.get('max_world_error_m')) not in (int,float) or not math.isfinite(row['max_world_error_m'])
                or not 0<=row['max_world_error_m']<=1e-5):raise ValidationError('Native target sample evidence is incomplete or outside fixed limits')
        path=regular_file(folder/f'runtime_{index:04d}.png',folder,2*1024*1024)
        if _digest(path,None)!=row.get('png_sha256'):raise ValidationError('Native target image hash changed')
        decoded=png_measurements(path.read_bytes(),include_pixel_hash=True)
        if decoded['rgba_sha256']!=row.get('rgba_sha256'):raise ValidationError('Native target pixels differ from the draw receipt')
        hashes.add(decoded['rgba_sha256'])
    if len(hashes)!=report.get('distinct_rendered_frames'):raise ValidationError('Native target distinct-draw coverage differs')
    values=compare_outputs(folder,samples=COUNT,vertices=VERTICES,check=check)
    return {'status':'INDEPENDENT_NATIVE_TARGET_GEOMETRY_NORMALS_AND_CLAY_VERIFIED','readback':values,
        'uv_readback':uv,'runtime_mesh_uvs_checked':COUNT,
        'distinct_pixel_hashes':len(hashes),'actual_positions_sha256':_digest(folder/'actual_corrected_world.f32',None),
        'actual_normals_sha256':_digest(folder/'actual_normals_vec4.f32',None),'measurement_sha256':_digest(folder/'measurement.json',None),
        'engine_import_verified':False,'visual_quality_approved':False,'actual_materials_verified':False,'distribution_license_review_complete':False}
