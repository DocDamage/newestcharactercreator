"""Actual MPFB export experiment, not a shipping asset or engine acceptance.

Consumes a staged copy of an admitted original master and the existing facial
clip recipe. Full reference coordinates remain private; stdout is aggregate.
"""
from array import array
from hashlib import file_digest
import argparse
import json
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from blender_bridge.face_geometry import intake, evaluated
from blender_bridge.expression_geometry import macro_context
from blender_bridge.expression_clip_action import create_action, peaks, linear_weight
from blender_bridge.expression_policy import keyname
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh, discard_godot_bind_mesh


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def run(master: Path, recipe: Path, out: Path, *, diagnostic_uv: bool = True,
        skeletal_probe: bool = False) -> dict:
    if master.is_symlink() or not master.is_file() or out.exists() or out.is_symlink():
        raise ValueError('Require a regular staged master and a new output directory')
    out.mkdir()
    before = digest(master)
    clip = json.loads(recipe.read_text(encoding='utf-8'))
    if clip['source']['master_sha256'] != before:
        raise ValueError('Facial recipe does not describe this exact staged master')
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    human, rig, _, targets = intake(bpy)
    _, race = macro_context(human, targets)
    values = peaks(clip['parameters'], race)
    candidate = build_godot_bind_mesh(bpy, human, rig)
    try:
        mesh = candidate.object.data
        if len(mesh.uv_layers) != 1:
            raise ValueError('Correspondence probe requires one original UV set; never overwrite user UV2')
        # Non-shipping diagnostic channel. Byte-pair encoding survives UV
        # packing and vertex splits, without changing the material's UV0.
        if diagnostic_uv:
            ids = mesh.uv_layers.new(name='UCC_DIAGNOSTIC_SOURCE_ID_V1')
            for index, loop in enumerate(mesh.loops):
                vertex = loop.vertex_index
                ids.data[index].uv = ((vertex & 255)/255., (vertex >> 8)/255.)
            ids.active_render = False
        mesh.uv_layers[0].active_render = True
        mesh.uv_layers.active_index = 0
        names = {group.index: group.name for group in human.vertex_groups}
        deform = {bone.name for bone in rig.data.bones if bone.use_deform}
        original_weights = []
        for source_index in candidate.source_vertex_ids:
            rows = [(names[group.group], float(group.weight))
                    for group in human.data.vertices[source_index].groups
                    if group.weight > 0 and names[group.group] in deform]
            total = math.fsum(weight for _, weight in rows)
            original_weights.append([[name, weight/total] for name, weight in rows])
        with (out/'source_weights.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(original_weights, stream, separators=(',', ':'), allow_nan=False)
        bind = array('f', (value for vertex in mesh.vertices
                          for value in (vertex.co.x, vertex.co.z, -vertex.co.y)))
        with (out/'bind_positions.bin').open('xb') as stream:
            bind.tofile(stream)
        create_action(bpy, candidate.object, values)
        if skeletal_probe:
            from fixtures.blender_godot_motion_probe import create, verify_controls
            create(bpy, rig)
        references = array('f')
        maximum = 0.
        for frame in range(1, 26):
            bpy.context.scene.frame_set(frame)
            if skeletal_probe:
                verify_controls(rig, frame)
            for (role, family), peak in values.items():
                human.data.shape_keys.key_blocks[keyname(role, family)].value = linear_weight(peak, frame)
            bpy.context.view_layer.update()
            source = evaluated(bpy, human)
            converted = evaluated(bpy, candidate.object)
            if len(source) != 13380 or len(converted) != len(source):
                raise ValueError('Conversion dropped or introduced visible vertices')
            error = max(math.dist(a, b) for a, b in zip(source, converted))
            if not math.isfinite(error) or error > 1e-6:
                raise ValueError('Converted facial mesh differs from the actual evaluated MPFB source')
            maximum = max(maximum, error)
            references.extend(value for vertex in source for value in vertex)
        for role, family in values:
            human.data.shape_keys.key_blocks[keyname(role, family)].value = 0.
        bpy.context.scene.frame_set(1)
        for obj in bpy.context.scene.objects:
            obj.select_set(False)
        rig.select_set(True); candidate.object.select_set(True)
        bpy.context.view_layer.objects.active = candidate.object
        destination = out/'character.glb'
        status = bpy.ops.export_scene.gltf(filepath=str(destination), check_existing=False,
            export_format='GLB', use_selection=True, export_yup=True,
            export_apply=False, export_skins=True, export_morph=True,
            export_morph_normal=True, export_def_bones=True,
            export_rest_position_armature=True, export_influence_nb=8,
            export_all_influences=False, export_materials='EXPORT',
            export_animations=True, export_animation_mode='SCENE',
            export_anim_scene_split_object=False,
            export_force_sampling=True, export_frame_range=True, export_frame_step=1,
            export_anim_slide_to_zero=True, export_morph_animation=True,
            export_cameras=False, export_lights=False)
        if 'FINISHED' not in status or not destination.is_file() or destination.is_symlink():
            raise ValueError('No actual regular GLB export was produced')
        if sys.byteorder != 'little':
            raise ValueError('Reference writer requires explicit little-endian floats')
        with (out/'source_positions.bin').open('xb') as stream:
            references.tofile(stream)
        if skeletal_probe:
            bpy.context.scene.frame_set(1)
            bpy.ops.wm.save_as_mainfile(filepath=str(out/'source_review.blend'), check_existing=False)
        observation = dict(candidate.observation)
        observation.update(status='REAL_MPFB_MASK_SKIN_MORPH_EXPORT_STAGED_NOT_ENGINE_VERIFIED',
            master_sha256=before, glb_sha256=digest(destination), glb_bytes=destination.stat().st_size,
            blender_version=bpy.app.version_string, fps=24, frames=25,
            positions_dtype='float32le', positions_sha256=digest(out/'source_positions.bin'),
            positions_bytes=(out/'source_positions.bin').stat().st_size,
            weights_sha256=digest(out/'source_weights.json'),
            diagnostic_source_ids_in_UV2=diagnostic_uv,
            bind_positions_sha256=digest(out/'bind_positions.bin'),
            actual_original_skeletal_diagnostic=skeletal_probe,
            shipping_animation_created=False,
            max_preexport_source_difference_m=maximum,
            source_world_matrix=[list(row) for row in human.matrix_world],
            bone_names=[bone.name for bone in rig.data.bones],
            expression_peaks={keyname(role, family): value
                              for (role, family), value in values.items()},
            skeletal_animation_export_verified=False, material_export_verified=False,
            engine_import_verified=False, visual_quality_approved=False)
    finally:
        for role, family in values:
            human.data.shape_keys.key_blocks[keyname(role, family)].value = 0.
        discard_godot_bind_mesh(bpy, candidate)
    if digest(master) != before:
        raise ValueError('Original staged master bytes changed')
    with (out/'blender_stage.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(observation, stream, indent=2, allow_nan=False)
    return observation


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--without-diagnostic-uv', action='store_true')
    parser.add_argument('--skeletal-probe', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = run(args.master, args.recipe, args.out,
                 diagnostic_uv=not args.without_diagnostic_uv, skeletal_probe=args.skeletal_probe)
    print(result['status'], result['visible_vertices'], result['frames'], flush=True)
