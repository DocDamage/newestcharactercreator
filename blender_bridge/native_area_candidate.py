"""Eight-SHA candidate search with freshly reproduced stable body-contact areas."""
from hashlib import sha256
import json

from blender_bridge.native_contact_candidate import search_candidate
from blender_bridge.contact_candidate_policy import candidate_layout
from blender_bridge.contact_area_probe import SourceAreaAudit,AreaCandidateProbe,area_critical_layout,area_trial_rank
from blender_bridge.native_surface_verify import verify_surface_review
from blender_bridge.native_review_reopen import scene_objects,digest
from blender_bridge.native_inputs import read_json,validate_profile
from blender_bridge.native_rest_frames import capture_rest_frames
from blender_bridge.native_fit_policy import BASE_HASHES

OPERATION='propose_native_area_contact_fit'
ALGORITHM='BOUNDED_CONTACT_AREA_SEARCH_V2'
FIELDS=BASE_HASHES|{'surface_review_sha256','source_body_areas_sha256'}


def checked_area_candidate_job(job):
    options=job['options']
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=FIELDS or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Area contact candidate requires eight exact hashes and fixed staged inputs')
    return options


def propose_area_contact_fit(bpy,root,options):
    inputs={'candidate.blend':'master_sha256','review_motion.blend':'review_sha256','target_timeline.json':'timeline_sha256',
        'native_mapping.json':'mapping_sha256','source_snapshot.json':'snapshot_sha256','motion_contacts.json':'surface_review_sha256',
        'source_body_areas.json':'source_body_areas_sha256'}
    def unchanged():
        for name,key in inputs.items():
            p=root/name
            if p.is_symlink() or not p.is_file() or digest(p)!=options[key]:raise ValueError('Area search changed a bound original: '+name)
    output=root/'proposed_contact_fit.json'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace an area-aware candidate')
    unchanged()
    try:
        baseline=read_json(root/'target_timeline.json',options['timeline_sha256'],64*1024*1024)
        profile=validate_profile(read_json(root/'native_mapping.json',options['mapping_sha256'],64*1024),
            options['source_sha256'],options['snapshot_sha256'],options['master_sha256'])
        expected=read_json(root/'source_body_areas.json',options['source_body_areas_sha256'],40*1024*1024)
        source=SourceAreaAudit(profile);base={k:options[k] for k in BASE_HASHES}
        surface_options={k:v for k,v in options.items() if k!='source_body_areas_sha256'}
        verification=verify_surface_review(bpy,root,surface_options,frame_observer=source.frame)
        source.verify(expected,baseline,base,verification['saved_review_verification'])
        contacts=read_json(root/'motion_contacts.json',options['surface_review_sha256'],16*1024*1024)
        human,rig=scene_objects(bpy);rest=capture_rest_frames(rig);parents={n:r['parent'] for n,r in rest.items()}
        layout=area_critical_layout(candidate_layout(baseline,profile,parents,contacts),source)
        probe=AreaCandidateProbe(bpy,human,rig,baseline,profile,source)
        observations=[]
        def diagnostic(reason):
            unchanged()
            best=[{**{k:v for k,v in r.items() if k!='pairs'},'constraint_cost':r['pairs']}
                for r in sorted(observations,key=area_trial_rank)[:8]]
            data={'schema_version':1,'algorithm':ALGORITHM,'bindings':dict(options),'reason':reason,'pose_tests':probe.tested,
                'trials':len(observations),'source_frames_verified':layout.count,
                'polygon_topology_sha256':source.inspector.polygon_sha,
                'body_area_pose_rejections':len(probe.area_guard.rejected),
                'cached_pose_queries':probe.cache_hits,
                'best_observations':best,
                'originals_unchanged':True,'contact_quality_verified':False,'engine_import_verified':False}
            with (root/'candidate_search.json').open('x') as stream:json.dump(data,stream,allow_nan=False)
        try:chosen,observations=search_candidate(layout,probe,base,baseline,profile,parents,observations=observations,
            rank_key=area_trial_rank,refinement_factors=(1.,.5,.25),learn_failed_frames=True)
        except ValueError as error:
            diagnostic(str(error)[:512])
            if 'NO_BOUNDED_CONTACT_CANDIDATE_FOUND' in str(error):raise ValueError('NO_BOUNDED_AREA_CONTACT_CANDIDATE_FOUND; original motion retained') from error
            raise
        diagnostic('CANDIDATE_PASSED_CHANGED_INTERVAL')
        changed=list(range(layout.start+1,layout.end))
        if probe.area_guard.frames!=changed:raise ValueError('Area candidate omitted complete changed-frame body coverage')
        payload=json.dumps(chosen,allow_nan=False,separators=(',',':')).encode()
        if len(payload)>512*1024:raise ValueError('Area candidate exceeds existing fit-policy bound')
        unchanged()
        with output.open('xb') as stream:stream.write(payload)
        return {'status':'REAL_NATIVE_CONTACT_CANDIDATE_PROPOSED','algorithm':ALGORITHM,'bindings':dict(options),
            'source_surface_verification':verification,'target_rest_frames':rest,
            'policy':{'name':output.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},
            'source_frames_verified':layout.count,'contact_interval':[layout.first,layout.last],
            'candidate_interval':[layout.start+1,layout.end-1],'candidate_frames_checked':len(changed),
            'candidate_pose_tests':probe.tested,'candidate_trials':len(observations),'candidate_intersection_pairs':0,
            'body_area_verification':{'policy':'NO_NEW_CENTRAL_BODY_POLYGONS_V1','source_frames_verified':layout.count,'polygon_topology_sha256':source.inspector.polygon_sha,
                'candidate_frames_checked':len(changed),'new_area_frames':0,'more_hand_pair_frames':0,
                'rejected_pose_observations':len(probe.area_guard.rejected)},
            'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
    finally:unchanged()
