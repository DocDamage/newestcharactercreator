"""Decode admitted real RGBA frames and verify exact atlas placement."""
from pathlib import Path
from hashlib import sha256
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.sprite_render import POLICY,SpriteRenderRequest,canonical
from ucc.jobs.private_render_evidence import png_measurements
from ucc.jobs.godot_candidate_inputs import regular_file,read_json
from ucc.jobs.master_preview import _digest


def checked_sprite_evidence(folder: Path,request: SpriteRenderRequest,bindings: dict) -> tuple[dict,dict]:
    report_path=regular_file(folder/'sprite_stage.json',folder,4*1024*1024)
    if _digest(report_path)!=bindings['stage_sha256']:raise ValidationError('Sprite render report changed')
    report=read_json(report_path,4*1024*1024);proof=read_json(regular_file(folder/'sprite_verification.json',folder,4*1024*1024),4*1024*1024)
    fields={'schema_version','policy','recipe_sha256','master_sha256','scene_sha256','source_state_sha256','shader_sha256','configuration','pivot','frames','blender_version','blender_build_hash','animation_clips','visual_quality_approved'}
    if (set(report)!=fields or type(report['schema_version']) is not int or report['schema_version']!=1 or report['policy']!=POLICY
            or report['animation_clips'] is not False or report['visual_quality_approved'] is not False
            or any(report[k]!=bindings[k] for k in ('master_sha256','recipe_sha256','scene_sha256'))
            or any(not is_sha256(report[k]) for k in ('source_state_sha256','shader_sha256'))
            or type(report['blender_version']) is not str or not report['blender_version'].startswith('5.3.')
            or type(report['blender_build_hash']) is not str or not 7<=len(report['blender_build_hash'])<=64):
        raise ValidationError('Sprite stage lacks complete source-bound evidence')
    expected={'schema_version':1,'policy':POLICY,'bindings':bindings,'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':report['source_state_sha256'],'shader_sha256':report['shader_sha256'],
        'frame_count':request.settings.directions,'exact_rerender_pixels':True,'visual_quality_approved':False}
    if canonical(proof)!=canonical(expected):raise ValidationError('Sprite images lack independent saved-scene re-render evidence')
    size=request.settings.resolution;cfg=report['configuration']
    if (type(cfg) is not dict or cfg.get('engine')!='CYCLES' or cfg.get('device')!='CPU' or cfg.get('samples')!=32
            or cfg.get('resolution')!=[size,size,100] or cfg.get('transparent') is not True
            or cfg.get('format')!=['PNG','RGBA','8',15] or cfg.get('frame')!=1):
        raise ValidationError('Sprite output has unsupported renderer, canvas or alpha settings')
    pivot=report['pivot']
    if type(pivot) is not list or len(pivot)!=2 or any(type(v) not in (int,float) or not 0<=v<=1 for v in pivot):raise ValidationError('Invalid sprite origin')
    rows=report['frames']
    if type(rows) is not list or len(rows)!=request.settings.directions:raise ValidationError('Incomplete sprite direction set')
    from PIL import Image
    hashes=[]
    for i,(row,yaw) in enumerate(zip(rows,request.settings.angles())):
        if type(row) is not dict or set(row)!={'file','direction_index','yaw_deg','sha256','rgba_sha256','opaque_pixels','opaque_bounds'} or row['file']!=f'sprite-{i:02d}.png' or type(row['direction_index']) is not int or row['direction_index']!=i or row['yaw_deg']!=yaw:
            raise ValidationError('Sprite direction or filename differs from the camera request')
        path=regular_file(folder/row['file'],folder,2*1024*1024)
        if _digest(path)!=row['sha256']:raise ValidationError('Sprite image changed after rendering')
        observed=png_measurements(path.read_bytes(),include_pixel_hash=True,expected_size=(size,size))
        if observed!={k:row[k] for k in ('rgba_sha256','opaque_pixels','opaque_bounds')}:raise ValidationError('Sprite pixel evidence differs from the real PNG')
        with Image.open(path) as im:
            alpha=im.getchannel('A');values=alpha.tobytes()
            border=values[:size]+values[-size:]+values[::size]+values[size-1::size]
            if any(border) or values.count(0)<size*size//5:raise ValidationError('Sprite canvas must retain a transparent margin and background')
        hashes.append(observed['rgba_sha256'])
    if len(set(hashes))!=len(hashes):raise ValidationError('Sprite directions reuse identical rendered pixels')
    return report,proof


def checked_atlas(folder: Path,frame_folder: Path,request: SpriteRenderRequest,report: dict) -> dict:
    from PIL import Image
    record=read_json(regular_file(folder/'sprite_atlas.json',folder,4*1024*1024),4*1024*1024)
    n=request.settings.resolution
    if (record.get('frame_count')!=request.settings.directions or record.get('frame_resolution')!={'width':n,'height':n}
            or record.get('angle_degrees')!=list(request.settings.angles()) or len(record.get('frames',[]))!=request.settings.directions
            or len(record.get('sheets',[]))!=1 or record['sheets'][0]['file']!='sprite_sheet_000.png'):
        raise ValidationError('Sprite atlas metadata differs from the admitted direction sample')
    sheet=regular_file(folder/'sprite_sheet_000.png',folder,16*1024*1024)
    with Image.open(sheet) as image:
        if image.mode!='RGBA' or image.size!=(n*request.settings.directions,n):raise ValidationError('Sprite atlas lost RGBA or canvas dimensions')
        for i,row in enumerate(record['frames']):
            if (row.get('clip')!='neutral' or row.get('direction_index')!=i or row.get('frame_index')!=0
                    or row.get('rect')!={'x':i*n,'y':0,'width':n,'height':n} or row.get('source_sha256')!=report['frames'][i]['sha256']
                    or row.get('source_frame')!=f'neutral/dir-{i:02d}/frame-0000.png'
                    or row.get('pivot')!={'x':round(report['pivot'][0]*n,4),'y':round(report['pivot'][1]*n,4)}):
                raise ValidationError('Sprite atlas frame lineage or rectangle changed')
            with Image.open(frame_folder/f'sprite-{i:02d}.png') as original:
                if image.crop((i*n,0,(i+1)*n,n)).tobytes()!=original.tobytes():raise ValidationError('Sprite atlas pixels differ from the actual rendered frame')
    return record
