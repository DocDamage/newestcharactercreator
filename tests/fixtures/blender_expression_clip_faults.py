"""Real saved-Action/scene corruption in disposable copies; no source edits."""
from pathlib import Path
import json
import struct
import sys
import bpy

FAULTS = ('peak-ulp', 'key-time', 'interpolation', 'extra-channel', 'influence', 'key-coordinate-ulp',
          'rest-roll', 'uv', 'material', 'material-driver', 'fps', 'extra-action')


def mutate(source: Path, out: Path):
    out.mkdir(exist_ok=False)
    for fault in FAULTS:
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
        human = next(o for o in bpy.data.objects if o.type == 'MESH' and o.data.shape_keys)
        rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
        keys = human.data.shape_keys; action = keys.animation_data.action
        curves = [c for l in action.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
        curve = next(c for c in curves if c.keyframe_points[1].co.y > .001)
        if fault == 'peak-ulp':
            point = curve.keyframe_points[1]
            bits = struct.unpack('<I', struct.pack('<f', point.co.y))[0]
            point.co.y = struct.unpack('<f', struct.pack('<I', bits+1))[0]
        elif fault == 'key-time': curve.keyframe_points[1].co.x = 12.5; curve.update()
        elif fault == 'interpolation': curve.keyframe_points[0].interpolation = 'BEZIER'
        elif fault == 'extra-channel':
            key = next(k for k in keys.key_blocks if k.name != 'Basis' and not k.name.startswith('UCC_EXPR_V1_'))
            key.keyframe_insert(data_path='value', frame=1)
        elif fault == 'influence': keys.animation_data.action_influence = .75
        elif fault == 'key-coordinate-ulp':
            key = next(k for k in keys.key_blocks if k.name.startswith('UCC_EXPR_V1_'))
            point = next(p for p in key.data if abs(p.co.x) > .001)
            bits = struct.unpack('<I', struct.pack('<f', point.co.x))[0]
            point.co.x = struct.unpack('<f', struct.pack('<I', bits+1))[0]
        elif fault == 'rest-roll':
            bpy.context.view_layer.objects.active = rig; rig.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT'); rig.data.edit_bones['head'].roll += .001
            bpy.ops.object.mode_set(mode='OBJECT')
        elif fault == 'uv': human.data.uv_layers[0].data[0].uv.x += .001
        elif fault == 'material': bpy.data.materials[0].diffuse_color[0] = .12345
        elif fault == 'material-driver':
            material = bpy.data.materials[0]
            value = float(material.diffuse_color[0]); curve = material.driver_add('diffuse_color', 0)
            curve.driver.expression = repr(value)
        elif fault == 'fps': bpy.context.scene.render.fps = 23
        elif fault == 'extra-action':
            unexpected = bpy.data.actions.new('UNEXPECTED_EXPRESSION_ACTION'); unexpected.use_fake_user = True
        else: raise ValueError('Unsupported expression clip fixture fault')
        bpy.ops.wm.save_as_mainfile(filepath=str(out/(fault+'.blend')), compress=False)
        if fault == 'extra-action':
            bpy.ops.wm.open_mainfile(filepath=str(out/(fault+'.blend')), load_ui=False)
            if len(bpy.data.actions) != 2 or bpy.data.actions.get('UNEXPECTED_EXPRESSION_ACTION') is None:
                raise RuntimeError('Extra-Action corruption did not persist after reopening')
    (out/'faults.json').write_text(json.dumps(list(FAULTS)), encoding='utf-8')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:]
    if len(args) != 2: raise ValueError('Expected saved preview and new output directory')
    mutate(Path(args[0]), Path(args[1]))
