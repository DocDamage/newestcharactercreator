"""Original-only compatible hand gate reusing the preceding accepted face gate.

Only hand_parts_summary.json is suitable for CI artifact retention. All .blend,
GLB, worker data and private intermediate files remain in the runner workspace.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from ucc.core.storage import ProjectStore
from ucc.jobs.hand_library import build_hand_library
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.hand_storage import installed_inputs
from ci.hand_fault_checks import verify_scene_faults
from ci.hand_transaction_checks import verify_transactions,require

WORKER=ROOT/'blender_bridge/entrypoint.py'
NAMES=('short-light-narrow','middle-neutral','tall-muscular-wide')


def digest(path):return sha256(path.read_bytes()).hexdigest()


def verify(blender,source_root,out):
    out.mkdir(exist_ok=False);started=time.monotonic()
    accepted=json.loads((source_root/'custom_face_summary.json').read_text())
    require(accepted['status']=='REAL_CUSTOM_FACE_GENERATION_REFIT_80_POSES_AND_SEVEN_REHASHED_FAULTS_PASSED'
            and accepted['original_source_only'] is True,'Hand gate requires the preceding accepted original-only facial gate')
    accepted_masters={row['master_sha256'] for row in accepted['cases'].values()}
    protected={};cases={};stores={};shorter=None;middle_stage=None;data=None
    for name in NAMES:
        source=ProjectStore(source_root/name);original=source.load();path=source.root/original.master_blend
        require(not original.parts and not original.animations and digest(path) in accepted_masters,
                'Hand source is not an accepted original face-gate master')
        protected[str(source.file)]=digest(source.file);protected[str(path)]=digest(path)
        root=out/name;root.mkdir();shutil.copyfile(source.file,root/'project.ucc.json')
        destination=root/original.master_blend;destination.parent.mkdir(parents=True);shutil.copyfile(path,destination)
        store=ProjectStore(root);initial=store.load();before=store.file.read_bytes()
        if data is None:data=discover_face_data(store,blender_exe=blender,worker_script=WORKER)
        common={'blender_exe':blender,'worker_script':WORKER,'mpfb_data_dir':data}
        assets_before={key:digest(value) for key,value in installed_inputs(data).items()}
        library=build_hand_library(store,**common,expected_project_id=initial.project_id,
                                  expected_revision=initial.revision,expected_master_blend=initial.master_blend)
        require(store.file.read_bytes()==before,'Hand library registration changed character metadata')
        identity=library.library.sha256;selections=[];old_masters={}
        for selection in ('shorter','longer','neutral'):
            current=store.load();current_path=store.root/current.master_blend;old_masters[str(current_path)]=digest(current_path)
            result=apply_hand_revision(store,**common,manifest_sha256=identity,selection=selection,
                         expected_project_id=current.project_id,expected_revision=current.revision,
                         expected_master_blend=current.master_blend)
            require(result.revision is not None and result.project.revision==current.revision+1,'Hand swap did not commit once')
            require(result.project.facial_parameters==initial.facial_parameters and result.project.parameters==initial.parameters,
                    'Hand swap lost original body/face intent')
            require(result.observed['actual_skin_pose_checks']==40 and result.observed['potential_overlap_poses']==0,
                    'Hand candidate has missing pose checks or unresolved potential overlaps')
            require(old_masters=={p:digest(Path(p)) for p in old_masters},'Hand swap changed a prior immutable master')
            selections.append({'selection':selection,'master_sha256':result.observed['authoritative_master_sha256'],
                               'pose_checks':40,'potential_overlap_poses':0,'body_face_intent_preserved':True})
            if name=='middle-neutral' and selection=='shorter':
                shorter=result;middle_stage=root/'.ucc-jobs'/result.stage_job_id
                saved=store.file.read_bytes()
                no_op=apply_hand_revision(store,**common,manifest_sha256=identity,selection=selection,
                    expected_project_id=result.project.project_id,expected_revision=result.project.revision,
                    expected_master_blend=result.project.master_blend)
                require(no_op.revision is None and store.file.read_bytes()==saved,'Hand no-op invented a revision')
        require(store.load().parts==() and digest(store.root/store.load().master_blend)==digest(path),
                'Neutral hand reset did not restore original bytes and part metadata')
        require(assets_before=={key:digest(value) for key,value in installed_inputs(data).items()},'Installed hand data changed')
        cases[name]={'source_master_sha256':digest(path),'body_parameters':dict(initial.parameters),
                     'facial_parameters':dict(initial.facial_parameters),'library_assets':2,'library_skin_pose_checks':40,
                     'selections':selections,'exact_neutral_master_restoration':True,'all_previous_masters_preserved':True}
        stores[name]=(store,identity,common)
        print('REAL_ORIGINAL_HAND_ASSETS_SWAPS_AND120_POSE_CHECKS_PASSED',name,flush=True)
    store,identity,common=stores['middle-neutral']
    transactions=verify_transactions(store,identity,common,shorter,out)
    fault_dir=out/'saved-scene-faults'
    with (out/'create-saved-scene-faults.log').open('x',encoding='utf-8') as log:
        completed=subprocess.run([str(blender),'--background','--disable-autoexec','--python-exit-code','13',
             '--python',str(ROOT/'tests/fixtures/blender_hand_faults.py'),'--','--source',str(middle_stage/'revised_human.blend'),
             '--output',str(fault_dir)],stdout=log,stderr=subprocess.STDOUT,timeout=120)
    require(completed.returncode==0,'Actual hand saved-scene fault fixture failed')
    faults=verify_scene_faults(blender,WORKER,middle_stage,fault_dir,out/'fault-verifiers')
    require(protected=={p:digest(Path(p)) for p in protected},'Original face-gate project/master changed')
    return {'status':'REAL_HAND_ASSETS_THREE_BODY_FACE_CASES_SWAPS_RESET_AND_EIGHT_REHASHED_FAULTS_PASSED',
            'cases':cases,'transactions':transactions,'saved_scene_faults':faults,'already_applied_no_revision':True,
            'original_inputs_unchanged':True,'installed_assets_unchanged':True,'original_source_only':True,
            'visual_quality_approved':False,'penetration_quality_approved':False,'engine_import_verified':False,
            'elapsed_seconds':time.monotonic()-started}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--blender',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args();summary=verify(args.blender.resolve(strict=True),args.source_root.resolve(strict=True),args.outdir.resolve(strict=False))
    with (args.outdir/'hand_parts_summary.json').open('x',encoding='utf-8') as stream:json.dump(summary,stream,indent=2,allow_nan=False)
    print(summary['status'],flush=True)
