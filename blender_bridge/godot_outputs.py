"""Fixed private candidate serialization and explicit glTF exporter settings."""
from array import array
import json
from pathlib import Path
import sys
from typing import Any

from blender_bridge.face_policy import digest


def write_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
        stream.write('\n')


def write_floats(path: Path, values: array) -> None:
    if sys.byteorder != 'little':
        raise ValueError('Godot candidate requires explicit little-endian float32 serialization')
    with path.open('xb') as stream:
        values.tofile(stream)


def export_glb(bpy: Any, root: Path, human: Any, rig: Any, *, optimize_animation: bool = True,
               include_animation: bool = True, dense_morphs: bool = False) -> dict:
    if any(type(value) is not bool for value in (optimize_animation,include_animation,dense_morphs)):
        raise ValueError('Animation export, optimization and dense morph selection require explicit Booleans')
    destination = root/'character.glb'
    if destination.exists() or destination.is_symlink():
        raise ValueError('Refuse to replace an existing candidate export')
    for obj in bpy.context.scene.objects: obj.select_set(False)
    human.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = human
    options={'export_try_sparse_sk':False} if dense_morphs else {}
    result = bpy.ops.export_scene.gltf(filepath=str(destination), check_existing=False,
        export_format='GLB', use_selection=True, export_yup=True, export_apply=False,
        export_skins=True, export_morph=True, export_morph_normal=True,
        export_def_bones=True, export_rest_position_armature=True, export_influence_nb=8,
        export_all_influences=False, export_materials='EXPORT', export_animations=include_animation,
        export_animation_mode='SCENE', export_anim_scene_split_object=False,
        export_force_sampling=True, export_frame_range=True, export_frame_step=1,
        export_anim_slide_to_zero=True, export_morph_animation=True,
        export_optimize_animation_size=optimize_animation,
        export_cameras=False, export_lights=False,**options)
    if 'FINISHED' not in result or destination.is_symlink() or not destination.is_file():
        raise ValueError('Blender did not produce an actual complete candidate GLB')
    return {'glb_sha256': digest(destination), 'glb_bytes': destination.stat().st_size}
