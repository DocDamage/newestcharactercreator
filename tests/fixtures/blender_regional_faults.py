"""Actual original-only saved and transaction faults; aggregate records only."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import sys
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src'), str(Path(__file__).parent)]
from blender_bridge.native_region_mask import MASK_NAME, mask_signature
from blender_bridge.native_retarget import retarget_native
import blender_bridge.native_regional_corrective as regional
from blender_regional_checks import geometry, groups, rest, modifier_state, require

SAVED = ('missing_layer', 'reordered_layers', 'unbound_layer', 'coherent_factor',
         'bone_weight_ulp', 'coherent_mask_ulp', 'missing_mask', 'boolean_schema')


def objects():
    return (next(o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.vertices) > 100),
            next(o for o in bpy.data.objects if o.type == 'ARMATURE'))


def next_float(value):
    return struct.unpack('<f', struct.pack('<I', struct.unpack('<I', struct.pack('<f', value))[0]+1))[0]


def saved_faults(job: Path, out: Path):
    out.mkdir(exist_ok=False)
    original = json.loads((job/'target_timeline.json').read_text(encoding='utf-8'))
    protected = {name: sha256((job/name).read_bytes()).hexdigest() for name in
                 ('candidate.blend', 'review_motion.blend', 'target_timeline.json', 'source_snapshot.json', 'native_mapping.json')}
    records = {}
    for fault in SAVED:
        bpy.ops.wm.open_mainfile(filepath=str(job/'review_motion.blend'), load_ui=False)
        human, rig = objects(); data = deepcopy(original); folder = out/fault; folder.mkdir()
        bpy.context.view_layer.objects.active = human; human.select_set(True); details = {}
        if fault == 'missing_layer': human.modifiers.remove(human.modifiers[-1])
        if fault == 'reordered_layers':
            require('FINISHED' in bpy.ops.object.modifier_move_up(modifier=human.modifiers[-1].name), 'Fault reorder failed')
        if fault == 'unbound_layer':
            mod = human.modifiers[-1]
            require(mod.is_bind and 'FINISHED' in bpy.ops.object.correctivesmooth_bind(modifier=mod.name) and not mod.is_bind, 'Fault unbind failed')
        if fault == 'coherent_factor':
            human.modifiers[-2].factor = .4
            data['skin_deformation']['modifiers'][0]['factor'] = float(human.modifiers[-2].factor)
        if fault == 'bone_weight_ulp':
            found = False
            for vertex in human.data.vertices:
                if found: break
                for row in vertex.groups:
                    group = human.vertex_groups[row.group]; bone = rig.data.bones.get(group.name)
                    if bone is None or not bone.use_deform or not .01 < row.weight < .99: continue
                    value = float(row.weight); changed = next_float(value)
                    if round(value*1000000) != round(changed*1000000): continue
                    group.add([vertex.index], changed, 'REPLACE'); found = True; break
            require(found, 'No genuine one-ULP bone weight fault could be constructed')
            details['legacy_weight_rounding_unchanged'] = True
        if fault == 'coherent_mask_ulp':
            group = human.vertex_groups[MASK_NAME]; found = False
            for vertex in human.data.vertices:
                selected = [g for g in vertex.groups if g.group == group.index]
                if selected and .01 < selected[0].weight < .99:
                    group.add([vertex.index], next_float(selected[0].weight), 'REPLACE'); found = True; break
            require(found, 'No genuine one-ULP mask fault could be constructed')
            data['skin_deformation']['region_mask'] = mask_signature(human, group)
            details['derived_mask_proof_coherently_rehashed'] = True
        if fault == 'missing_mask': human.vertex_groups.remove(human.vertex_groups[MASK_NAME])
        if fault == 'boolean_schema': data['skin_deformation']['schema_version'] = True
        scene = folder/'review_motion.blend'
        require('FINISHED' in bpy.ops.wm.save_as_mainfile(filepath=str(scene), compress=False, copy=True), 'Fault scene save failed')
        data['visual_review_blend'] = {'name': scene.name, 'bytes': scene.stat().st_size, 'sha256': sha256(scene.read_bytes()).hexdigest()}
        timeline = folder/'target_timeline.json'; timeline.write_text(json.dumps(data, allow_nan=False)+'\n', encoding='utf-8')
        records[fault] = {'review_sha256': data['visual_review_blend']['sha256'],
                         'timeline_sha256': sha256(timeline.read_bytes()).hexdigest(), **details}
        require(all(sha256((job/name).read_bytes()).hexdigest() == h for name, h in protected.items()), 'Saved fault changed originals')
    (out/'generated.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')


def transactions(job: Path, out: Path):
    out.mkdir(exist_ok=False); checked = []
    base_options = json.loads((job/'request.json').read_text(encoding='utf-8'))['options']
    for fault in ('second_bind_failure', 'mid_action_settings'):
        folder = out/fault; folder.mkdir()
        for name in ('candidate.blend', 'source_snapshot.json', 'native_mapping.json'): shutil.copyfile(job/name, folder/name)
        bpy.ops.wm.open_mainfile(filepath=str(folder/'candidate.blend'), load_ui=False)
        human, rig = objects(); points, edges, skin = geometry(human)
        before = (groups(human), rest(rig), tuple(modifier_state(m) for m in human.modifiers), tuple(a.name for a in bpy.data.actions))
        original_bind = regional._bind; original_measure = regional.RegionalCorrectiveSkin.measure_raw; calls = [0]
        def failed_bind(bpy, name):
            calls[0] += 1
            return original_bind(bpy, name) if calls[0] == 1 else {'CANCELLED'}
        def changed_settings(state, *args):
            calls[0] += 1
            if calls[0] == 20: state.modifiers[-1].factor = .5
            return original_measure(state, *args)
        inject = (patch.object(regional, '_bind', failed_bind) if fault == 'second_bind_failure' else
                  patch.object(regional.RegionalCorrectiveSkin, 'measure_raw', changed_settings))
        try:
            with inject: retarget_native(bpy, folder, {**base_options, 'render_private_frames': False})
        except ValueError as error:
            require(('bind every regional' if fault == 'second_bind_failure' else 'binding or ordered settings changed') in str(error), 'Unexpected transaction error: '+str(error))
        else: raise RuntimeError('Original regional transaction fault was accepted')
        human, rig = objects(); after_points, after_edges, after_skin = geometry(human)
        require(before == (groups(human), rest(rig), tuple(modifier_state(m) for m in human.modifiers), tuple(a.name for a in bpy.data.actions)), 'Transaction left weights/groups/rest/modifiers/actions changed')
        require(points == after_points and edges == after_edges and skin == after_skin and not (folder/'review_motion.blend').exists() and not (rig.animation_data and rig.animation_data.action), 'Transaction failed exact original skin/Action cleanup')
        require(calls[0] == (2 if fault == 'second_bind_failure' else 20), 'Transaction did not reach the intended fault')
        checked.append(fault)
    (out/'transactions.json').write_text(json.dumps({'transaction_faults_rejected': checked, 'exact_original_float32_skin_groups_rest_stack_actions_restored': True}, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('saved', 'transaction'), required=True)
    parser.add_argument('--job', type=Path, required=True); parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    (saved_faults if args.mode == 'saved' else transactions)(args.job, args.outdir)
