"""Admit complete animated RGBA sequences and exact 5×5 per-direction atlases."""
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.facial_sprites import POLICY,FacialSpriteRequest
from ucc.core.sprite_render import canonical
from ucc.jobs.godot_candidate_inputs import regular_file,read_json
from ucc.jobs.master_preview import _digest
from ucc.jobs.private_render_evidence import png_measurements


def checked_facial_evidence(folder: Path,request: FacialSpriteRequest,bindings: dict) -> tuple[dict,dict]:
    path=regular_file(folder/'facial_sprite_stage.json',folder,4*1024*1024)
    if _digest(path)!=bindings['stage_sha256']:raise ValidationError('Animated sprite stage changed')
    report=read_json(path,4*1024*1024);proof=read_json(regular_file(folder/'facial_sprite_verification.json',folder,4*1024*1024),4*1024*1024)
    fields={'schema_version','policy','recipe_sha256','master_sha256','clip_sha256','scene_sha256','source_state_sha256','shader_sha256',
        'configuration','original_scene','pivot','frames','timeline','blender_version','blender_build_hash','animation_clips','visual_quality_approved'}
    if (type(report) is not dict or set(report)!=fields or type(report['schema_version']) is not int or report['schema_version']!=1
            or report['policy']!=POLICY or report['animation_clips'] is not True or report['visual_quality_approved'] is not False
            or any(report[k]!=bindings[k] for k in ('recipe_sha256','master_sha256','clip_sha256','scene_sha256'))
            or any(not is_sha256(report[k]) for k in ('source_state_sha256','shader_sha256'))
            or canonical(report['timeline'])!=canonical(request.clip['timeline'])
            or type(report['original_scene']) is not str or not report['original_scene']
            or type(report['blender_version']) is not str or not report['blender_version'].startswith('5.3.')
            or type(report['blender_build_hash']) is not str or not 7<=len(report['blender_build_hash'])<=64):
        raise ValidationError('Animated sprite stage lacks complete source/clip/timeline evidence')
    settings=request.review.settings;n=settings.resolution;count=25*settings.directions
    expected={'schema_version':1,'policy':POLICY,'bindings':bindings,'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':report['source_state_sha256'],'shader_sha256':report['shader_sha256'],'reference_frames':count,'saved_frames':count,
        'exact_neutral_endpoints':True,'exact_rerender_pixels':True,'visual_quality_approved':False}
    if canonical(proof)!=canonical(expected):raise ValidationError('Animated sprite proof lacks every original-source and saved frame')
    cfg=report['configuration']
    if (type(cfg) is not dict or cfg.get('engine')!='CYCLES' or cfg.get('device')!='CPU' or cfg.get('samples')!=32
            or cfg.get('resolution')!=[n,n,100] or cfg.get('transparent') is not True or cfg.get('frame')!=1
            or cfg.get('format')!=['PNG','RGBA','8',15]):raise ValidationError('Animated sprite canvas/render policy differs')
    pivot=report['pivot']
    if type(pivot) is not list or len(pivot)!=2 or any(type(v) not in (int,float) or not 0<=v<=1 for v in pivot):raise ValidationError('Invalid animated sprite pivot')
    rows=report['frames']
    if type(rows) is not list or len(rows)!=count:raise ValidationError('Animated sprite coverage is incomplete')
    from PIL import Image
    motion=False
    for direction,yaw in enumerate(settings.angles()):
        sequence=rows[direction*25:(direction+1)*25]
        for frame,row in enumerate(sequence,1):
            if (type(row) is not dict or set(row)!={'file','direction_index','yaw_deg','frame','geometry','normals_sha256','sha256','rgba_sha256','opaque_pixels','opaque_bounds'}
                    or row['file']!=f'facial-{direction:02d}-{frame:02d}.png' or type(row['frame']) is not int or row['frame']!=frame
                    or type(row['direction_index']) is not int or row['direction_index']!=direction or row['yaw_deg']!=yaw
                    or any(not is_sha256(row[k]) for k in ('normals_sha256','sha256','rgba_sha256'))):raise ValidationError('Animated frame identity/order differs')
            geometry=row['geometry'];hash_fields={'full_sha256','visible_sha256','fixed_state_sha256','local_vertices_sha256','triangles_sha256','skin_sha256','raw_sha256'}
            if (type(geometry) is not dict or set(geometry)!=hash_fields|{'frame','maximum_displacement','moved_vertices_over_1um'}
                    or type(geometry['frame']) is not int or geometry['frame']!=frame or any(not is_sha256(geometry[k]) for k in hash_fields)
                    or type(geometry['maximum_displacement']) not in (int,float) or not 0<=geometry['maximum_displacement']<=.03
                    or type(geometry['moved_vertices_over_1um']) is not int or not 0<=geometry['moved_vertices_over_1um']<=19158):
                raise ValidationError('Animated frame lacks complete independently measured geometry')
            path=regular_file(folder/row['file'],folder,2*1024*1024)
            if _digest(path)!=row['sha256']:raise ValidationError('Animated frame PNG changed')
            stats=png_measurements(path.read_bytes(),include_pixel_hash=True,expected_size=(n,n))
            if stats!={k:row[k] for k in stats}:raise ValidationError('Animated frame pixels differ from the report')
            with Image.open(path) as im:
                if im.mode!='RGBA':raise ValidationError('Animated frame lost RGBA')
                alpha=im.getchannel('A').tobytes()
                if any(alpha[:n]+alpha[-n:]+alpha[::n]+alpha[n-1::n]) or alpha.count(0)<n*n//5:raise ValidationError('Animated frame is clipped or lacks transparent background')
        for key in ('rgba_sha256','normals_sha256'):
            if sequence[0][key]!=sequence[-1][key]:raise ValidationError('Animated sprite endpoints differ')
        if any(sequence[0]['geometry'][k]!=sequence[-1]['geometry'][k] for k in hash_fields):raise ValidationError('Animated geometry endpoints differ')
        if sequence[0]['geometry']['maximum_displacement']!=0 or sequence[-1]['geometry']['maximum_displacement']!=0:raise ValidationError('Animated endpoints are not neutral')
        motion|=len({r['rgba_sha256'] for r in sequence})>1
    if not motion:raise ValidationError('Animated sprite sample contains no visible animation')
    return report,proof


