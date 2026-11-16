"""Actual MPFB source negatives; no substitute model or saved mutation."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blender_bridge.face_geometry import intake
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh, discard_godot_bind_mesh, SOURCE_ID


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def run(master: Path) -> dict:
    before = digest(master)
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    human, rig, _, _ = intake(bpy)
    armature = human.modifiers[0]
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    visibility, pose = armature.show_viewport, rig.data.pose_position
    candidate = build_godot_bind_mesh(bpy, human, rig)
    if (any(key.value != 0. for key in candidate.object.data.shape_keys.key_blocks)
            or not candidate.object.modifiers[0].show_viewport or not candidate.object.modifiers[0].show_render
            or armature.show_viewport != visibility or rig.data.pose_position != pose):
        raise RuntimeError('Actual neutral bind copy activated morphs, lost skin or changed source visibility/pose')
    discard_godot_bind_mesh(bpy, candidate)
    if (len(bpy.data.objects), len(bpy.data.meshes)) != counts or human.data.attributes.get(SOURCE_ID):
        raise RuntimeError('Positive bind copy cleanup changed source/copy ownership')
    guards = []
    for case in ('preserve_volume', 'envelopes', 'multi_modifier', 'corrective_smooth',
                 'negative_mesh_scale', 'negative_rig_scale', 'zero_scale', 'nonneutral_morph'):
        scale_human, scale_rig = human.scale.copy(), rig.scale.copy()
        flags = {name: getattr(armature, name) for name in ('use_deform_preserve_volume', 'use_bone_envelopes', 'use_multi_modifier')}
        added = None; changed_key = None
        try:
            if case == 'preserve_volume': armature.use_deform_preserve_volume = True
            if case == 'envelopes': armature.use_bone_envelopes = True
            if case == 'multi_modifier': armature.use_multi_modifier = True
            if case == 'corrective_smooth': added = human.modifiers.new('UCC_ACTUAL_NEGATIVE_ONLY', 'CORRECTIVE_SMOOTH')
            if case == 'negative_mesh_scale': human.scale = (-1., -1., 1.)
            if case == 'negative_rig_scale': rig.scale = (-1., -1., 1.)
            if case == 'zero_scale': human.scale = (0., 1., 1.)
            if case == 'nonneutral_morph':
                changed_key = next(key for key in human.data.shape_keys.key_blocks if key.name.startswith('UCC_EXPR_V1_'))
                changed_key.value = .1
            bpy.context.view_layer.update()
            counts = (len(bpy.data.objects), len(bpy.data.meshes))
            try:
                build_godot_bind_mesh(bpy, human, rig)
            except ValueError as error:
                if (len(bpy.data.objects), len(bpy.data.meshes)) != counts or human.data.attributes.get(SOURCE_ID):
                    raise RuntimeError('Rejected actual source left an owned copy or source attribute behind')
                guards.append({'case': case, 'error': str(error), 'no_source_or_copy_leak': True})
            else:
                raise RuntimeError('Unsupported actual source was admitted: '+case)
        finally:
            human.scale, rig.scale = scale_human, scale_rig
            for name, value in flags.items(): setattr(armature, name, value)
            if added is not None: human.modifiers.remove(added)
            if changed_key is not None: changed_key.value = 0.
            bpy.context.view_layer.update()
    if digest(master) != before:
        raise RuntimeError('Actual source master bytes changed')
    return {'status': 'ACTUAL_MPFB_GODOT_BIND_NEGATIVES_VERIFIED', 'blender_version': bpy.app.version_string,
            'positive_copy_all_morphs_neutral_and_skin_enabled': True,
            'positive_source_visibility_pose_and_ownership_preserved': True,
            'master_sha256': before, 'guards': guards, 'master_unchanged': True,
            'engine_import_verified': False, 'shipping_asset_created': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = run(args.master)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(result['status'], len(result['guards']), flush=True)
