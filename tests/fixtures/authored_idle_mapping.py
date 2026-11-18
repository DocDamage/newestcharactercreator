"""NONSHIPPING invented matrices/receipts; NEVER actual/native/rights proof."""
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
import json
import math
import struct
from uuid import UUID

from fixtures.authored_idle_contract import request
from ucc.animations.authored_idle_mapping import QUALITY, SOURCE_PROFILE, FRAME_PROFILE, STATUS, VERIFY
from ucc.animations.fbx_snapshot import CONVENTION, IMPORT_OPTIONS


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def matrix(y):
    return [1.,0.,0.,0.,0.,1.,0.,y,0.,0.,1.,0.,0.,0.,0.,1.]


def pose_signature(sample):
    digest = sha256()
    for values in [sample['armature_world'], *sample['poses']]:
        digest.update(struct.pack('<16q',*(round(v*1_000_000) for v in values)))
    return digest.hexdigest()


def record(name, payload):
    return {'name':name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()}


@lru_cache(maxsize=1)
def evidence():
    parents = {'root':None,'spine05':'root','spine03':'spine05','spine01':'spine03',
        'neck01':'spine01','neck02':'neck01','head':'neck02'}
    for side in ('L','R'):
        parent = 'spine01'
        for name in ('clavicle','shoulder01','upperarm01','upperarm02','lowerarm01','lowerarm02','wrist'):
            full = name+'.'+side; parents[full] = parent; parent = full
        for digit in range(1,6):
            parent = 'wrist.'+side
            for joint in range(0 if digit > 1 else 1,4):
                full = f'finger{digit}-{joint}.{side}'; parents[full] = parent; parent = full
        parent = 'root'
        for name in ('pelvis','upperleg01','upperleg02','lowerleg01','lowerleg02','foot','toe3-1'):
            full = name+'.'+side; parents[full] = parent; parent = full
    for index in range(163-len(parents)):
        parents[f'NONSHIPPING_identity_helper{index:03d}'] = 'root'
    depths = {}
    bones = []
    for name,parent in parents.items():
        depth = depths[parent]+1 if parent else 0; depths[name] = depth
        y = depth*.1
        bones.append({'name':name,'parent':parent,'head':[0.,y,0.],
                      'tail':[0.,y+.05,0.],'matrix':matrix(y)})
    measured = [{'name':b['name'],'parent':b['parent'],'head_world':b['head'],
        'tail_world':b['tail'],'rest_local':b['matrix'],'rest_world':b['matrix']}
        for b in sorted(bones,key=lambda item:(depths[item['name']],item['name']))]
    target_request = request()
    fingerprint = sha256(encoded({'profile':SOURCE_PROFILE,
        'bones':[{'name':b['name'],'parent':b['parent']} for b in measured]})).hexdigest()
    frame = {'schema_version':1,'profile':FRAME_PROFILE,'target':target_request.target.to_dict(),
        'source_profile':SOURCE_PROFILE,'skeleton_fingerprint':fingerprint,
        'anatomy':{'axes':{},'hands':{},'bones':measured},'sole_patches':{},
        'neutral':{'rig_world':matrix(0.),'human_world':matrix(0.),'overflow_marker':0.0}}
    frame_json = encoded(frame)
    target_request = replace(target_request, anatomical_frame_sha256=sha256(frame_json).hexdigest())
    flags = dict.fromkeys(QUALITY,False)
    recipe = {'schema_version':1,'profile':SOURCE_PROFILE,'authoring_request_sha256':target_request.sha256,
        'anatomical_frame_sha256':target_request.anatomical_frame_sha256,'target':target_request.target.to_dict(),
        'skeleton_fingerprint':fingerprint,'construction':{},'source_samples':300,'source_first_frame':2,
        'source_last_frame':301,'fps':30,'review_first_frame':1,'review_last_frame':300,
        'virtual_source_frame302_stored':False,'existing_motion_read':False,'armature_only_source':True,**flags}
    recipe_json = encoded(recipe)
    frames = []
    head = next(i for i,b in enumerate(bones) if b['name']=='head')
    for index in range(300):
        poses = [list(b['matrix']) for b in bones]
        angle = .01*math.sin(2*math.pi*index/300)
        poses[head][0] = poses[head][5] = math.cos(angle)
        poses[head][1] = -math.sin(angle); poses[head][4] = math.sin(angle)
        sample = {'frame':index+2,'armature_world':matrix(0.),'poses':poses}
        sample['pose_sha256'] = pose_signature(sample); frames.append(sample)
    snapshot = {'schema_version':1,'convention':CONVENTION,'source_sha256':'2'*64,
        'blender_version':'SYNTHETIC-NO-BLENDER','import_options':IMPORT_OPTIONS,
        'rest_import_options':{**IMPORT_OPTIONS,'use_anim':False},'action':'NONSHIPPING_SYNTHETIC',
        'fps':30.,'first_frame':2,'last_frame':301,'armature_rest_world':matrix(0.),'bones':bones,
        'frames':frames,'retargeting_verified':False,'animation_visual_quality_verified':False,
        'engine_import_verified':False}
    snapshot_json = encoded(snapshot)
    verification = {'schema_version':1,'status':STATUS,'authoring_request_sha256':target_request.sha256,
        'anatomical_frame_sha256':target_request.anatomical_frame_sha256,'target':target_request.target.to_dict(),
        'skeleton_fingerprint':fingerprint,'direct_recipe':{'direct_samples':300},'saved_review':{'saved_review_samples':300},
        'actual_fbx_source':{'source_samples':300,'actual_source_frames':[2,301],
            'source_snapshot':record('authored_idle_source_snapshot.json',snapshot_json),
            'armature_only':True,'automatic_retarget_family_admission':False},
        'original_inputs_preserved':True,'private_geometry_metrics_not_for_model_output':True,
        'required_quality_execution':{**dict.fromkeys(('root_neutral_measured','lower_chain_neutral_measured',
            'neutral_sole_drift_measured','full300_finite_zero_translation_unit_scale','analytic_seam_value_measured',
            'analytic_seam_first_derivative_measured','wrapped_same_interval_velocities_measured'),True),
            **dict.fromkeys(('palmar_skin_surface_normal_verified','hand_digit_body_clearance_measured',
                'human_visual_review_performed','complete_required_quality_verified'),False)},
        'independent_root_nine_worker_and_human_review_required':True,**flags}
    verification_json = encoded(verification)
    verify_id = str(UUID(int=403))
    worker = {'protocol_version':1,'job_id':verify_id,'operation':VERIFY,'input_project':'candidate.blend',
        'options':{'request_sha256':target_request.sha256,'source_sha256':'2'*64,
            'review_sha256':'3'*64,'recipe_sha256':sha256(recipe_json).hexdigest()}}
    summary = {'schema_version':1,'status':STATUS,'operation':VERIFY,'request_sha256':target_request.sha256,
        'target':target_request.target.to_dict(),'anatomical_frame_sha256':target_request.anatomical_frame_sha256,
        'source_profile':SOURCE_PROFILE,'skeleton_fingerprint':fingerprint,'bone_count':163,
        'outputs':[record('authored_idle_source_snapshot.json',snapshot_json),
                   record('authored_idle_verification.json',verification_json)],
        'sample_count':300,'source_first_frame':2,'source_last_frame':301,'fps':30,**flags}
    result = {'protocol_version':1,'job_id':verify_id,'operation':VERIFY,'status':'ok','details':summary,'error':None}
    worker_json = encoded(worker); result_json = encoded(result)
    return target_request, dict(frame_json=frame_json,recipe_json=recipe_json,snapshot_json=snapshot_json,
        verification_json=verification_json,worker_request_json=worker_json,worker_result_json=result_json,
        source_sha256='2'*64,review_sha256='3'*64,recipe_sha256=sha256(recipe_json).hexdigest(),
        snapshot_sha256=sha256(snapshot_json).hexdigest(),worker_request_sha256=sha256(worker_json).hexdigest(),
        worker_result_sha256=sha256(result_json).hexdigest(),inspection_job_id=str(UUID(int=400)),
        verification_job_id=verify_id)


