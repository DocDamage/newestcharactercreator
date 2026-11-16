"""Fresh-process saved Action/deformation observation without recreating export."""
from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from blender_bridge.expression_clip_action import linear_weight
from blender_bridge.face_geometry import evaluated
from fixtures.blender_godot_motion_probe import verify_controls


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(folder: Path) -> dict:
    scene = folder/'source_review.blend'
    report = json.loads((folder/'blender_stage.json').read_text())
    hashes = {name: digest(folder/name) for name in
              ('source_review.blend', 'character.glb', 'source_positions.bin', 'bind_positions.bin')}
    if hashes['character.glb'] != report['glb_sha256'] or hashes['source_positions.bin'] != report['positions_sha256']:
        raise ValueError('Staged geometry or candidate changed before independent reopening')
    bpy.ops.wm.open_mainfile(filepath=str(scene), load_ui=False)
    humans = [obj for obj in bpy.data.objects if obj.type == 'MESH' and len(obj.data.vertices) == 19158]
    rigs = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    candidate = bpy.data.objects.get('UCC_Godot_Private_Character')
    if len(humans) != 1 or len(rigs) != 1 or candidate is None or len(candidate.data.uv_layers) != 1:
        raise ValueError('Saved scene lost actual source, rig, candidate or original UV set')
    human, rig = humans[0], rigs[0]
    if len(bpy.data.actions) != 2 or rig.animation_data.action is None:
        raise ValueError('Saved scene lost combined skeletal and facial Actions')
    references = array('f')
    maximum = 0.
    frames = []
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        verify_controls(rig, frame)
        for name, peak in report['expression_peaks'].items():
            human.data.shape_keys.key_blocks[name].value = linear_weight(peak, frame)
        bpy.context.view_layer.update()
        source = evaluated(bpy, human)
        converted = evaluated(bpy, candidate)
        if len(source) != 13380 or len(converted) != len(source):
            raise ValueError('Saved animation changed visible topology')
        error = max(math.dist(a, b) for a, b in zip(source, converted))
        if not math.isfinite(error) or error > 1e-6:
            raise ValueError('Reopened candidate differs from independent original deformation')
        maximum = max(maximum, error)
        sample = array('f', (value for point in source for value in point))
        references.extend(sample)
        frames.append({'frame': frame, 'source_world_sha256': hashlib.sha256(sample.tobytes()).hexdigest(),
                       'converted_max_error_m': error})
    if references.tobytes() != (folder/'source_positions.bin').read_bytes():
        raise ValueError('Fresh original saved-Action evaluation differs from staged reference bytes')
    if any(digest(folder/name) != sha for name, sha in hashes.items()):
        raise ValueError('Independent reopening changed staged files')
    return {'status': 'FRESH_SAVED_COMBINED_ACTION_AND_FULL_SURFACE_VERIFIED',
            'blender_version': bpy.app.version_string, 'bound_files': hashes,
            'frames': frames, 'source_vertices': 13380, 'max_conversion_error_m': maximum,
            'independent_source_bytes_exact': True, 'shipping_animation_created': False,
            'engine_import_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = run(args.folder)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(result['status'], flush=True)
