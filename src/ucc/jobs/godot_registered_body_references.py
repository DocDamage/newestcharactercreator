"""Bounded source-bound body300 reference conversion and readback checks."""
from hashlib import sha256
import math
import os
from pathlib import Path
import struct
from .target_action_context import Budget,protected
from .godot_registered_runtime_files import hash_file,read_metadata
from .godot_candidate_inputs import identity
from .target_action_storage import ancestry
from .godot_native_target_evidence import compare_outputs,verify_uv_readback
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.core.target_action_format import checked_sha
from ucc.export.godot_registered_body_runtime import (FRAMES,VERTICES,OUTPUT_BYTES,STATUS,FALSE_FLAGS)


def verify_import_configuration(folder:Path,phase:str,budget:Budget)->dict:
    if phase not in {'PRE_REIMPORT','POST_REIMPORT'}:raise ValidationError("Unknown import configuration phase")
    name='configured_import.json' if phase=='PRE_REIMPORT' else 'import_configuration.json'
    value,_,digest=read_metadata(folder/name,256*1024,budget)
    if (set(value)!={'schema_version','phase','animation_fps','optimizer_enabled','compression_enabled','import_settings_sha256'}
            or type(value['schema_version']) is not int or value['schema_version']!=1 or value['phase']!=phase
            or type(value['animation_fps']) not in (int,float) or value['animation_fps']!=30.
            or value['optimizer_enabled'] is not False or value['compression_enabled'] is not False):
        raise ValidationError("Actual typed animation import settings differ")
    checked_sha(value['import_settings_sha256'])
    from .godot_registered_runtime_files import read_bytes
    read_bytes(folder/'character.glb.import',1024*1024,budget,expected_sha256=value['import_settings_sha256'])
    return dict(report_sha256=digest,**value)


def convert_reference(source:Path,target:Path,expected_sha256:str,*,normal:bool,budget:Budget,
                      frames:int=FRAMES,vertices:int=VERTICES)->dict:
    """Synthetic tests may use smaller counts; production supplies fixed profile."""
    if type(frames) is not int or type(vertices) is not int or not 1<=frames<=FRAMES or not 1<=vertices<=VERTICES:
        raise ValidationError("Unbounded body reference conversion profile")
    maximum=frames*vertices*12
    if hash_file(source,maximum,budget)!=(expected_sha256,maximum):
        raise ValidationError("Body300 reference SHA/length differs from actual source receipt")
    initial=identity(protected(source));digest=sha256();emitted=sha256();total=0
    target=protected(target);authority=ancestry((target.parent,))
    with source.open('rb') as reader,target.open('xb') as writer:
        opened=os.fstat(writer.fileno())
        owned=(opened.st_dev,opened.st_ino)
        def guard_target()->None:
            budget.check()
            if identity(protected(target))[:2]!=owned:
                raise ProjectStorageError("Owned converted reference file replaced")
            current=os.fstat(writer.fileno())
            if (current.st_dev,current.st_ino)!=owned:
                raise ProjectStorageError("Converted reference descriptor changed")
            for path,stamp in authority.items():
                if identity(protected(path))!=stamp:
                    raise ProjectStorageError("Converted reference ancestry changed")
        for frame in range(frames):
            guard_target();raw=reader.read(vertices*12)
            if len(raw)!=vertices*12:raise ValidationError("Incomplete source reference frame")
            digest.update(raw);total+=len(raw)
            output=bytearray()
            for point in struct.iter_unpack('<3f',raw):
                if (any(not math.isfinite(v) or abs(v)>100 for v in point)
                        or normal and abs(sum(v*v for v in point)-1)>2e-5):
                    raise ValidationError("Invalid source reference positions/normals")
                output.extend(struct.pack('<4f',*point,0. if normal else 1.))
            writer.write(output);emitted.update(output);guard_target()
        if reader.read(1):raise ValidationError("Trailing source reference records")
        writer.flush()
        os.fsync(writer.fileno())
        guard_target()
    if identity(protected(source))!=initial or digest.hexdigest()!=expected_sha256 or total!=maximum:
        raise ProjectStorageError("Source references changed during conversion")
    digest,size=hash_file(target,frames*vertices*16,budget)
    if identity(protected(target))[:2]!=owned or (digest,size)!=(emitted.hexdigest(),frames*vertices*16):
        raise ProjectStorageError("Converted reference differs from owned emitted bytes")
    for path,stamp in authority.items():
        if identity(protected(path))!=stamp:raise ProjectStorageError("Converted reference ancestry changed after close")
    return dict(sha256=digest,bytes=size)


def verify_body_outputs(folder:Path,execution_sha256:str,spec_sha256:str,budget:Budget,*,input_hashes:dict[str,str])->dict:
    report,_,report_sha=read_metadata(folder/'measurement.json',2*1024*1024,budget)
    keys={'status','schema_version','execution_sha256','spec_sha256','frames','source_vertices',
          'imported_vertices','bones','canonical_morphs','godot_version','rendering_device',
          'gpu_correction_applied','uv_readback_sha256','files'}|FALSE_FLAGS
    version=report.get('godot_version')
    if (set(report)!=keys or report['status']!=STATUS or type(report['schema_version']) is not int or report['schema_version']!=1
            or report['execution_sha256']!=execution_sha256 or report['spec_sha256']!=spec_sha256
            or type(report['frames']) is not list or any(type(value) is not int for value in report['frames'])
            or report['frames']!=list(range(1,301)) or report['source_vertices']!=VERTICES
            or report['imported_vertices']!=14517 or report['bones']!=163 or report['canonical_morphs']!=12
            or report['gpu_correction_applied'] is not True or any(report[k] is not False for k in FALSE_FLAGS)
            or type(version) is not dict or any(type(version.get(k)) is not int or version[k]!=v for k,v in [('major',4),('minor',7),('patch',1)])
            or type(report['rendering_device']) is not str or not report['rendering_device'].strip()):
        raise ValidationError("Incomplete body300 actual engine/profile evidence")
    output_names={'actual_corrected_world.f32','actual_normals_vec4.f32'}
    if type(report['files']) is not dict or set(report['files'])!=output_names:
        raise ValidationError("Body300 output file closure changed")
    identities={}
    for name,row in report['files'].items():
        if type(row) is not dict or set(row)!={'sha256','bytes'} or row['bytes']!=OUTPUT_BYTES or hash_file(folder/name,OUTPUT_BYTES,budget)!=(row['sha256'],OUTPUT_BYTES):
            raise ValidationError("Body300 GPU readback changed")
        identities[name]=identity(folder/name)
    readback=compare_outputs(folder,samples=FRAMES,vertices=VERTICES,check=budget.check)
    uv=verify_uv_readback(folder,report['uv_readback_sha256'],budget.check,input_hashes=input_hashes)
    for name,row in report['files'].items():
        if identity(protected(folder/name))!=identities[name] or hash_file(folder/name,OUTPUT_BYTES,budget)!=(row['sha256'],OUTPUT_BYTES):
            raise ProjectStorageError("Body300 outputs changed during independent comparison")
    uv_sizes={'imported_uv.f32':14517*8,'imported_uv_source_ids.u32':14517*4,'imported_uv_triangles.u32':26756*3*4}
    output_records=report['files']|{name:dict(sha256=digest,bytes=uv_sizes[name]) for name,digest in report['uv_readback_sha256'].items()}
    return dict(status=STATUS,measurement_sha256=report_sha,output_files=output_records,
        readback=readback,uv_readback=uv,
        **{name:False for name in FALSE_FLAGS})