def rebind_snapshot(arguments, snapshot):
    """Coherently rehash invented witnesses; NEVER evidence of actual workers."""
    for sample in snapshot['frames']:
        sample['pose_sha256'] = pose_signature(sample)
    result = dict(arguments)
    result['snapshot_json'] = encoded(snapshot)
    result['snapshot_sha256'] = sha256(result['snapshot_json']).hexdigest()
    verification = json.loads(result['verification_json'])
    verification['actual_fbx_source']['source_snapshot'] = record('authored_idle_source_snapshot.json',result['snapshot_json'])
    result['verification_json'] = encoded(verification)
    worker_result = json.loads(result['worker_result_json'])
    worker_result['details']['outputs'] = [record('authored_idle_source_snapshot.json',result['snapshot_json']),
        record('authored_idle_verification.json',result['verification_json'])]
    result['worker_result_json'] = encoded(worker_result)
    result['worker_result_sha256'] = sha256(result['worker_result_json']).hexdigest()
    return result


def rebind_frame(request, arguments, frame_payload):
    """Coherently rehash an invented frame chain; not actual neutral admission."""
    updated = replace(request,anatomical_frame_sha256=sha256(frame_payload).hexdigest())
    result = dict(arguments,frame_json=frame_payload)
    recipe = json.loads(result['recipe_json'])
    recipe.update(anatomical_frame_sha256=updated.anatomical_frame_sha256,
                  authoring_request_sha256=updated.sha256)
    result['recipe_json'] = encoded(recipe)
    result['recipe_sha256'] = sha256(result['recipe_json']).hexdigest()
    verification = json.loads(result['verification_json'])
    verification.update(anatomical_frame_sha256=updated.anatomical_frame_sha256,
                        authoring_request_sha256=updated.sha256)
    result['verification_json'] = encoded(verification)
    worker = json.loads(result['worker_request_json'])
    worker['options'].update(request_sha256=updated.sha256,recipe_sha256=result['recipe_sha256'])
    result['worker_request_json'] = encoded(worker)
    result['worker_request_sha256'] = sha256(result['worker_request_json']).hexdigest()
    receipt = json.loads(result['worker_result_json'])
    receipt['details'].update(request_sha256=updated.sha256,
                             anatomical_frame_sha256=updated.anatomical_frame_sha256)
    receipt['details']['outputs'][1] = record('authored_idle_verification.json',result['verification_json'])
    result['worker_result_json'] = encoded(receipt)
    result['worker_result_sha256'] = sha256(result['worker_result_json']).hexdigest()
    return updated,result
