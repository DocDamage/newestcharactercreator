"""Private actual native300 export prototype; never a shipping clip or asset."""
from array import array
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh
from blender_bridge.godot_outputs import export_glb,write_json
from blender_bridge.face_geometry import evaluated
from blender_bridge.expression_clip_action import all_curves
from blender_bridge.native_corrective import NAME


def digest(path):return sha256(path.read_bytes()).hexdigest()


def run(job: Path, inversion: Path, output: Path) -> dict:
    proof=json.loads((inversion/'receipt.json').read_text())
    if (proof['status']!='REAL_NATIVE300_INVERSE_CORRECTIVE_FLOAT32_FEASIBILITY_PASSED'
            or proof['actual_Blender_mesh_evaluation_verified'] is not True or proof['frames']!=300):
        raise ValueError('Require complete actual Blender corrective inversion evidence')
    for name,row in proof['private_files'].items():
        if digest(inversion/name)!=row['sha256'] or (inversion/name).stat().st_size!=row['bytes']:
            raise ValueError('Corrective inversion data changed')
    source_files={str(job/name):digest(job/name) for name in ('candidate.blend','review_motion.blend','target_timeline.json')}
    if proof['source_files_unchanged']!=source_files:raise ValueError('Inverse targets belong to another native source')
    targets=np.fromfile(inversion/'corrective_targets_blender_local.f32',dtype='<f4').reshape(300,13380,3)
    reference=np.fromfile(inversion/'source_corrected_blender_world.f32',dtype='<f4').reshape(300,13380,3)
    output.mkdir(exist_ok=False)
    bpy.ops.wm.open_mainfile(filepath=str(job/'review_motion.blend'),load_ui=False)
    human=bpy.data.objects['Human'];rig=bpy.data.objects['Human.rig']
    if len(bpy.data.actions)!=1 or list(rig.animation_data.action.frame_range)!=[1.,300.]:
        raise ValueError('Prototype needs the single complete original native Action')
    if bpy.context.scene.render.fps!=30 or bpy.context.scene.render.fps_base!=1.:
        raise ValueError('Prototype source frame rate differs')
    donor=human.copy();donor.data=human.data.copy();bpy.context.scene.collection.objects.link(donor)
    donor.modifiers.remove(donor.modifiers[NAME])
    candidate=build_godot_bind_mesh(bpy,donor,rig);converted=candidate.object
    donor_mesh=donor.data;bpy.data.objects.remove(donor,do_unlink=True);bpy.data.meshes.remove(donor_mesh)
    bind=array('f',(value for vertex in converted.data.vertices for value in (vertex.co.x,vertex.co.z,-vertex.co.y)))
    with (output/'bind_positions.bin').open('xb') as stream:bind.tofile(stream)
    keys=converted.data.shape_keys
    keys.animation_data_create();keys.animation_data.action=bpy.data.actions.new('UCC_PRIVATE_NATIVE_CORRECTIVE_SEQUENCE_PROBE')
    canonical=[key.name for key in keys.key_blocks if key.name!='Basis']
    if len(canonical)!=12 or any(key.value!=0. for key in keys.key_blocks):
        raise ValueError('Prototype bind copy is not neutral with complete canonical controls')
    corrective=[]
    for index in range(300):
        key=converted.shape_key_add(name=f'UCC_POSE_CORRECTION_V1_f{index+1:04d}',from_mix=False)
        key.data.foreach_set('co',targets[index].reshape(-1));key.slider_min=0.;key.slider_max=1.;key.value=0.
        for frame,value in ((index,0.),(index+1,1.),(index+2,0.)):
            if 1<=frame<=300:
                key.value=value
                if not key.keyframe_insert(data_path='value',frame=frame):raise ValueError('Cannot key actual corrective target')
        key.value=0.;corrective.append(key)
    for curve in all_curves(keys.animation_data.action):
        curve.extrapolation='CONSTANT'
        for point in curve.keyframe_points:point.interpolation='LINEAR'
    bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=300
    rows=[];maximum=0.;fresh=array('f')
    for frame in range(1,301):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        if any(abs(key.value-(1. if index+1==frame else 0.))>1e-7 for index,key in enumerate(corrective)):
            raise ValueError('Actual corrective Action lost exact frame weights')
        if any(keys.key_blocks[name].value!=0. for name in canonical):
            raise ValueError('Native neutral facial controls changed')
        original=np.array(evaluated(bpy,human),dtype=np.float32)
        actual=np.array(evaluated(bpy,converted),dtype=np.float64)
        if not np.array_equal(original,reference[frame-1]):raise ValueError('Fresh source differs from independently sampled exact corrected reference')
        error=float(np.max(np.linalg.norm(actual-original.astype(np.float64),axis=1)))
        if not np.isfinite(error) or error>1e-6:raise ValueError('Actual corrective key Action exceeds fixed Blender error: '+str({'frame':frame,'error':error}))
        fresh.extend(float(value) for value in original.reshape(-1));maximum=max(maximum,error)
        rows.append({'frame':frame,'converted_max_error_m':error})
        if frame%50==0:print('ACTUAL_CORRECTIVE_ACTION_FRAMES',frame,flush=True)
    with (output/'source_positions.bin').open('xb') as stream:fresh.tofile(stream)
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    exported=export_glb(bpy,output,converted,rig)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'source_review.blend'),check_existing=False)
    if any(digest(Path(path))!=value for path,value in source_files.items()):raise ValueError('Prototype changed original source inputs')
    report={**candidate.observation,**exported,'profile':'MPFB_GODOT_NATIVE_CORRECTIVE_SEQUENCE_PROBE_V1',
        'status':'REAL_NATIVE300_CORRECTIVE_ACTION_AND_GLB_STAGED_NOT_ENGINE_VERIFIED',
        'frames':300,'fps':30,'canonical_morphs':canonical,'corrective_morphs':[key.name for key in corrective],
        'total_morphs':312,'source_correction_policy':'BOUND_CORRECTIVE_SMOOTH_V1',
        'source_correction_baked_from_actual_full_surface':True,'original_source_files':source_files,
        'bind_positions_sha256':digest(output/'bind_positions.bin'),
        'positions_sha256':digest(output/'source_positions.bin'),'positions_bytes':(output/'source_positions.bin').stat().st_size,
        'review_scene_sha256':digest(output/'source_review.blend'),'blender_version':bpy.app.version_string,
        'max_source_error_m':maximum,'sample_rows':rows,'animation_verified':False,
        'source_only_catalog_upgraded':False,'nonshipping_original_diagnostic':True,
        'material_appearance_verified':False,'engine_import_verified':False,'visual_quality_approved':False}
    write_json(output/'blender_stage.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--inversion',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);print(run(args.job,args.inversion,args.out)['status'],flush=True)
