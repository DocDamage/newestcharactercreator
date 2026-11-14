"""Original-source real MPFB fitting gate; JSON diagnostics only, no owner assets."""
from pathlib import Path
from hashlib import sha256
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import argparse,json,math,subprocess,sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.humanoid_generation import generate_humanoid
from ucc.jobs.native_fit import fit_native_preview
from ucc.jobs.fitted_playback import prepare_fitted_playback
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def fit_policy(preview):
    data=preview.evidence;count=data['source_frame_count']
    profile=json.loads(Path(preview.mapping_profile_used).read_text())
    snapshot=json.loads((Path(preview.private_timeline).parent/'source_snapshot.json').read_text())
    bones={b['name']:b for b in snapshot['bones']};mapped={p['source']:p['target'] for p in profile['pairs']}
    hand=profile['landmarks']['right_hand']['source'];current=bones[hand]['parent'];ancestors=[]
    while current is not None and len(ancestors)<2:
        if current in mapped:ancestors.append(current)
        current=bones[current]['parent']
    if len(ancestors)!=2:raise RuntimeError('Original CI source does not declare a mapped arm chain')
    chain={'side':'right','upper_arm':mapped[ancestors[1]],'forearm':mapped[ancestors[0]],'hand':mapped[hand]}
    names=[p['target'] for p in profile['pairs']];indices=[names.index(chain[k]) for k in ('upper_arm','forearm','hand')]
    def geometry(frame):
        poses=frame['target_global_poses'];s,e,w=[[poses[i][j*4+3] for j in range(3)] for i in indices]
        a=[e[i]-s[i] for i in range(3)];b=[w[i]-e[i] for i in range(3)]
        la,lb=math.hypot(*a),math.hypot(*b);d=math.dist(s,w)
        angle=math.acos(max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/(la*lb))))
        return s,w,d,max(0.,la+lb-d),angle
    original=data['full_timeline_frames']
    if count!=300:raise RuntimeError('Original CI fitting challenge requires its complete 300-frame source')
    center=max(range(20,count-20),key=lambda i:geometry(original[i])[-1]);half=15
    if geometry(original[center])[-1]<math.radians(1):raise RuntimeError('Original source has no useful bent-arm fitting window')
    rows=[];maximum=0.
    for i,frame in enumerate(original):
        offset=[0.,0.,0.]
        if center-half<i<center+half:
            s,w,d,slack,_=geometry(frame);bump=math.sin(math.pi*(i-(center-half))/(2*half))**2
            # An original, small inward endpoint challenge, proportional to
            # measured extension slack; do not force IK through a straight pole.
            amount=min(.0005,.2*slack)*bump
            offset=[(s[j]-w[j])*amount/d for j in range(3)];maximum=max(maximum,amount)
        rows.append({'frame':i+1,'offset_world':offset})
    if maximum<1e-5:raise RuntimeError('Original CI fitting displacement is too small to measure meaningfully')
    raw=preview.worker_report
    bindings={**raw['bindings'],'review_sha256':raw['visual_review_blend']['sha256'],'timeline_sha256':raw['timeline']['sha256']}
    return {'schema_version':1,'policy':'BOUNDED_NATIVE_ARM_IK_V1','bindings':bindings,'coordinate_space':'BLENDER_WORLD_METERS',
            'chain':chain,'fps':data['fps'],'frames':rows,'render_frames':[1,center-half+2,center+1,center+half,count]},maximum


