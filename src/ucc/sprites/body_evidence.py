"""Decode every requested RGBA sample and bind it to admitted cached geometry."""
from hashlib import sha256
from io import BytesIO
import json
import math
import struct
from pathlib import Path

from ucc.core.body_sprites import POLICY, BodySpriteRequest, WORKER_FIELDS
from ucc.core.errors import ValidationError
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.core.target_action_format import CLOCK, canonical_bytes, checked_sha
from ucc.jobs.godot_candidate_inputs import regular_file, read_json
from ucc.jobs.master_preview import _digest
from ucc.jobs.private_render_evidence import png_measurements


def frame_names(request: BodySpriteRequest) -> tuple[str, ...]:
    return tuple(f'body-{direction:02d}-{frame:04d}.png'
                 for direction in range(request.settings.directions) for frame in request.window.target_frames)


def atlas_side(request: BodySpriteRequest) -> int:
    return request.settings.resolution*min(8, max(2, math.ceil(math.sqrt(request.image_count))))


def _configuration(value, request):
    n = request.settings.resolution
    expected = {'engine':'CYCLES', 'device':'CPU', 'samples':32, 'resolution':[n,n,100],
                'transparent':True, 'format':['PNG','RGBA','8',15],
                'frame':request.window.target_first_frame, 'denoising':False,
                'adaptive_sampling':False, 'seed':0, 'animated_seed':False,
                'threads':['FIXED',2], 'pixel_aspect':[1.,1.], 'dither':0.,
                'compositor':False, 'sequencer':False, 'view':['Standard','None',0.,1.,False],
                'world_nodes':[[1.,1.,1.,1.],struct.unpack('<f',struct.pack('<f',.15))[0]],
                'world_node_types':['ShaderNodeBackground','ShaderNodeOutputWorld'], 'units':['METRIC',1.]}
    if type(value) is not dict or set(value) != set(expected)|{'objects'}:
        raise ValidationError('Body-sprite render configuration is incomplete or contains unknown fields')
    if canonical_bytes({key:value[key] for key in expected}) != canonical_bytes(expected):
        raise ValidationError('Body-sprite camera, transparent canvas or deterministic renderer changed')
    objects = value['objects']; kinds = {}
    if type(objects) is not dict: raise ValidationError('Body-sprite scene inventory is missing')
    for row in objects.values():
        if type(row) is not dict or row.get('type') not in ('MESH','ARMATURE','CAMERA','LIGHT'):
            raise ValidationError('Unsupported body-sprite scene object')
        world = row.get('world')
        if type(world) is not list or len(world) != 16 or any(type(v) not in (int,float) or not math.isfinite(v) for v in world):
            raise ValidationError('Body-sprite scene transform is invalid')
        kind = row['type']; kinds[kind] = kinds.get(kind,0)+1
        if kind == 'CAMERA':
            camera = row.get('camera')
            if (type(camera) is not dict or set(camera) != {'type','ortho_scale','clip_start','clip_end'}
                    or camera['type'] != 'ORTHO' or type(camera['ortho_scale']) not in (int,float)
                    or not .1 <= camera['ortho_scale'] <= 100 or row.get('dof') is not False):
                raise ValidationError('Body sprites require the bounded orthographic camera grid')
    if kinds != {'MESH':1,'ARMATURE':1,'CAMERA':request.settings.directions,'LIGHT':3}:
        raise ValidationError('Body-sprite scene objects differ from the selected human and camera grid')


