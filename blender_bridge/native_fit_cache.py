"""Private fitted playback, independently remeasured from the saved Action."""
from array import array
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import struct
import sys
import zlib

from blender_bridge.native_fit_measure import measure_saved_fit
from blender_bridge.native_fit_scene import unchanged
from blender_bridge.native_inputs import read_json
from blender_bridge.native_playback_cache import MAGIC,MAX_BYTES,record
from blender_bridge.native_review_reopen import scene_objects


def export_fit_cache(bpy: Any,root: Path,options: dict) -> dict:
    expected=read_json(root/'fitted_timeline.json',options['fit_report_sha256'],64*1024*1024)
    actual=measure_saved_fit(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh fitted playback measurement differs from canonical saved geometry')
    baseline=read_json(root/'target_timeline.json',options['timeline_sha256'],64*1024*1024)
    if actual['surface_review']['status']!='CHECKED' or any(r[side]['pair_count'] for r in actual['surface_review']['frames'] for side in ('left','right')):
        raise ValueError('Fitted playback requires a complete clear hand/arm surface review')
    human,_rig=scene_objects(bpy)
    binary=root/'fitted_skin.bin';manifest=root/'fitted_skin.json';partial=root/'fitted_skin.partial'
    if any(p.exists() or p.is_symlink() for p in (binary,manifest,partial)):
        raise ValueError('Refuse to replace fitted playback outputs')
    rows=[];counts=None;total_raw=0
    try:
        with partial.open('xb') as stream:
            stream.write(MAGIC)
            for frame,row in enumerate(actual['frames'],1):
                bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
                graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
                mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
                if mesh is None:raise ValueError('Cannot evaluate fitted playback skin')
                try:
                    mesh.calc_loop_triangles();n,t=len(mesh.vertices),len(mesh.loop_triangles)
                    if not 100<n<=100000 or not 100<t<=200000:raise ValueError('Fitted playback exceeds geometry bounds')
                    if counts is None:counts=(n,t)
                    if counts!=(n,t):raise ValueError('Fitted playback topology counts change; no cropping')
                    total_raw+=12*(n+t)
                    if total_raw>MAX_BYTES:raise ValueError('Full fitted playback exceeds 256 MiB; no cropping')
                    vertices=array('f',[0.])*(3*n);indices=array('I',[0])*(3*t)
                    mesh.vertices.foreach_get('co',vertices);mesh.loop_triangles.foreach_get('vertices',indices)
                    if any(not math.isfinite(v) or abs(v)>10000 for v in vertices):raise ValueError('Invalid fitted playback coordinates')
                    skin=sha256()
                    for i in range(0,len(vertices),3):
                        skin.update(struct.pack('<qqq',*(round(v*1000000) for v in vertices[i:i+3])))
                    if sys.byteorder!='little':vertices.byteswap();indices.byteswap()
                    if (skin.hexdigest()!=row['skin_sha256'] or sha256(indices.tobytes()).hexdigest()!=row['triangle_sha256'] or
                        n!=row['vertex_count'] or t!=row['triangle_count']):
                        raise ValueError('Fitted playback skin/topology differs from independently saved geometry')
                    raw=vertices.tobytes()+indices.tobytes();packed=zlib.compress(raw,1);offset=stream.tell()
                    if offset+len(packed)>MAX_BYTES:raise ValueError('Packed fitted playback exceeds 256 MiB')
                    stream.write(packed)
                    rows.append({'frame':frame,'offset':offset,'compressed_bytes':len(packed),'raw_sha256':sha256(raw).hexdigest(),
                                 'skin_sha256':row['skin_sha256'],'hip_world':baseline['full_timeline_frames'][frame-1].get('hip_midpoint_world',baseline['full_timeline_frames'][frame-1]['root_world_head'])})
                finally:evaluated.to_mesh_clear()
        partial.rename(binary)
        data={'schema_version':1,'status':'FITTED_VERIFIED_SKIN_CACHE_V1','bindings':dict(options),
              'coordinate_space':'BLENDER_LOCAL_Z_UP','world_matrix':actual['mesh_world'],'fps':actual['fps'],
              'frame_count':actual['frame_count'],'source_first_frame':actual['source_first_frame'],
              'vertex_count':counts[0],'triangle_count':counts[1],'frames':rows,'geometry':record(binary),
              'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        payload=json.dumps(data,allow_nan=False,separators=(',',':')).encode()
        if len(payload)>4*1024*1024:raise ValueError('Fitted playback manifest exceeds its bound')
        unchanged(root,options)
        with manifest.open('xb') as stream:stream.write(payload)
        return {'status':'REAL_NATIVE_FIT_CACHE_EXPORTED','bindings':dict(options),'frames_verified':actual['frame_count'],
                'manifest':record(manifest),'originals_unchanged':True,
                'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    except BaseException:
        for path in (partial,binary,manifest):
            if path.is_file() and not path.is_symlink():path.unlink()
        raise