def checked_facial_atlas(folder: Path,frames: Path,request: FacialSpriteRequest,report: dict) -> dict:
    from PIL import Image
    data=read_json(regular_file(folder/'sprite_atlas.json',folder,4*1024*1024),4*1024*1024)
    settings=request.review.settings;n=settings.resolution;directions=settings.directions
    sheets=[f'sprite_sheet_{i:03d}.png' for i in range(directions)]
    if (data.get('frame_count')!=25*directions or data.get('fps')!=24 or data.get('frame_resolution')!={'width':n,'height':n}
            or data.get('angle_degrees')!=list(settings.angles()) or len(data.get('frames',[]))!=25*directions
            or [s.get('file') for s in data.get('sheets',[])]!=sheets):raise ValidationError('Animated atlas coverage/timing/camera differs')
    for direction,name in enumerate(sheets):
        path=regular_file(folder/name,folder,16*1024*1024)
        with Image.open(path) as image:
            if image.mode!='RGBA' or image.size!=(n*5,n*5):raise ValidationError('Animated atlas canvas differs')
            for i in range(25):
                row=data['frames'][direction*25+i];source=report['frames'][direction*25+i];x=(i%5)*n;y=(i//5)*n
                expected={'clip':'facial','direction_index':direction,'yaw_deg':settings.angles()[direction],'frame_index':i,'timestamp_s':round(i/24,7),
                    'sheet':name,'rect':{'x':x,'y':y,'width':n,'height':n},'pivot':{'x':round(report['pivot'][0]*n,4),'y':round(report['pivot'][1]*n,4)},
                    'source_frame':f'facial/dir-{direction:02d}/frame-{i:04d}.png','source_sha256':source['sha256']}
                if canonical(row)!=canonical(expected):raise ValidationError('Animated atlas frame timing/lineage/rectangle differs')
                with Image.open(regular_file(frames/source['file'],frames,2*1024*1024)) as original:
                    if image.crop((x,y,x+n,y+n)).tobytes()!=original.tobytes():raise ValidationError('Animated atlas crop differs from its actual frame')
    return data
