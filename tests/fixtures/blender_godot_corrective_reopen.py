"""Fresh saved native/corrective Action audit without creating or repairing it."""
from array import array
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from blender_bridge.expression_clip_action import all_curves
from blender_bridge.face_geometry import evaluated
from blender_bridge.fbx_source import pose_digest
from blender_bridge.pose_deformation import _evaluated_vertices


def run(folder: Path) -> dict:
    report=json.loads((folder/'blender_stage.json').read_text())
    files={name:sha256((folder/name).read_bytes()).hexdigest() for name in ('source_review.blend','character.glb','source_positions.bin','bind_positions.bin','blender_stage.json')}
    if files['source_review.blend']!=report['review_scene_sha256'] or files['character.glb']!=report['glb_sha256']:
        raise ValueError('Saved corrective candidate changed')
    for path,value in report['original_source_files'].items():
        if sha256(Path(path).read_bytes()).hexdigest()!=value:raise ValueError('Original native source changed')
    source_job=Path(next(path for path in report['original_source_files'] if path.endswith('target_timeline.json'))).parent
    timeline=json.loads((source_job/'target_timeline.json').read_text())
    profile=json.loads((source_job/'native_mapping.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(folder/'source_review.blend'),load_ui=False)
    human=bpy.data.objects['Human'];rig=bpy.data.objects['Human.rig'];converted=bpy.data.objects['UCC_Godot_Private_Character']
    keys=converted.data.shape_keys;animation=keys.animation_data;action=animation.action
    if (len(bpy.data.actions)!=2 or len(action.slots)!=1 or animation.action_slot!=action.slots[0]
            or len(animation.drivers) or len(animation.nla_tracks) or animation.action_blend_type!='REPLACE'
            or animation.action_influence!=1. or list(action.frame_range)!=[1.,300.]
            or len(keys.key_blocks)!=313 or len(rig.data.bones)!=163):
        raise ValueError('Saved candidate lost complete bound morph/skeleton Actions')
    expected={keys.key_blocks[name].path_from_id('value'):frame for frame,name in enumerate(report['corrective_morphs'],1)}
    curves=all_curves(action)
    if len(curves)!=300 or {curve.data_path for curve in curves}!=set(expected):raise ValueError('Saved corrective channels differ')
    for curve in curves:
        frame=expected[curve.data_path];points=[(number,1. if number==frame else 0.) for number in (frame-1,frame,frame+1) if 1<=number<=300]
        if (curve.array_index!=0 or curve.mute or curve.modifiers or curve.extrapolation!='CONSTANT'
                or len(curve.keyframe_points)!=len(points) or any(list(point.co)!=[float(number),value] or point.interpolation!='LINEAR'
                    for point,(number,value) in zip(curve.keyframe_points,points))):
            raise ValueError('Saved corrective keyframes differ')
    world=[float(value) for row in rig.matrix_world for value in row]
    observed=array('f');rows=[];maximum=0.
    for frame in range(1,301):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        for index,name in enumerate(report['corrective_morphs'],1):
            if abs(keys.key_blocks[name].value-(1. if index==frame else 0.))>1e-7:raise ValueError('Saved corrective playback weight differs')
        if any(keys.key_blocks[name].value!=0. for name in report['canonical_morphs']):raise ValueError('Saved neutral canonical control changed')
        poses=[[float(value) for row in rig.matrix_world@rig.pose.bones[pair['target']].matrix for value in row] for pair in profile['pairs']]
        _,skin_sha=_evaluated_vertices(bpy,human);source_row=timeline['full_timeline_frames'][frame-1]
        if skin_sha!=source_row['evaluated_sha256'] or pose_digest(world,poses)!=source_row['target_pose_sha256']:
            raise ValueError('Saved candidate changed native source corrected skin or poses')
        source=np.array(evaluated(bpy,human),dtype=np.float32)
        actual=np.array(evaluated(bpy,converted),dtype=np.float64)
        error=float(np.max(np.linalg.norm(actual-source.astype(np.float64),axis=1)))
        if not np.isfinite(error) or error>1e-6:raise ValueError('Fresh saved corrected candidate exceeds fixed Blender error')
        observed.extend(float(value) for value in source.reshape(-1));maximum=max(maximum,error)
        rows.append({'frame':frame,'converted_max_error_m':error})
    if observed.tobytes()!=(folder/'source_positions.bin').read_bytes():raise ValueError('Fresh corrected source bytes differ')
    if any(sha256((folder/name).read_bytes()).hexdigest()!=value for name,value in files.items()):raise ValueError('Reopening changed staged files')
    return {'status':'FRESH_NATIVE300_CORRECTIVE_SOURCE_ACTIONS_AND_SURFACE_VERIFIED','blender_version':bpy.app.version_string,
        'bound_files':files,'frames':rows,'source_frames':300,'canonical_morphs':12,'corrective_morphs':300,'bones':163,
        'max_conversion_error_m':maximum,'independent_source_bytes_exact':True,
        'native_corrected_skin_and_target_pose_hashes_exact':True,'engine_import_verified':False,'visual_quality_approved':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);result=run(args.folder)
    with args.out.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(result['status'],flush=True)
