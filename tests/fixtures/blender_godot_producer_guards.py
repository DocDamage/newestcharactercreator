"""Rehashed saved-scene faults on private copies, never shipping animations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from blender_bridge.expression_clip_action import all_curves
from blender_bridge.godot_policy import OUTPUTS
from blender_bridge.godot_verify import verify_candidate


def run(source: Path, output: Path) -> dict:
    output.mkdir(exist_ok=False)
    original = {path.name:sha256(path.read_bytes()).hexdigest() for path in source.iterdir() if path.is_file()}
    job = json.loads((source/'request.json').read_text())
    rows = []
    for fault in ('facial_key', 'body_key', 'bone_bind'):
        folder = output/fault; folder.mkdir()
        for path in source.iterdir():
            if path.is_file() and path.name not in {'blender_verification.json', 'result.json', 'request.json', 'stdout.log', 'stderr.log'}:
                shutil.copy2(path, folder/path.name)
        bpy.ops.wm.open_mainfile(filepath=str(folder/'source_review.blend'), load_ui=False)
        rig = bpy.data.objects['Human.rig']
        if fault == 'facial_key':
            action = bpy.data.objects['UCC_Godot_Private_Character'].data.shape_keys.animation_data.action
            all_curves(action)[0].keyframe_points[1].co.y += .01
        elif fault == 'body_key':
            all_curves(rig.animation_data.action)[0].keyframe_points[1].co.y += .01
        else:
            bpy.context.view_layer.objects.active = rig
            rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
            rig.data.edit_bones['root'].head.x += .001
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.wm.save_as_mainfile(filepath=str(folder/'source_review.blend'), check_existing=False)
        modified = {**job, 'options':dict(job['options'])}
        modified['options'][OUTPUTS['source_review.blend']] = sha256((folder/'source_review.blend').read_bytes()).hexdigest()
        try:
            verify_candidate(bpy, folder.resolve(), modified)
        except ValueError as error:
            rows.append({'fault':fault,'rejected':True,'error':str(error),'outer_scene_hash_rebound':True})
        else:
            raise AssertionError('Rehashed saved-scene fault was accepted: '+fault)
        if (folder/'blender_verification.json').exists():
            raise AssertionError('Fault published a verification report')
    assert all(sha256((source/name).read_bytes()).hexdigest() == digest for name,digest in original.items())
    result = {'status':'REAL_REHASHED_PRODUCER_REOPEN_GUARDS_PASSED','blender':bpy.app.version_string,
              'rows':rows,'positive_source_unchanged':True,'engine_import_verified':False}
    (output/'receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    print(run(args.source,args.out)['status'],flush=True)
