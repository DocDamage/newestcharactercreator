"""Distinct fitted-cache contract; never presented as original source FK."""
from pathlib import Path
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from ucc.jobs.native_fit_evidence import FLAGS,read_json_record
from .motion_cache import decode_skin_buffers,HASHES,MotionCache
from .surface_review import SurfaceReview

FIT_HASHES=HASHES|{'fit_sha256','fitted_sha256','fit_report_sha256'}


def read_fitted_cache(folder: Path,report: dict,bindings: dict,fitted: dict,baseline: dict,
                      surface: SurfaceReview,*,cancel_check=lambda:None) -> MotionCache:
    fields={'status','bindings','frames_verified','manifest','originals_unchanged'}|FLAGS
    if (type(report) is not dict or set(report)!=fields or report['status']!='REAL_NATIVE_FIT_CACHE_EXPORTED' or
        type(bindings) is not dict or set(bindings)!=FIT_HASHES or any(not is_sha256(v) for v in bindings.values()) or
        report['bindings']!=bindings or type(report['frames_verified']) is not int or report['frames_verified']!=fitted['frame_count'] or
        report['originals_unchanged'] is not True or any(report[k] is not False for k in FLAGS)):
        raise ValidationError('Fitted playback lacks a complete independent saved-scene verification')
    data,_=read_json_record(folder,report['manifest'],'fitted_skin.json',4*1024*1024,cancel_check=cancel_check)
    fields={'schema_version','status','bindings','coordinate_space','world_matrix','fps','frame_count',
            'source_first_frame','vertex_count','triangle_count','frames','geometry'}|FLAGS
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        data['status']!='FITTED_VERIFIED_SKIN_CACHE_V1' or data['bindings']!=bindings or
        data['coordinate_space']!='BLENDER_LOCAL_Z_UP' or data['world_matrix']!=fitted['mesh_world'] or
        any(data[k] is not False for k in FLAGS) or type(data['frame_count']) is not int or
        data['frame_count']!=fitted['frame_count'] or data['frame_count']!=baseline['source_frame_count'] or
        type(data['fps']) not in (int,float) or data['fps']!=fitted['fps'] or data['fps']!=baseline['fps'] or
        type(data['source_first_frame']) is not int or data['source_first_frame']!=fitted['source_first_frame'] or
        data['source_first_frame']!=baseline['source_first_frame']):
        raise ValidationError('Fitted playback provenance, world transform, timing or approval differs')
    rows=fitted['frames']
    if (surface is None or surface.status!='CHECKED' or surface.flagged_frames or
        surface.triangle_hashes!=tuple(r['triangle_sha256'] for r in rows) or
        data['vertex_count']!=rows[0]['vertex_count'] or data['triangle_count']!=rows[0]['triangle_count']):
        raise ValidationError('Fitted playback has unresolved surface review or incompatible topology')
    return decode_skin_buffers(folder,data,skin_hashes=[r['skin_sha256'] for r in rows],
        hip_positions=[r.get('hip_midpoint_world',r['root_world_head']) for r in baseline['full_timeline_frames']],
        triangle_hashes=[r['triangle_sha256'] for r in rows],surface=surface,
        geometry_name='fitted_skin.bin',cancel_check=cancel_check)
