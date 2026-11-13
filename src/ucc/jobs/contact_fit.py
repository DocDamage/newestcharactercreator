"""Measured candidate -> saved fit -> fresh fitted cache; original stays available."""
from pathlib import Path
from threading import Event

from ucc.animations.contact_fit import read_contact_fit,MAX_FIT_BYTES,fit_frame,verify_fitted_sequence
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy,AssetPolicyError
from ucc.preview.surface_review import validate_surface_verification
from .contact_fit_context import contact_context
from .master_preview import _digest
from .native_body import NativeBodyPreview
from .native_playback import NativePlayback
from .native_fit import fit_native_preview
from .native_fit_evidence import FLAGS,rest_parents
from .native_evidence import bound_file
from .fitted_playback import FittedComparison,prepare_fitted_playback
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .body_contact_review import review_body_contact_areas,review_anatomical_safety
from .enclosure_fit_guard import require_enclosure_fit_guard
from .body_fit_guard import require_body_fit_guard
from .source_area_context import source_area_inputs,validate_candidate_areas


def fit_measured_contacts(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                          permission: LicensePolicy,blender_exe: Path,worker_script: Path,cancel: Event | None=None,
                          timeout_s: float=900) -> FittedComparison:
    allowed,reason=permission.allow('local_preview')
    if not allowed:raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Contact fitting cancelled; original motion retained')
    ctx=contact_context(store,preview,playback,source_fbx=source_fbx,cancel=cancel,cancel_check=check_cancel)
    originals=[(p,ctx.expected[n]) for n,p in ctx.staged.items()]+[(source_fbx,preview.source_sha256),
        (store.root/'project.ucc.json',_digest(store.root/'project.ucc.json',cancel))]
    def unchanged():
        check_cancel()
        if store.load()!=ctx.project:raise ProjectConflict('Character changed during contact fitting; candidate not published')
        for path,digest in originals:
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Contact fitting source/master/review evidence changed')
    arguments=dict(source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,worker_script=worker_script,
                   cancel=cancel,timeout_s=timeout_s)
    source_review=review_body_contact_areas(store,preview,ctx.playback,**arguments);unchanged()
    area_path,area_sha=source_area_inputs(store,ctx,source_review,cancel=cancel);originals.append((area_path,area_sha))
    staged={**ctx.staged,'source_body_areas.json':area_path};expected={**ctx.expected,'source_body_areas.json':area_sha}
    options={**ctx.bindings,'surface_review_sha256':ctx.expected['motion_contacts.json'],'source_body_areas_sha256':area_sha}
    unchanged();request=JobRequest.new('propose_native_hand_contact_fit',input_project='candidate.blend',options=options)
    result,folder=BlenderJobRunner(blender_exe,store.root/'.ucc-jobs',worker_script).run(
        request,timeout_s=timeout_s,cancel=cancel,staged_inputs=staged)
    unchanged()
    if folder.is_symlink() or folder.resolve().parent!=(store.root/'.ucc-jobs').resolve():
        raise ValidationError('Contact candidate output folder is redirected')
    for name,digest in expected.items():
        path=folder/name
        if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
            raise ProjectStorageError('Contact search changed a bound staged original')
    raw=result.details
    fields={'status','algorithm','bindings','source_surface_verification','target_rest_frames','policy','source_frames_verified',
            'contact_interval','candidate_interval','candidate_frames_checked','candidate_pose_tests','candidate_trials',
            'candidate_intersection_pairs','originals_unchanged','body_area_verification'}|FLAGS
    if (type(raw) is not dict or set(raw)!=fields or raw['status']!='REAL_NATIVE_CONTACT_CANDIDATE_PROPOSED' or
        raw['algorithm']!='BOUNDED_HAND_CONTACT_AREA_SEARCH_V3' or raw['bindings']!=options or raw['originals_unchanged'] is not True or any(raw[k] is not False for k in FLAGS) or
        type(raw['source_frames_verified']) is not int or raw['source_frames_verified']!=ctx.baseline['source_frame_count'] or
        type(raw['candidate_intersection_pairs']) is not int or raw['candidate_intersection_pairs']!=0):
        raise ValidationError('Contact candidate scope, coverage or approval differs')
    validate_surface_verification(raw['source_surface_verification'],ctx.bindings,ctx.baseline,
        options['surface_review_sha256'],list(ctx.playback.cache.world_matrix))
    policy=bound_file(folder,raw['policy'],'proposed_contact_fit.json',MAX_FIT_BYTES,cancel_check=check_cancel)
    plan=read_contact_fit(policy,raw['policy']['sha256'],ctx.bindings,ctx.baseline,ctx.profile,
        rest_parents(raw['target_rest_frames'],ctx.baseline),cancel_check=check_cancel)
    flagged=ctx.playback.cache.surface_review.flagged_frames
    active=[i for i,v in enumerate(plan.offsets,1) if any(v)]
    interval=[active[0],active[-1]]
    if (type(raw['contact_interval']) is not list or any(type(v) is not int for v in raw['contact_interval']) or
        raw['contact_interval']!=[flagged[0]+1,flagged[-1]+1] or
        type(raw['candidate_interval']) is not list or any(type(v) is not int for v in raw['candidate_interval']) or
        raw['candidate_interval']!=interval or any(not any(plan.offsets[f]) for f in flagged) or
        type(raw['candidate_frames_checked']) is not int or raw['candidate_frames_checked']!=interval[1]-interval[0]+1 or
        type(raw['candidate_pose_tests']) is not int or not raw['candidate_frames_checked']<=raw['candidate_pose_tests']<=1024 or
        type(raw['candidate_trials']) is not int or not 1<=raw['candidate_trials']<=500):
        raise ValidationError('Contact candidate omitted measured crossings or actual changed-frame coverage')
    originals.append((policy,raw['policy']['sha256']));unchanged()
    validate_candidate_areas(raw['body_area_verification'],source_review,ctx.baseline['source_frame_count'],
        interval[1]-interval[0]+1,raw['candidate_pose_tests'])
    original=[r['target_global_poses'] for r in ctx.baseline['full_timeline_frames']]
    expected=[]
    for frame,poses in enumerate(original,1):
        check_cancel();expected.append(fit_frame(plan,poses,frame))
    verify_fitted_sequence(plan,original,expected);unchanged()
    fitted=fit_native_preview(store,preview,fit_policy=policy,**arguments);unchanged()
    prepared=prepare_fitted_playback(store,fitted,**arguments);unchanged()
    review=review_anatomical_safety(store,preview,ctx.playback,fitted=prepared,**arguments);unchanged()
    guard=require_body_fit_guard(review);unchanged()
    enclosure_guard=require_enclosure_fit_guard(review);unchanged()
    return FittedComparison(ctx.playback,prepared,request.job_id,str(policy),review,guard,source_review,enclosure_guard)
