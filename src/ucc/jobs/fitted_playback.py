"""Project/license-bound fitted playback through a fresh saved-scene worker."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .body_contact_review import BodyContactReview
    from .body_fit_guard import BodyFitGuard

from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import AssetPolicyError,LicensePolicy
from ucc.preview.motion_cache import MotionCache
from ucc.preview.fitted_cache import read_fitted_cache,FIT_HASHES
from .master_preview import _digest,_master_file
from .native_evidence import bound_file,read_native_timeline
from .native_fit_evidence import read_json_record,validate_fitted_data
from .native_fit_renders import validate_fit_verification
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .native_body import NativeBodyPreview
from .native_fit import NativeFitPreview
from .native_playback import NativePlayback,prepare_native_playback


@dataclass(frozen=True,slots=True)
class FittedPlayback:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    fit_policy_sha256: str
    fitted_scene_sha256: str
    cache: MotionCache
    job_id: str
    private_manifest: str
    original_preview: NativeBodyPreview
    fitted_preview: NativeFitPreview


@dataclass(frozen=True,slots=True)
class FittedComparison:
    original: NativePlayback
    fitted: FittedPlayback
    candidate_job_id: str=''
    private_candidate_policy: str=''
    body_review: BodyContactReview | None=None
    body_fit_guard: BodyFitGuard | None=None


def prepare_fitted_comparison(store: ProjectStore,preview: NativeFitPreview,*,source_fbx: Path,
                              permission: LicensePolicy,blender_exe: Path,worker_script: Path,
                              cancel: Event | None=None,timeout_s: float=300) -> FittedComparison:
    """Use both guarded production coordinators; never publish a partial pair."""
    options=dict(source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,
                 worker_script=worker_script,cancel=cancel,timeout_s=timeout_s)
    original=prepare_native_playback(store,preview.original_preview,**options)
    fitted=prepare_fitted_playback(store,preview,**options)
    return FittedComparison(original,fitted)


def prepare_fitted_playback(store: ProjectStore,preview: NativeFitPreview,*,source_fbx: Path,
                            permission: LicensePolicy,blender_exe: Path,worker_script: Path,
                            cancel: Event | None=None,timeout_s: float=300) -> FittedPlayback:
    allowed,reason=permission.allow('local_preview')
    if not allowed:raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Fitted playback cancelled; originals unchanged')
    check_cancel();project=store.load()
    if project.master_blend is None:raise ValidationError('Fitted playback requires a saved character master')
    master,master_sha=_master_file(store,project.master_blend)
    if (project.project_id!=preview.project_id or project.revision!=preview.revision or master_sha!=preview.master_sha256):
        raise ProjectConflict('Saved character changed since target fitting')
    original=preview.original_preview;raw=original.worker_report
    options=preview.verification.get('bindings')
    if (type(options) is not dict or set(options)!=FIT_HASHES or options['source_sha256']!=preview.source_sha256 or
        options['master_sha256']!=master_sha or options['fit_sha256']!=preview.fit_policy_sha256 or
        options['fitted_sha256']!=preview.fitted_scene_sha256):
        raise ValidationError('Fitted playback identity differs from its verified candidate')
    options=dict(options);jobs=store.root/'.ucc-jobs';folder=Path(original.private_timeline).parent
    paths={
        'candidate.blend':master,'review_motion.blend':Path(original.private_visual_review_blend),
        'source_snapshot.json':folder/'source_snapshot.json','native_mapping.json':Path(original.mapping_profile_used),
        'target_timeline.json':Path(original.private_timeline),'contact_fit.json':Path(preview.fit_policy_used),
        'fitted_motion.blend':Path(preview.private_fitted_scene),'fitted_timeline.json':Path(preview.private_timeline)}
    keys=('master_sha256','review_sha256','snapshot_sha256','mapping_sha256','timeline_sha256','fit_sha256','fitted_sha256','fit_report_sha256')
    expected=dict(zip(paths,(options[k] for k in keys)))
    if jobs.is_symlink() or folder.is_symlink() or folder.resolve().parent!=jobs.resolve():
        raise ValidationError('Fitted playback original review folder is redirected')
    for name in ('review_motion.blend','target_timeline.json','fitted_motion.blend','fitted_timeline.json'):
        if paths[name].parent.is_symlink() or paths[name].resolve().parent.parent!=jobs.resolve():
            raise ValidationError('Fitted playback scene/evidence is outside its private job folder')
    watched=[(p,expected[n]) for n,p in paths.items()]+[(source_fbx,preview.source_sha256),
             (store.root/'project.ucc.json',_digest(store.root/'project.ucc.json',cancel))]
    def unchanged():
        check_cancel()
        if store.load()!=project:raise ProjectConflict('Character changed during fitted playback preparation')
        for path,digest in watched:
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Fitted playback source/master/policy/evidence changed')
    unchanged()
    profile,_=read_native_profile(paths['native_mapping.json'],preview.source_sha256,options['snapshot_sha256'],master_sha)
    def read(path,key):
        return read_json_record(path.parent,{'name':path.name,'bytes':path.stat().st_size,'sha256':options[key]},
                                path.name,64*1024*1024,cancel_check=check_cancel)[0]
    snapshot=read(paths['source_snapshot.json'],'snapshot_sha256');validate_snapshot(snapshot,preview.source_sha256,cancel_check=check_cancel)
    baseline,_=read_native_timeline(folder,raw,snapshot,profile,{k:options[k] for k in raw['bindings']},cancel_check=check_cancel)
    fitted=read(paths['fitted_timeline.json'],'fit_report_sha256')
    _plan,surface,_angular=validate_fitted_data(fitted,{k:v for k,v in options.items() if k!='fit_report_sha256'},
        baseline,profile,paths['contact_fit.json'],preview.evidence['target_rest_frames'],cancel_check=check_cancel)
    validate_fit_verification(preview.verification,options,fitted)
    if surface.status!='CHECKED' or surface.flagged_frames:raise ValidationError('Fitted playback has unresolved surface review')
    request=JobRequest.new('cache_native_fit',input_project='candidate.blend',options=options)
    result,output=BlenderJobRunner(blender_exe,jobs,worker_script).run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs=paths)
    unchanged()
    if output.is_symlink() or output.resolve().parent!=jobs.resolve():raise ValidationError('Fitted playback output is redirected')
    for name,digest in expected.items():
        if (output/name).is_symlink() or not (output/name).is_file() or _digest(output/name,cancel)!=digest:
            raise ProjectStorageError('Fitted playback worker changed a staged input')
    cache=read_fitted_cache(output,result.details,options,fitted,baseline,surface,cancel_check=check_cancel)
    unchanged()
    return FittedPlayback(project.project_id,project.revision,master_sha,preview.source_sha256,preview.fit_policy_sha256,
        preview.fitted_scene_sha256,cache,request.job_id,str(output/'fitted_skin.json'),original,preview)
