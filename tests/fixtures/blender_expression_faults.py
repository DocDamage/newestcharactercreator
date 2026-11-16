"""Real saved-scene mutations on disposable copies; never product geometry."""
from pathlib import Path
import json
import sys

import bpy

REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from blender_bridge.expression_policy import TARGETS, keyname
from blender_bridge.face_geometry import intake

FAULTS = ('value', 'key-coordinate', 'weight', 'rest', 'uv', 'material', 'saved-pose', 'unrelated-key')


def mutate(source: Path, out: Path) -> None:
    out.mkdir(exist_ok=False)
    for fault in FAULTS:
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
        human, rig, _, _ = intake(bpy)
        key = human.data.shape_keys.key_blocks[keyname(*TARGETS[0][:2])]
        if fault == 'value':
            key.value = .001
        elif fault == 'key-coordinate':
            key.data[0].co.x += .001
        elif fault == 'weight':
            group = human.vertex_groups['head']
            vertex = next(v for v in human.data.vertices if any(g.group == group.index for g in v.groups))
            group.add([vertex.index], .125, 'REPLACE')
        elif fault == 'rest':
            bpy.context.view_layer.objects.active = rig; rig.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT'); rig.data.edit_bones['head'].roll += .001
            bpy.ops.object.mode_set(mode='OBJECT')
        elif fault == 'uv':
            human.data.uv_layers[0].data[0].uv.x += .01
        elif fault == 'material':
            if not bpy.data.materials: raise RuntimeError('Missing actual material to mutate')
            bpy.data.materials[0].diffuse_color[0] = .12345
        elif fault == 'saved-pose':
            rig.pose.bones['head'].location.x += .001
        elif fault == 'unrelated-key':
            old = next(k for k in human.data.shape_keys.key_blocks if not k.name.startswith('UCC_EXPR_V1_') and k.name != 'Basis')
            old.data[0].co.y += .001
        else:
            raise ValueError('Unsupported expression fixture fault')
        bpy.ops.wm.save_as_mainfile(filepath=str(out/(fault+'.blend')), compress=False)
    (out/'faults.json').write_text(json.dumps(list(FAULTS)), encoding='utf-8')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:]
    if len(args) != 2: raise ValueError('Expected source and new output directory')
    mutate(Path(args[0]), Path(args[1]))