def _json_bytes(path, expected=None):
    payload = path.read_bytes()
    if len(payload) > 4*1024*1024 or (expected is not None and sha256(payload).hexdigest() != expected):
        raise ValidationError('Body-sprite evidence bytes changed or exceed their bound')
    try:
        return json.loads(payload, object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed body-sprite evidence JSON') from error


def checked_body_evidence(folder: Path, request: BodySpriteRequest, bindings: dict, cache,
                          *, proof_sha256=None) -> tuple[dict, dict]:
    path = regular_file(folder/'body_sprite_stage.json', folder, 4*1024*1024)
    if _digest(path) != bindings['stage_sha256']:
        raise ValidationError('Body-sprite stage report changed')
    report = _json_bytes(path, bindings['stage_sha256'])
    proof = _json_bytes(regular_file(folder/'body_sprite_verification.json', folder, 4*1024*1024), proof_sha256)
    fields = {'schema_version','policy','bindings','scene_sha256','source_state_sha256',
              'saved_action_state_sha256','shader_sha256','temporary_matte_sha256','source_material_slots',
              'configuration','original_scene','pivot','full_clock','window','frames','blender_version',
              'blender_build_hash','visual_quality_approved','material_adopted'}
    base = {key:bindings[key] for key in WORKER_FIELDS}
    if (type(report) is not dict or set(report) != fields or type(report['schema_version']) is not int
            or report['schema_version'] != 1 or report['policy'] != POLICY
            or canonical_bytes(report['bindings']) != canonical_bytes(base)
            or report['scene_sha256'] != bindings['scene_sha256']
            or report['temporary_matte_sha256'] != request.temporary_matte.sha256
            or type(report['source_material_slots']) is not int or report['source_material_slots'] != 0
            or report['material_adopted'] is not False or report['visual_quality_approved'] is not False
            or canonical_bytes(report['full_clock']) != canonical_bytes(dict(CLOCK))
            or canonical_bytes(report['window']) != canonical_bytes(request.window.to_dict())
            or type(report['original_scene']) is not str or not report['original_scene']
            or type(report['blender_version']) is not str or not report['blender_version'].startswith('5.3.')
            or type(report['blender_build_hash']) is not str or not 7 <= len(report['blender_build_hash']) <= 64):
        raise ValidationError('Body-sprite report lost its complete Action, window or temporary-material binding')
    for key in ('source_state_sha256','saved_action_state_sha256','shader_sha256'): checked_sha(report[key])
    expected = {'schema_version':1,'policy':POLICY,'bindings':bindings,'verified_reopen':True,
                'saved_scene_rebuilt_or_repaired':False,'source_state_sha256':report['source_state_sha256'],
                'saved_action_state_sha256':report['saved_action_state_sha256'],
                'shader_sha256':report['shader_sha256'],'temporary_matte_sha256':request.temporary_matte.sha256,
                'reference_frames':request.image_count,'saved_frames':request.image_count,
                'full_source_frames_verified':300,'full_saved_frames_verified':300,
                'exact_selected_pose_match':True,'exact_rerender_pixels':True,
                'material_adopted':False,'visual_quality_approved':False}
    if canonical_bytes(proof) != canonical_bytes(expected):
        raise ValidationError('Body sprites lack complete original-source and saved-scene verification')
    _configuration(report['configuration'], request)
    pivot = report['pivot']
    if type(pivot) is not list or len(pivot) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1 for v in pivot):
        raise ValidationError('Body-sprite origin is invalid')
    if cache.frame_count != 300 or cache.source_first_frame != 2 or cache.fps != 30:
        raise ValidationError('Body sprites need the original complete admitted cache clock')
    rows = report['frames']; names = frame_names(request); per_frame = {}
    if type(rows) is not list or len(rows) != request.image_count:
        raise ValidationError('Body-sprite selected image coverage is incomplete')
    from PIL import Image
    n = request.settings.resolution
    geometry_fields = {'evaluated_sha256','positions_sha256','triangles_sha256','pose_sha256',
                       'raw_skin_sha256','vertex_count','triangle_count'}
    for index, (row, name) in enumerate(zip(rows, names)):
        direction, offset = divmod(index, request.window.sample_count)
        target = request.window.target_first_frame+offset
        if (type(row) is not dict or set(row) != {'file','direction_index','yaw_deg','target_frame','source_frame',
                'geometry','normals_sha256','sha256','rgba_sha256','opaque_pixels','opaque_bounds'}
                or row['file'] != name or type(row['direction_index']) is not int or row['direction_index'] != direction
                or row['yaw_deg'] != request.settings.angles()[direction]
                or type(row['target_frame']) is not int or row['target_frame'] != target
                or type(row['source_frame']) is not int or row['source_frame'] != target+1):
            raise ValidationError('Body-sprite image order or absolute source/target frame changed')
        geometry = row['geometry']
        if (type(geometry) is not dict or set(geometry) != geometry_fields
                or type(geometry['vertex_count']) is not int or geometry['vertex_count'] != cache.vertex_count
                or type(geometry['triangle_count']) is not int or geometry['triangle_count'] != cache.triangle_count):
            raise ValidationError('Body-sprite geometry coverage differs from the admitted character')
        for key in geometry_fields-{'vertex_count','triangle_count'}: checked_sha(geometry[key])
        for key in ('normals_sha256','sha256','rgba_sha256'): checked_sha(row[key])
        positions, triangles = cache.frame(target-1)
        if geometry['positions_sha256'] != sha256(positions).hexdigest() or geometry['triangles_sha256'] != sha256(triangles).hexdigest():
            raise ValidationError('Body-sprite selected geometry differs from the complete admitted Action cache')
        signature = (canonical_bytes(geometry), row['normals_sha256'])
        if target in per_frame and per_frame[target] != signature:
            raise ValidationError('Camera direction changed the selected body geometry or normals')
        per_frame[target] = signature
        image_path = regular_file(folder/name, folder, 2*1024*1024)
        payload = image_path.read_bytes()
        if sha256(payload).hexdigest() != row['sha256']: raise ValidationError('Body-sprite PNG changed')
        observed = png_measurements(payload, include_pixel_hash=True, expected_size=(n,n))
        if observed != {key:row[key] for key in observed}: raise ValidationError('Body-sprite decoded pixels differ from evidence')
        with Image.open(BytesIO(payload)) as image:
            if image.mode != 'RGBA': raise ValidationError('Body sprite lost its alpha channel')
            alpha = image.getchannel('A').tobytes()
            if any(alpha[:n]+alpha[-n:]+alpha[::n]+alpha[n-1::n]) or alpha.count(0) < n*n//5:
                raise ValidationError('Body sprite is clipped or lacks transparent background')
    return report, proof


