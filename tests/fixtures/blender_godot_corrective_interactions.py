"""Measure real temporal/facial corrective fidelity; completion is not a pass."""
from array import array
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from blender_bridge.expression_policy import TARGETS,keyname
from blender_bridge.expression_geometry import macro_context
from blender_bridge.face_geometry import evaluated
from blender_bridge.mpfb_service import locate_human_service,locate_target_service
from blender_bridge.native_corrective import NAME,SETTINGS


def digest(path):return sha256(path.read_bytes()).hexdigest()


def run(folder: Path, output: Path) -> dict:
    output.mkdir(exist_ok=False)
    stage=json.loads((folder/'blender_stage.json').read_text())
    protected={str(folder/name):digest(folder/name) for name in ('source_review.blend','character.glb','blender_stage.json')}
    if protected[str(folder/'source_review.blend')]!=stage['review_scene_sha256']:
        raise ValueError('Saved corrective candidate changed')
    bpy.ops.wm.open_mainfile(filepath=str(folder/'source_review.blend'),load_ui=False)
    human=bpy.data.objects['Human'];converted=bpy.data.objects['UCC_Godot_Private_Character']
    modifier=human.modifiers[NAME]
    if not modifier.is_bind or any(getattr(modifier,name)!=value for name,value in SETTINGS.items()):
        raise ValueError('Interaction reference lost actual bound corrective policy')
    _,module=locate_human_service();targets,_=locate_target_service(module)
    _,race=macro_context(human,targets)
    roles=sorted({role for role,_,_ in TARGETS})
    def facial(parameters):
        for role,family,_ in TARGETS:
            value=float(np.float32(parameters.get(role,0.)*race[family]))
            for obj in (human,converted):obj.data.shape_keys.key_blocks[keyname(role,family)].value=value
        bpy.context.view_layer.update()
    def measure(frame,subframe,parameters,stream):
        bpy.context.scene.frame_set(frame,subframe=subframe);facial(parameters)
        source=np.array(evaluated(bpy,human),dtype=np.float32)
        actual=np.array(evaluated(bpy,converted),dtype=np.float64)
        if source.shape!=(13380,3) or actual.shape!=source.shape:raise ValueError('Interaction topology changed')
        error=float(np.max(np.linalg.norm(actual-source.astype(np.float64),axis=1)))
        if not np.isfinite(error):raise ValueError('Interaction produced nonfinite source/error')
        source.astype('<f4').tofile(stream)
        return {'frame':frame,'subframe':subframe,'max_world_error_m':error,
                'within_fixed_Blender_1um':error<=1e-6,'within_fixed_engine_10um':error<=1e-5}
    rows={};summaries={}
    try:
        with (output/'temporal_source_world.f32').open('xb') as stream:
            temporal=[]
            for frame in range(1,300):
                for phase in (.25,.5,.75):temporal.append(measure(frame,phase,{},stream))
                if frame%50==0:print('TEMPORAL_FULL_SURFACE_INTERVALS',frame,flush=True)
            rows['temporal_neutral_face']=temporal
        profiles={role:{role:.5} for role in roles};profiles['all_roles']={role:.5 for role in roles}
        for name,parameters in profiles.items():
            face_rows=[]
            with (output/('face_'+name+'_source_world.f32')).open('xb') as stream:
                for frame in range(1,301):face_rows.append(measure(frame,0.,parameters,stream))
            rows['face_'+name]=face_rows
            print('FACE_FULL_SURFACE_PROFILE_COMPLETE',name,flush=True)
    finally:
        bpy.context.scene.frame_set(1);facial({})
    for name,values in rows.items():
        worst=max(values,key=lambda row:row['max_world_error_m'])
        summaries[name]={'samples':len(values),'max_world_error_m':worst['max_world_error_m'],
            'worst_frame':worst['frame'],'worst_subframe':worst['subframe'],
            'failures_over_1um':sum(not row['within_fixed_Blender_1um'] for row in values),
            'failures_over_10um':sum(not row['within_fixed_engine_10um'] for row in values)}
    if any(digest(Path(path))!=value for path,value in protected.items()):raise ValueError('Interaction probe changed saved inputs')
    result={'status':'REAL_TEMPORAL_AND_FACIAL_CORRECTIVE_MEASUREMENTS_COMPLETE_NOT_APPROVAL',
        'blender_version':bpy.app.version_string,'source_vertices_per_sample':13380,'race_mix':race,
        'profiles':summaries,'sample_rows':rows,'saved_files_unchanged':protected,
        'complete_temporal_and_face_accuracy_verified':all(row['failures_over_10um']==0 for row in summaries.values()),
        'private_reference_files':{path.name:{'bytes':path.stat().st_size,'sha256':digest(path)} for path in output.glob('*.f32')},
        'shipping_animation_created':False,'engine_import_verified':False,'visual_quality_approved':False}
    with (output/'measurement.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);result=run(args.folder,args.out)
    print(result['status'],json.dumps(result['profiles']),flush=True)