def verify_fit_on_preview(blender,store,preview,source,permission,folder,*,original_playback):
    folder.mkdir(exist_ok=False);policy,maximum=fit_policy(preview)
    policy_path=folder/'original-ci-fit-policy.json';policy_path.write_text(json.dumps(policy,indent=2))
    project=store.load();master=store.root/project.master_blend
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    before={str(p):digest(p) for p in (master,source,store.root/'project.ucc.json',Path(preview.private_visual_review_blend),Path(preview.private_timeline),policy_path)}
    result=fit_native_preview(store,preview,source_fbx=source,fit_policy=policy_path,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=600)
    if result.evidence['frame_count']!=300 or result.surface_review.status!='CHECKED' or result.surface_review.flagged_frames:
        raise RuntimeError('Original actual MPFB fitted skin lacks complete clearance evidence')
    original=preview.evidence['full_timeline_frames'];fitted=result.evidence['frames']
    hand=[p['target'] for p in preview.evidence['mapped_pairs']].index(policy['chain']['hand'])
    displacement=max(math.dist([a['target_global_poses'][hand][i*4+3] for i in range(3)],
                               [b['target_global_poses'][hand][i*4+3] for i in range(3)]) for a,b in zip(original,fitted))
    if displacement<1e-5:raise RuntimeError('Original real MPFB fitting did not move the actual hand endpoint')
    playback=prepare_fitted_playback(store,result,source_fbx=source,permission=permission,
        blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',timeout_s=600)
    if playback.cache.frame_count!=300:raise RuntimeError('Fitted playback cropped original full sequence')
    from ci.verify_body_fit_guard import verify_body_fit_guard
    body_guard=verify_body_fit_guard(blender,store,preview,original_playback,playback,source,permission,folder/'body-fit-guard')
    prior=store.root/'.ucc-jobs'/result.worker_job_ids[-1]
    subprocess.run([str(blender),'-b','--factory-startup','--disable-autoexec','--python-exit-code','13','--python',
        str(ROOT/'tests/fixtures/blender_native_fit_faults.py'),'--','--scene',result.private_fitted_scene,
        '--policy',str(policy_path),'--mapping',preview.mapping_profile_used,'--folder',str(folder/'faults')],check=True,timeout=90)
    names=('candidate.blend','review_motion.blend','source_snapshot.json','native_mapping.json','target_timeline.json','contact_fit.json','fitted_motion.blend')
    bad=json.loads((prior/'fitted_timeline.json').read_text());bad['frames'][7]['skin_sha256']='0'*64
    bad['frames'][7]['raw_skin_sha256']='1'*64;bad['surface_review']['frames'][7]['skin_sha256']='0'*64
    forged=folder/'rehashed-false-skin.json';forged.write_text(json.dumps(bad))
    def negative(case):
        name,reason=case;options=dict(result.verification['bindings']);options.pop('fit_report_sha256')
        staged={n:prior/n for n in names};operation='measure_native_fit'
        if name=='report':
            operation='verify_native_fit';staged['fitted_timeline.json']=forged;options['fit_report_sha256']=digest(forged)
        else:
            staged['fitted_motion.blend']=folder/'faults'/f'{name}.blend';options['fitted_sha256']=digest(staged['fitted_motion.blend'])
        try:
            BlenderJobRunner(blender,store.root/'.ucc-jobs',ROOT/'blender_bridge/entrypoint.py').run(
                JobRequest.new(operation,input_project='candidate.blend',options=options),timeout_s=600,staged_inputs=staged)
        except WorkerFailure as error:
            if reason not in str(error):raise
            return name
        raise RuntimeError('Real fitted-scene corruption was accepted: '+name)
    cases=(('helper_ulp','unkeyed helper'),('weight_ulp','exact weights'),('deform_flag','bone controls'),('rest_roll','rest/roll'),('action','declared bounded trajectory'),('polygon','source topology'),('report','measurement differs'))
    with ThreadPoolExecutor(max_workers=2) as pool:rejected=list(pool.map(negative,cases))
    from ci.verify_hand_fit import verify_hand_fit
    hand_fit=verify_hand_fit(blender,store,preview,source,permission,folder/'hand-orientation',policy)
    if before!={p:digest(Path(p)) for p in before} or store.load()!=project:
        raise RuntimeError('Original source/master/project changed during real fitting gate')
    return {'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_OR_PACK_COMPATIBILITY','frames':300,'mapped_joints':len(preview.evidence['mapped_pairs']),
        'actual_endpoint_displacement_world':displacement,'declared_max_endpoint_offset_world':maximum,
        'source_fk_separate':True,'all_corrected_raw_skin_and_topology_reproduced':True,'private_images_decoded':15,
        'fitted_playback':{'frames':playback.cache.frame_count,'packed_bytes':len(playback.cache.packed),
            'all_vertex_and_triangle_hashes_checked':True,'fresh_saved_scene_verified':True,'gpu_playback_tested':False},
        'application_angular_audit':result.angular_audit,'real_rehashed_scene_report_faults_rejected':rejected,
        'stable_body_fit_guard':body_guard,
        'bounded_hand_orientation':hand_fit,
        'originals_unchanged':True,'contact_quality_approved':False,'engine_import_verified':False}


def verify(blender,root,contact_candidate_check=False):
    from ci.verify_native_body import verify_native_body
    root.mkdir(parents=True,exist_ok=False);store=ProjectStore(root/'project')
    project=store.save(CharacterProject.new('Original native fitting CI'))
    project=store.save(replace(project,parameters=tuple(sorted({'height':.66,'muscle':.76,'weight':.33}.items())),revision=project.revision+1),expected_revision=project.revision)
    generate_humanoid(store,blender_exe=blender,worker_script=ROOT/'blender_bridge/entrypoint.py',
        expected_project_id=project.project_id,expected_revision=project.revision,timeout_s=300)
    body=verify_native_body(blender,store,root/'original-native-source',hip_anchor=True,corrective=True,
                           neutral_reference=True,include_hands=True,fit_check=True)
    summary={'status':'REAL_ORIGINAL_NATIVE_FITTING_GATE_PASSED','native_body':body,'bounded_fit':body['bounded_target_fit_contract'],
             'assets_uploaded':False,'engine_import_verified':False}
    if contact_candidate_check:
        from ci.verify_contact_candidate import verify_candidate_negatives
        summary['contact_candidate_negative_contract']=verify_candidate_negatives(blender,store,root/'contact-candidate-negatives')
    (root/'native_fit_summary.json').write_text(json.dumps(summary,indent=2));return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--blender',type=Path,required=True);parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--contact-candidate-check',action='store_true')
    args=parser.parse_args();summary=verify(args.blender,args.outdir,args.contact_candidate_check)
    print('REAL_ORIGINAL_NATIVE_FITTING_GATE_PASSED',summary['bounded_fit']['frames'],flush=True)
