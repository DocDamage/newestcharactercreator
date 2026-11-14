"""Corrupt actual prepared keys in disposable saved scenes; no product edits."""
from pathlib import Path
import json
import struct
import sys

import bpy

REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from blender_bridge.expression_policy import TARGETS, keyname
from blender_bridge.face_geometry import intake

FAULTS = ('missing', 'extra', 'value', 'coordinate-ulp', 'relative', 'mute', 'slider', 'interpolation', 'group', 'animation')


def mutate(source: Path, out: Path):
    out.mkdir(exist_ok=False)
    for fault in FAULTS:
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
        human, rig, _, _ = intake(bpy); keys = human.data.shape_keys.key_blocks
        key = keys[keyname(*TARGETS[0][:2])]
        if fault == 'missing': human.shape_key_remove(key)
        elif fault == 'extra': human.shape_key_add(name=key.name+'.001', from_mix=False)
        elif fault == 'value': key.value = .001
        elif fault == 'coordinate-ulp':
            point = next(p for p in key.data if abs(p.co.x) > .001)
            bits = struct.unpack('<I', struct.pack('<f', point.co.x))[0]
            point.co.x = struct.unpack('<f', struct.pack('<I', bits+1))[0]
        elif fault == 'relative': key.relative_key = next(k for k in keys if k.name != 'Basis' and k != key)
        elif fault == 'mute': key.mute = True
        elif fault == 'slider': key.slider_max = .75
        elif fault == 'interpolation': key.interpolation = 'KEY_CARDINAL'
        elif fault == 'group': key.vertex_group = 'head'
        elif fault == 'animation':
            key.keyframe_insert(data_path='value', frame=1)
        else: raise ValueError('Unknown canonical expression fixture fault')
        bpy.ops.wm.save_as_mainfile(filepath=str(out/(fault+'.blend')), compress=False)
    (out/'faults.json').write_text(json.dumps(list(FAULTS)), encoding='utf-8')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:]
    if len(args) != 2: raise ValueError('Expected source and new output directory')
    mutate(Path(args[0]), Path(args[1]))
