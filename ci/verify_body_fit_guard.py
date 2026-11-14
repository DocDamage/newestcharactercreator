"""Original-source stable-face positive guard and rehashed-report negatives."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path

from ucc.jobs.body_contact_review import review_body_contact_areas,review_complete_anatomical_safety
from ucc.jobs.body_fit_guard import require_body_fit_guard
from ucc.jobs.enclosure_fit_guard import require_enclosure_fit_guard
from ucc.jobs.complete_trunk_fit_guard import require_complete_trunk_fit_guard
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner,WorkerFailure


def verify_body_fit_guard(blender,store,preview,original,fitted,source,permission,folder):
    folder.mkdir(exist_ok=False);repo=Path(__file__).resolve().parents[1]
    args=dict(source_fbx=source,permission=permission,blender_exe=blender,worker_script=repo/'blender_bridge/entrypoint.py')
    project=store.load();digest=lambda p:sha256(Path(p).read_bytes()).hexdigest()
    originals=[source,store.root/project.master_blend,store.root/'project.ucc.json',
        Path(preview.private_visual_review_blend),Path(preview.private_timeline),Path(fitted.fitted_preview.fit_policy_used),
        Path(fitted.fitted_preview.private_fitted_scene),Path(fitted.fitted_preview.private_timeline)]
    before=[digest(p) for p in originals]
    native=review_body_contact_areas(store,preview,original,**args)
    paired=review_complete_anatomical_safety(store,preview,original,fitted=fitted,timeout_s=1800,**args)
    guard=require_body_fit_guard(paired)
    enclosure_guard=require_enclosure_fit_guard(paired);complete_guard=require_complete_trunk_fit_guard(paired)
    if (native.areas.status!='CHECKED' or len(native.areas.original)!=300 or native.areas.fitted is not None or
        guard.frames_checked!=300 or paired.areas.new_area_frames or paired.areas.more_hand_pair_frames):
        raise RuntimeError('Original stable-face contact challenge did not pass its complete guard')
    from ci.complete_surface_forgery import forged_complete_contact
    full_forged=forged_complete_contact(paired,fitted.cache,folder/'coherent-false-fitted-complete-contact.json',variant='fitted')
    def negative(case):
        label,review=case;root=Path(review.private_report).parent;bad=json.loads(Path(review.private_report).read_text())
        if label=='native_body':bad['body_contacts']['original']['frames'][7]['skin_sha256']='0'*64
        elif label!='fitted_full_trunk':
            bad['polygons'][0]=list(reversed(bad['polygons'][0]))
            bad['polygon_topology_sha256']=sha256(json.dumps(bad['polygons'],separators=(',',':')).encode()).hexdigest()
        fake=folder/(label+'-rehashed.json');fake.write_text(json.dumps(bad))
        names=['candidate.blend','review_motion.blend','target_timeline.json','source_snapshot.json','native_mapping.json']
        if label!='native_body':names+=['contact_fit.json','fitted_motion.blend','fitted_timeline.json']
        staged={n:root/n for n in names};staged['body_contacts.json']=fake
        options={**dict(review.bindings),'body_review_sha256':digest(fake)}
        operation='verify_native_body_areas' if label=='native_body' else 'verify_fitted_body_areas'
        expected_error='Fresh saved-scene stable contact areas differ'
        if label=='fitted_full_trunk':
            staged['body_contacts.json']=Path(review.private_report)
            staged['central_enclosure.json']=Path(review.private_enclosure_report)
            staged['full_trunk_contacts.json']=full_forged
            options.update(body_review_sha256=review.report_sha256,enclosure_review_sha256=review.enclosure_report_sha256,
                full_trunk_review_sha256=digest(full_forged))
            operation='verify_fitted_complete_anatomical_safety';expected_error='Fresh complete anatomical surface/enclosure evidence differs'
        try:
            BlenderJobRunner(blender,store.root/'.ucc-jobs',repo/'blender_bridge/entrypoint.py').run(
                JobRequest.new(operation,input_project='candidate.blend',options=options),timeout_s=1800,staged_inputs=staged)
        except WorkerFailure as error:
            if expected_error not in str(error):raise
            return label
        raise RuntimeError('Rehashed stable-body-area report accepted: '+label)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejected=list(pool.map(negative,(('native_body',native),('fitted_polygon_order',paired),('fitted_full_trunk',paired))))
    from ci.verify_area_candidate import verify_area_candidate_negatives
    area_candidates=verify_area_candidate_negatives(blender,store,original,native,folder/'area-candidate-negatives')
    hand_candidates=verify_area_candidate_negatives(blender,store,original,native,folder/'hand-candidate-negatives',
        operation='propose_native_hand_contact_fit')
    if store.load()!=project or [digest(p) for p in originals]!=before:
        raise RuntimeError('Stable-face fitting guard changed source/master/project/policy/scene originals')
    return {'status':'REAL_ORIGINAL_BODY_FIT_GUARD_PASSED','source_frames':300,'fitted_frames':300,
        'scope':'ORIGINAL_CI_SOURCE_ON_REAL_MPFB_NOT_OWNER_OR_PACK_COMPATIBILITY','source_only_and_paired_reproduced':True,
        'all_cached_highlight_triangles_resolved_to_stable_polygons':True,'guard_policy':guard.policy,
        'new_contact_area_frames':len(paired.areas.new_area_frames),'more_per_hand_pair_frames':len(paired.areas.more_hand_pair_frames),
        'complete_trunk_guard':{'policy':complete_guard.policy,'frames_checked':complete_guard.frames_checked,
            'new_area_frames':len(paired.full_trunk.new_area_frames),'more_per_hand_pair_frames':len(paired.full_trunk.more_hand_pair_frames),
            'enclosure_frames_checked':enclosure_guard.frames_checked,'coherent_rehashed_fitted_contact_rejected':'fitted_full_trunk' in rejected},
        'rehashed_false_reports_rejected':rejected,'area_candidate_negatives':area_candidates,'hand_candidate_negatives':hand_candidates,
        'original_inputs_unchanged':True,'assets_uploaded':False,
        'contact_quality_approved':False,'engine_import_verified':False}