def annotate_body_atlas(folder: Path, request: BodySpriteRequest) -> None:
    """Add absolute clock labels to newly generated sample metadata only."""
    path = regular_file(folder/'sprite_atlas.json', folder, 4*1024*1024); data = read_json(path, 4*1024*1024)
    data['registered_body_sample'] = {'full_clock':dict(CLOCK),'selected_window':request.window.to_dict(),'material_adopted':False}
    for row in data['frames']:
        target = request.window.target_first_frame+row['frame_index']
        row.update(target_frame=target, source_frame_number=target+1)
    path.write_bytes(canonical_bytes(data))


def checked_body_atlas(folder: Path, frames: Path, request: BodySpriteRequest, report: dict) -> dict:
    from PIL import Image
    data = read_json(regular_file(folder/'sprite_atlas.json', folder, 4*1024*1024), 4*1024*1024)
    n = request.settings.resolution; columns = atlas_side(request)//n; capacity = columns*columns
    pages = math.ceil(request.image_count/capacity); sheets = [f'sprite_sheet_{i:03d}.png' for i in range(pages)]
    clock = {'full_clock':dict(CLOCK),'selected_window':request.window.to_dict(),'material_adopted':False}
    if (set(data) != {'schema_version','source_geometry_verified','frame_count','fps','frame_resolution',
                     'angle_degrees','alpha','sheets','frames','registered_body_sample'}
            or data['schema_version'] != 1 or data['source_geometry_verified'] is not False
            or data['frame_count'] != request.image_count or data['fps'] != 30
            or data['frame_resolution'] != {'width':n,'height':n} or data['alpha'] != 'straight_rgba'
            or data['angle_degrees'] != list(request.settings.angles())
            or canonical_bytes(data['registered_body_sample']) != canonical_bytes(clock)
            or [row.get('file') for row in data['sheets']] != sheets or len(data['frames']) != request.image_count):
        raise ValidationError('Body-sprite atlas lost complete selected timing, image coverage or camera labels')
    for page, name in enumerate(sheets):
        sheet = regular_file(folder/name, folder, 32*1024*1024)
        selected = report['frames'][page*capacity:(page+1)*capacity]
        if data['sheets'][page] != {'file':name,'size_bytes':sheet.stat().st_size}:
            raise ValidationError('Body-sprite atlas sheet record changed')
        with Image.open(sheet) as image:
            height = math.ceil(len(selected)/columns)*n
            if image.mode != 'RGBA' or image.size != (columns*n,height):
                raise ValidationError('Body-sprite atlas canvas changed')
            for offset, source in enumerate(selected):
                index = page*capacity+offset; direction, frame = divmod(index, request.window.sample_count)
                x = offset%columns*n; y = offset//columns*n; target = request.window.target_first_frame+frame
                expected = {'clip':'body_sample','direction_index':direction,'yaw_deg':request.settings.angles()[direction],
                    'frame_index':frame,'timestamp_s':round(frame/30,7),'sheet':name,
                    'rect':{'x':x,'y':y,'width':n,'height':n},
                    'pivot':{'x':round(report['pivot'][0]*n,4),'y':round(report['pivot'][1]*n,4)},
                    'source_frame':f'body_sample/dir-{direction:02d}/frame-{frame:04d}.png',
                    'source_sha256':source['sha256'],'target_frame':target,'source_frame_number':target+1}
                if canonical_bytes(data['frames'][index]) != canonical_bytes(expected):
                    raise ValidationError('Body-sprite atlas frame lineage or absolute clock changed')
                with Image.open(regular_file(frames/source['file'], frames, 2*1024*1024)) as original:
                    if image.crop((x,y,x+n,y+n)).tobytes() != original.tobytes():
                        raise ValidationError('Body-sprite atlas crop differs from its verified PNG')
            for offset in range(len(selected), columns*math.ceil(len(selected)/columns)):
                x = offset%columns*n; y = offset//columns*n
                if image.crop((x,y,x+n,y+n)).getbbox() is not None:
                    raise ValidationError('Body-sprite atlas contains unrequested pixels')
    return data
