"""Original-source real MPFB hand-policy gate; aggregate JSON only."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import math
import subprocess

from ucc.jobs.native_fit import fit_native_preview
from ucc.jobs.fitted_playback import prepare_fitted_playback
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure

ROOT=Path(__file__).resolve().parents[1]


def verify_hand_fit(blender,store,preview,source,permission,folder,arm_policy,*,body_shape=False):
    folder.mkdir(exist_ok=False)
    policy=deepcopy(arm_policy)
    policy['policy']='BOUNDED_NATIVE_BODY_SHAPE_IK_V3' if body_shape else 'BOUNDED_NATIVE_ARM_HAND_IK_V2'
    center=max(range(len(policy['frames'])),key=lambda i:math.hypot(*policy['frames'][i]['offset_world']))
    for i,row in enumerate(policy['frames']):
        bump=math.cos((i-center)*math.pi/40)**2 if abs(i-center)<20 else 0.
        row['hand_rotation_local_degrees']=[v*bump for v in (.3,-.2,.4)]
    path=folder/'original-hand-fit.json';path.write_text(json.dumps(policy))
    project=store.load()
    inputs=(source,store.root/project.master_blend,store.root/'project.ucc.json',path,
            Path(preview.private_timeline),Path(preview.private_visual_review_blend))
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    before={p:digest(p) for p in inputs}
    result=fit_native_preview(store,preview,source_fbx=source,fit_policy=path,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=900)
    if result.evidence['policy']!=policy['policy'] or result.evidence['frame_count']!=300 or result.surface_review.flagged_frames:
        raise RuntimeError('Original hand fit lacks complete saved-pose/skin verification')
    original=preview.evidence['full_timeline_frames'];fitted=result.evidence['frames']
    hand=[p['target'] for p in preview.evidence['mapped_pairs']].index(policy['chain']['hand'])
    maximum=max(max(abs(a['target_global_poses'][hand][i]-b['target_global_poses'][hand][i]) for i in (0,1,2,4,5,6,8,9,10))
                for a,b in zip(original,fitted))
    if maximum<.001:raise RuntimeError('Hand policy did not change the actual saved hand orientation')
    playback=prepare_fitted_playback(store,result,source_fbx=source,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=900)
    if playback.cache.frame_count!=300:raise RuntimeError('Hand-policy cache cropped the full sequence')
    faults=folder/'faults'
    subprocess.run([str(blender),'-b','--factory-startup','--disable-autoexec','--python-exit-code','13','--python',
        str(ROOT/'tests/fixtures/blender_native_fit_faults.py'),'--','--scene',result.private_fitted_scene,
        '--policy',str(path),'--mapping',preview.mapping_profile_used,'--folder',str(faults),'--cases','action'],check=True,timeout=90)
    prior=store.root/'.ucc-jobs'/result.worker_job_ids[-1]
    names=('candidate.blend','review_motion.blend','source_snapshot.json','native_mapping.json','target_timeline.json','contact_fit.json')
    staged={n:prior/n for n in names};staged['fitted_motion.blend']=faults/'action.blend'
    options=dict(result.verification['bindings']);options.pop('fit_report_sha256');options['fitted_sha256']=digest(staged['fitted_motion.blend'])
    try:
        BlenderJobRunner(blender,store.root/'.ucc-jobs',ROOT/'blender_bridge/entrypoint.py').run(
            JobRequest.new('measure_native_fit',input_project='candidate.blend',options=options),timeout_s=900,staged_inputs=staged)
    except WorkerFailure as error:
        if 'declared bounded trajectory' not in str(error):raise
    else:raise RuntimeError('Rehashed actual hand-Action corruption was accepted')
    if before!={p:digest(p) for p in inputs} or store.load()!=project:
        raise RuntimeError('Hand-policy test changed original inputs')
    return {'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_PACK_COMPATIBILITY',
        'policy':policy['policy'],'frames':300,'hand_orientation_changed':True,
        'endpoint_challenge_world':max(math.hypot(*r['offset_world']) for r in policy['frames']),
        'large_body_shape_displacement_verified':False,
        'all_saved_poses_raw_corrected_skin_topology_reproduced':True,'private_images_decoded':15,
        'full_fitted_cache_verified':True,'rehashed_hand_action_rejected':True,
        'application_angular_audit':result.angular_audit,'originals_unchanged':True,
        'body_contact_quality_approved':False,'engine_import_verified':False}
