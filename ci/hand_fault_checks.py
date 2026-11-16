"""Rehashed saved-scene faults against the normal independent hand worker."""
from hashlib import sha256
import json
from pathlib import Path

from ucc.core.hand_parts import TARGETS
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def verify_scene_faults(blender,worker,stage_dir,fault_dir,jobs):
    request=json.loads((stage_dir/'request.json').read_text(encoding='utf-8'))
    if request['operation']!='stage_mpfb_hand_revision':raise RuntimeError('Expected a normal hand revision stage')
    options=request['options']
    names=['candidate.blend','original.blend','hand_manifest.json','basemesh_vertex_groups.json',
           *[t.filename for t in TARGETS],'hand-shorter.blend','hand-longer.blend']
    inputs={name:stage_dir/name for name in names}
    protected={str(p):digest(p) for p in [*inputs.values(),stage_dir/'revised_human.blend',stage_dir/'hand_revision_report.json']}
    runner=BlenderJobRunner(blender,jobs,worker)
    original_report=stage_dir/'hand_revision_report.json'
    positive_options=dict(options,revised_sha256=digest(stage_dir/'revised_human.blend'),revision_report_sha256=digest(original_report))
    positive=JobRequest.new('verify_mpfb_hand_revision',input_project='candidate.blend',options=positive_options)
    accepted,_=runner.run(positive,staged_inputs={**inputs,'revised_human.blend':stage_dir/'revised_human.blend',
                         'hand_revision_report.json':original_report},timeout_s=180)
    if (accepted.details.get('verified_reopen') is not True or accepted.details.get('all40_restores_exact') is not True
            or len(accepted.details.get('skin_poses',[]))!=20):raise RuntimeError('Positive hand reference was not independently accepted')
    print('POSITIVE_NORMAL_SAVED_HAND_REFERENCE_ACCEPTED',flush=True)
    faults=json.loads((fault_dir/'faults.json').read_text(encoding='utf-8'));rejected={}
    for fault,row in faults.items():
        scene=fault_dir/row['file']
        if scene.parent.resolve()!=fault_dir.resolve() or digest(scene)!=row['sha256']:
            raise RuntimeError('Fault fixture identity/path mismatch')
        report=json.loads(original_report.read_text(encoding='utf-8'));report['scene_sha256']=row['sha256']
        report_path=fault_dir/(fault+'-report.json')
        with report_path.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,allow_nan=False)
        checked=dict(options,revised_sha256=row['sha256'],revision_report_sha256=digest(report_path))
        job=JobRequest.new('verify_mpfb_hand_revision',input_project='candidate.blend',options=checked)
        try:
            runner.run(job,staged_inputs={**inputs,'revised_human.blend':scene,'hand_revision_report.json':report_path},timeout_s=180)
        except WorkerFailure as error:
            message=str(error)
            if not any(text in message for text in (
                'Saved hand geometry, keys, rig or unrelated state differs from independent reproduction',
                'non-neutral rest-local pose')):raise
            rejected[fault]={'semantic_rejection':message.split('; staged logs:')[0],
                             'scene_and_report_rehashed':True,'worker_job_id':job.job_id}
        else:raise RuntimeError('Rehashed real hand scene fault was accepted: '+fault)
        print('REAL_REHASHED_HAND_SCENE_FAULT_REJECTED',fault,flush=True)
    if len(rejected)!=8 or protected!={p:digest(p) for p in protected}:
        raise RuntimeError('Hand fault coverage incomplete or protected source changed')
    return {'positive_reference_accepted':True,'positive_pose_checks':40,
            'rehashed_saved_scene_faults':rejected,'protected_inputs_unchanged':True}
