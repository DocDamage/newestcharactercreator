"""Original idle measurement/authoring/independent reopen; no existing clip inputs."""
from pathlib import Path
from typing import Any
from blender_bridge.idle_authoring_measure import measure, check_frame
from blender_bridge.idle_authoring_policy import (
    SOURCE_PROFILE, QUALITY, checked_job, document, unchanged, write_document, output_record, require,
    canonical_digest,
)
from blender_bridge.idle_authoring_scene import solve_baseline, bake_and_save
from blender_bridge.idle_authoring_verify import expected_timeline, verify_review, verify_fbx


def _frame_context(bpy,root,job):
    request,inputs=checked_job(job,root)
    frame,human,rig,targets=measure(bpy,root,request.project,inputs['candidate.blend'])
    if job['operation']!='inspect_authored_idle_target':
        declared=document(root,'idle_anatomical_frame.json',request.anatomical_frame_sha256)
        check_frame(frame,declared)
        require(frame['target']==request.target.to_dict(),'Actual measured idle target differs from authoring intent')
    unchanged(root,inputs)
    return request,inputs,frame,human,rig,targets


def _summary(job,request,frame,files,status):
    inspect=job['operation']=='inspect_authored_idle_target'
    return {'schema_version':1,'status':status,'operation':job['operation'],
            'request_sha256':request.sha256,'target':frame['target'],
            'anatomical_frame_sha256':canonical_digest(frame),'source_profile':SOURCE_PROFILE,
            'skeleton_fingerprint':frame['skeleton_fingerprint'],
            'bone_count':len(frame['anatomy']['bones']),'outputs':files,
            'sample_count':0 if inspect else 300,'source_first_frame':None if inspect else 2,
            'source_last_frame':None if inspect else 301,'fps':None if inspect else 30,**QUALITY}


def inspect_target(bpy: Any, root: Path, job: dict) -> dict:
    require(job.get('operation')=='inspect_authored_idle_target','Wrong idle inspection handler')
    request,inputs,frame,_,_,_=_frame_context(bpy,root,job)
    try:
        output=write_document(root,'idle_anatomical_frame.json',frame)
        report={'schema_version':1,'status':'ACTUAL_NEUTRAL_IDLE_ANATOMY_MEASURED',
            'inspection_request_sha256':request.sha256,'target':frame['target'],
            'anatomical_frame':output,'source_profile':SOURCE_PROFILE,
            'skeleton_fingerprint':frame['skeleton_fingerprint'],
            'bone_count':len(frame['anatomy']['bones']),'existing_action_count':0,
            'existing_motion_read':False,'authoring_performed':False,**QUALITY}
        files=[output,write_document(root,'idle_inspection_report.json',report)]
        return _summary(job,request,frame,files,'ACTUAL_NEUTRAL_IDLE_ANATOMY_MEASURED')
    finally:unchanged(root,inputs)


def _recipe(request,frame,construction):
    return {'schema_version':1,'profile':SOURCE_PROFILE,'authoring_request_sha256':request.sha256,
            'anatomical_frame_sha256':canonical_digest(frame),'target':frame['target'],
            'skeleton_fingerprint':frame['skeleton_fingerprint'],'construction':construction,
            'source_samples':300,'source_first_frame':2,'source_last_frame':301,'fps':30,
            'review_first_frame':1,'review_last_frame':300,'virtual_source_frame302_stored':False,
            'existing_motion_read':False,'armature_only_source':True,**QUALITY}


def author_source(bpy: Any, root: Path, job: dict) -> dict:
    require(job.get('operation')=='author_original_idle_source','Wrong idle authoring handler')
    request,inputs,frame,human,rig,targets=_frame_context(bpy,root,job)
    try:
        construction=solve_baseline(rig,frame,request)
        # Measure actual directly evaluated standing recipe before creating any Action.
        _,numeric=expected_timeline(bpy,human,rig,targets,frame,construction,request)
        recipe=write_document(root,'authored_idle_recipe.json',_recipe(request,frame,construction))
        unchanged(root,inputs)
        bake_and_save(bpy,root,human,rig,construction,request)
        source=output_record(root,'original_idle.fbx');review=output_record(root,'authored_idle_review.blend')
        report={'schema_version':1,'status':'ORIGINAL_IDLE_SOURCE_AUTHORED_PENDING_INDEPENDENT_REOPEN',
            'authoring_request_sha256':request.sha256,'anatomical_frame_sha256':canonical_digest(frame),
            'target':frame['target'],'skeleton_fingerprint':frame['skeleton_fingerprint'],
            'sample_count':300,'numeric_observations':numeric,'files':[source,review,recipe],
            'saved_reopen_verified':False,'private_geometry_metrics_not_for_model_output':True,**QUALITY}
        files=[source,review,recipe,write_document(root,'authored_idle_report.json',report)]
        return _summary(job,request,frame,files,'ORIGINAL_IDLE_SOURCE_AUTHORED_PENDING_INDEPENDENT_REOPEN')
    finally:unchanged(root,inputs)


def verify_source(bpy: Any, root: Path, job: dict) -> dict:
    require(job.get('operation')=='verify_authored_idle_source','Wrong idle verification handler')
    request,inputs,frame,human,rig,targets=_frame_context(bpy,root,job)
    try:
        construction=solve_baseline(rig,frame,request)
        declared=document(root,'authored_idle_recipe.json',job['options']['recipe_sha256'])
        require(declared==_recipe(request,frame,construction),'Saved recipe differs from independently solved actual anatomy')
        expected,numeric=expected_timeline(bpy,human,rig,targets,frame,construction,request)
        unchanged(root,inputs)
        review=verify_review(bpy,root,frame,construction,request,targets,expected)
        unchanged(root,inputs)
        source=verify_fbx(bpy,root,frame,expected,job['options']['source_sha256'])
        unchanged(root,inputs)
        report={'schema_version':1,'status':'ORIGINAL_IDLE_FRESH_REOPEN_FULL300_VERIFIED_NOT_USABLE_APPROVED',
            'authoring_request_sha256':request.sha256,'anatomical_frame_sha256':canonical_digest(frame),
            'target':frame['target'],'skeleton_fingerprint':frame['skeleton_fingerprint'],
            'direct_recipe':numeric,'saved_review':review,'actual_fbx_source':source,
            'original_inputs_preserved':True,'private_geometry_metrics_not_for_model_output':True,
            'required_quality_execution':{'root_neutral_measured':True,'lower_chain_neutral_measured':True,
                'neutral_sole_drift_measured':True,'full300_finite_zero_translation_unit_scale':True,
                'analytic_seam_value_measured':True,'analytic_seam_first_derivative_measured':True,
                'wrapped_same_interval_velocities_measured':True,
                'palmar_skin_surface_normal_verified':False,'hand_digit_body_clearance_measured':False,
                'human_visual_review_performed':False,'complete_required_quality_verified':False},
            'independent_root_nine_worker_and_human_review_required':True,**QUALITY}
        files=[source['source_snapshot'],write_document(root,'authored_idle_verification.json',report)]
        result=_summary(job,request,frame,files,'ORIGINAL_IDLE_FRESH_REOPEN_FULL300_VERIFIED_NOT_USABLE_APPROVED')
        result.update(sample_count=300,source_first_frame=2,source_last_frame=301,fps=30)
        return result
    finally:unchanged(root,inputs)
