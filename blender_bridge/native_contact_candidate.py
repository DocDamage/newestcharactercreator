"""Propose an actual-skin-tested bounded fit, without approving or saving motion."""
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from blender_bridge.contact_candidate_policy import ALGORITHM,candidate_layout,coarse_vectors,refine_vectors,trial_policy
from blender_bridge.native_contact_probe import CandidateProbe
from blender_bridge.native_surface_verify import verify_surface_review
from blender_bridge.native_review_reopen import scene_objects,digest
from blender_bridge.native_inputs import read_json,validate_profile
from blender_bridge.native_rest_frames import capture_rest_frames
from blender_bridge.native_fit_policy import BASE_HASHES

OPERATION='propose_native_contact_fit'


def checked_candidate_job(job: dict) -> dict:
    options=job['options'];keys=BASE_HASHES|{'surface_review_sha256'}
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=keys or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Contact candidate requires seven exact hashes and fixed staged inputs')
    return options


def propose_contact_fit(bpy: Any,root: Path,options: dict) -> dict:
    inputs={'candidate.blend':'master_sha256','review_motion.blend':'review_sha256','target_timeline.json':'timeline_sha256',
            'native_mapping.json':'mapping_sha256','source_snapshot.json':'snapshot_sha256','motion_contacts.json':'surface_review_sha256'}
    def unchanged():
        for name,key in inputs.items():
            path=root/name
            if path.is_symlink() or not path.is_file() or digest(path)!=options[key]:
                raise ValueError('Contact search changed a bound original: '+name)
    output=root/'proposed_contact_fit.json'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace a contact candidate')
    unchanged()
    try:
        verification=verify_surface_review(bpy,root,options)
        baseline=read_json(root/'target_timeline.json',options['timeline_sha256'],64*1024*1024)
        profile=validate_profile(read_json(root/'native_mapping.json',options['mapping_sha256'],64*1024),
            options['source_sha256'],options['snapshot_sha256'],options['master_sha256'])
        contacts=read_json(root/'motion_contacts.json',options['surface_review_sha256'],16*1024*1024)
        human,rig=scene_objects(bpy);rest=capture_rest_frames(rig);parents={n:r['parent'] for n,r in rest.items()}
        layout=candidate_layout(baseline,profile,parents,contacts);probe=CandidateProbe(bpy,human,rig,baseline,profile)
        bindings={k:options[k] for k in BASE_HASHES};observations=[];chosen=None
        changed=range(layout.start+1,layout.end)
        def evaluate(vector,frames):
            try:data,plan=trial_policy(layout,vector,bindings,baseline,profile,parents)
            except ValueError as error:return None,{'vector':vector,'pairs':5_000_001,'checked':0,'reason':str(error)}
            return data,{'vector':vector,**probe.evaluate(plan,frames)}
        for vector in coarse_vectors(layout):
            data,result=evaluate(vector,layout.critical);observations.append(result)
        best=sorted(observations,key=lambda r:(r['pairs'],sum(v*v for v in r['vector'])))[:8]
        for row in best:
            if row['pairs']==0:
                data,result=evaluate(row['vector'],changed);observations.append(result)
                if result['pairs']==0:chosen=data;break
        if chosen is None:
            for vector in refine_vectors(layout,observations):
                data,result=evaluate(vector,layout.critical);observations.append(result)
                if result['pairs']==0:
                    data,result=evaluate(vector,changed);observations.append(result)
                    if result['pairs']==0:chosen=data;break
        if chosen is None:raise ValueError('NO_BOUNDED_CONTACT_CANDIDATE_FOUND; original motion retained')
        payload=json.dumps(chosen,allow_nan=False,separators=(',',':')).encode()
        if len(payload)>512*1024:raise ValueError('Generated contact policy exceeds existing fit bound')
        unchanged()
        with output.open('xb') as stream:stream.write(payload)
        return {'status':'REAL_NATIVE_CONTACT_CANDIDATE_PROPOSED','algorithm':ALGORITHM,'bindings':dict(options),
            'source_surface_verification':verification,'target_rest_frames':rest,
            'policy':{'name':output.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},
            'source_frames_verified':layout.count,'contact_interval':[layout.first,layout.last],
            'candidate_interval':[layout.start+1,layout.end-1],
            'candidate_frames_checked':len(changed),'candidate_pose_tests':probe.tested,'candidate_trials':len(observations),
            'candidate_intersection_pairs':0,'originals_unchanged':True,
            'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    finally:unchanged()
