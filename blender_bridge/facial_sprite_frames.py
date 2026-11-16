"""All-frame original interpolation/saved Action rendering; no geometry substitute."""
from pathlib import Path
from typing import Any
from hashlib import sha256
from blender_bridge.sprite_scene import snapshot,PREFIX
from blender_bridge.expression_clip_action import linear_weight
from blender_bridge.expression_clip_surface import measure_frame
from blender_bridge.expression_normals import corners
from blender_bridge.expression_geometry import source_state
from blender_bridge.face_policy import digest
from blender_bridge.skin_material_model import checked_owned_material
from ucc.jobs.private_render_evidence import png_measurements


def render_frames(bpy: Any,root: Path,scene: Any,settings: Any,context: tuple,spec: Any,*,prefix: str,manual: bool) -> list[dict]:
    human,rig,targets,loaded,baseline,neutral,original,values,support,hip=context
    before=snapshot(scene);rows=[]
    for direction,yaw in enumerate(settings.angles()):
        scene.camera=bpy.data.objects[PREFIX+f'CAMERA_{direction:02d}']
        for frame in range(1,26):
            scene.frame_set(frame)
            if manual:
                for pair,key in loaded.items():key.value=linear_weight(values[pair],frame)
            bpy.context.view_layer.update()
            _,geometry=measure_frame(bpy,human,rig,targets,frame,values,loaded,baseline,original,support)
            normal_sha=sha256(corners(bpy,human)).hexdigest()
            if checked_owned_material(bpy,human)!=spec:raise ValueError('Facial sprite shader changed during animation')
            name=f'facial-{direction:02d}-{frame:02d}.png';path=root/(prefix+name)
            if path.exists() or path.is_symlink():raise ValueError('Facial renderer refuses existing output')
            scene.render.filepath=str(path);bpy.ops.render.render(scene=scene.name,write_still=True)
            observed=snapshot(scene);observed['frame']=1
            if observed!=before:raise ValueError('Facial rendering changed source/camera/lighting settings')
            stats=png_measurements(path.read_bytes(),include_pixel_hash=True,expected_size=(settings.resolution,settings.resolution))
            rows.append({'file':name,'direction_index':direction,'yaw_deg':yaw,'frame':frame,'geometry':geometry,
                'normals_sha256':normal_sha,'sha256':digest(path),**stats})
        if rows[-25]['rgba_sha256']!=rows[-1]['rgba_sha256'] or rows[-25]['normals_sha256']!=rows[-1]['normals_sha256']:
            raise ValueError('Facial sprite endpoints do not restore exact neutral pixels and normals')
    if not any(len({r['rgba_sha256'] for r in rows[i*25:(i+1)*25]})>1 for i in range(settings.directions)):
        raise ValueError('Facial sprite sample contains no visible animation in any direction')
    scene.frame_set(1)
    if manual:
        for key in loaded.values():key.value=0.
    scene.camera=bpy.data.objects[PREFIX+'CAMERA_00'];bpy.context.view_layer.update()
    if source_state(bpy,human,rig,targets)!=neutral:raise ValueError('Facial sprite rendering failed to restore exact neutral geometry')
    return rows


def compare_frames(root: Path,actual: list[dict],report: dict) -> None:
    expected=report.get('frames')
    if type(expected) is not list or len(actual)!=len(expected):raise ValueError('Facial sprite frame coverage differs')
    from ucc.core.sprite_render import canonical
    for a,b in zip(actual,expected):
        path=root/a['file']
        if (not path.is_file() or path.is_symlink() or digest(path)!=b.get('sha256')
                or canonical({k:v for k,v in a.items() if k!='sha256'})!=canonical({k:v for k,v in b.items() if k!='sha256'})):
            raise ValueError('Facial sprite pixels, geometry or normals differ from the independent full-frame reference')
