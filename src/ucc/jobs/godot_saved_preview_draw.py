"""Saved D evidence and captured verified PNGs; no engine or private program load."""
import math
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_body_draw import (RegisteredBodyDrawSelection,POLICY,PROFILE,FRAMES)
from ucc.export.godot_registered_body_runtime import FALSE_FLAGS
from ucc.export.godot_saved_preview import CapturedPreviewFrame
from .godot_registered_body_draw_evidence import map_frame,verify_draw_outputs
from .private_render_evidence import png_measurements


def admit_draw_proof(reads,selected,body_selected,body):
    if selected.path.name!='diagnostic_draw_receipt.json':
        raise ValidationError('Select the saved D draw receipt')
    work=selected.path.parent;folder=work/'engine'
    receipt=reads.metadata(selected.path,4*1024*1024,selected.sha256)
    keys={'schema_version','policy','profile','selection_sha256','diagnostic_receipt_sha256','spec_sha256','command','observed'}|FALSE_FLAGS
    if (set(receipt)!=keys or type(receipt['schema_version']) is not int or receipt['schema_version']!=1
            or receipt['policy']!=POLICY or receipt['profile']!=PROFILE
            or receipt['diagnostic_receipt_sha256']!=body_selected.sha256
            or any(receipt[k] is not False for k in FALSE_FLAGS)
            or canonical_bytes(receipt)!=reads.capture(selected.path,4*1024*1024,selected.sha256)):
        raise ValidationError('Saved D receipt does not bind selected C proof/private scope')
    value=reads.metadata(folder/'selection.json',256*1024,receipt['selection_sha256'])
    draw=RegisteredBodyDrawSelection(**{name:value[name] for name in RegisteredBodyDrawSelection.__dataclass_fields__})
    if (canonical_bytes(draw.to_dict())!=reads.capture(folder/'selection.json',256*1024,draw.sha256)
            or draw.diagnostic_receipt_sha256!=body_selected.sha256
            or draw.draw_id==body.execution.execution_id
            or draw.godot_executable_sha256!=body.execution.godot_executable_sha256
            or draw.godot_main_sha256!=body.execution.godot_main_sha256):
        raise ValidationError('Saved D historical selection differs from C lineage')
    spec=reads.metadata(folder/'spec.json',256*1024,receipt['spec_sha256'])
    data={f'frame{frame:03d}_{kind}.f32' for frame in FRAMES for kind in ('positions','normals')}
    data|={'imported_uv.f32','imported_uv_triangles.u32'}
    if (set(spec)!={'schema_version','profile','selection_sha256','diagnostic_receipt_sha256','files'}
            or type(spec['schema_version']) is not int or spec['schema_version']!=1
            or spec['profile']!=PROFILE or spec['selection_sha256']!=draw.sha256
            or spec['diagnostic_receipt_sha256']!=body_selected.sha256
            or type(spec['files']) is not dict or set(spec['files'])!=data|{'project.godot','validate.gd','selection.json'}):
        raise ValidationError('Closed saved D staged resource set changed')
    sizes={f'frame{frame:03d}_{kind}.f32':14517*12 for frame in FRAMES for kind in ('positions','normals')}
    sizes.update({'imported_uv.f32':14517*8,'imported_uv_triangles.u32':26756*12})
    captured={}
    for name,digest in spec['files'].items():
        raw=reads.capture(folder/name,sizes.get(name,256*1024),digest)
        if name in sizes and len(raw)!=sizes[name]:raise ValidationError('Saved D staged array length differs')
        captured[name]=raw
    if captured['selection.json']!=canonical_bytes(draw.to_dict()):
        raise ValidationError('Saved D specification contains another selection')
    names=('imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32')
    source={name:reads.capture(body.directory/name,body.receipt['files'][name]['bytes'],
                              body.receipt['files'][name]['sha256']) for name in names}
    for frame in FRAMES:
        mapped=map_frame(body.frames['actual_corrected_world.f32'][frame],body.frames['actual_normals_vec4.f32'][frame],
            source['imported_uv_source_ids.u32'],source['imported_uv.f32'],source['imported_uv_triangles.u32'],check=reads.budget.check)
        if (captured[f'frame{frame:03d}_positions.f32']!=mapped['positions']
                or captured[f'frame{frame:03d}_normals.f32']!=mapped['normals']
                or captured['imported_uv.f32']!=mapped['uv']
                or captured['imported_uv_triangles.u32']!=mapped['triangles']):
            raise ValidationError('Saved D staged arrays differ from captured C source mapping')
    row=receipt['command'];tail=['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000','--script','res://validate.gd']
    from pathlib import Path
    if (type(row) is not dict or set(row)!={'command','return_code','cancelled','timed_out','elapsed_seconds'}
            or type(row['return_code']) is not int or row['return_code']!=0
            or row['cancelled'] is not False or row['timed_out'] is not False
            or type(row['elapsed_seconds']) not in (int,float) or not math.isfinite(row['elapsed_seconds']) or row['elapsed_seconds']<0
            or type(row['command']) is not list or len(row['command'])!=len(tail)+3
            or any(type(value) is not str or not 0<len(value)<=4096 for value in row['command'])
            or row['command'][1]!='--path' or not Path(row['command'][0]).is_absolute()
            or not Path(row['command'][2]).is_absolute() or row['command'][3:]!=tail
            or row['command'][0]!=body.receipt['commands'][0]['command'][0]
            or reads.metadata(work/'draw/process_outcome.json',256*1024)!=row):
        raise ValidationError('Saved D lacks successful historical selected native outcome')
    for name in ('stdout.log','stderr.log'):reads.record(work/'draw'/name,16*1024*1024)
    observed=verify_draw_outputs(folder,receipt['spec_sha256'],{name:spec['files'][name] for name in data},reads.budget)
    if observed!=receipt['observed']:raise ValidationError('Saved D independent draw evidence differs')
    reads.record(folder/'measurement.json',256*1024,observed['measurement_sha256'])
    for name,row in observed['files'].items():
        reads.record(folder/name,row['bytes'],row['sha256'])
        if reads.records[folder/name][2]!=row['bytes']:raise ValidationError('Saved D output length differs')
    frames=[]
    for observation in observed['observations']:
        frame=observation['frame'];name=f'frame{frame:03d}.png'
        raw=reads.capture(folder/name,2*1024*1024,observed['files'][name]['sha256'])
        decoded=png_measurements(raw,include_pixel_hash=True,expected_size=(512,512))
        if any(decoded[key]!=observation[key] for key in decoded):
            raise ValidationError('Captured PNG differs from independently checked pixels')
        frames.append(CapturedPreviewFrame(frame,raw,decoded['rgba_sha256'],decoded['opaque_pixels'],
            tuple(decoded['opaque_bounds']),observation['max_normal_vector_error']))
    reads.check()
    return draw.draw_id,tuple(frames)
