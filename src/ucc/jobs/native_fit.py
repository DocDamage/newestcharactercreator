"""Project-bound fitting: stage, measure saved Action, independently reproduce."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ucc.animations.contact_fit import HASHES,MAX_FIT_BYTES,read_contact_fit
from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy,AssetPolicyError
from ucc.preview.surface_review import SurfaceReview
from .master_preview import _master_file,_digest
from .native_body import NativeBodyPreview
from .native_evidence import bound_file,read_native_timeline
from .native_fit_evidence import read_json_record,validate_fit_stage,rest_parents,read_fitted_timeline
from .native_fit_renders import verify_fit_renders
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class NativeFitPreview:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    fitted_scene_sha256: str
    fit_policy_sha256: str
    private_fitted_scene: str
    private_timeline: str
    private_render_review: str
    worker_job_ids: tuple[str,str,str]
    evidence: dict
    surface_review: SurfaceReview
    angular_audit: dict
    verification: dict
    original_preview: NativeBodyPreview
    fit_policy_used: str

    @property
    def contact_quality_verified(self):return False

    @property
    def retargeting_verified(self):return False


def fit_native_preview(store: ProjectStore,preview: NativeBodyPreview,*,source_fbx: Path,fit_policy: Path,
                       permission: LicensePolicy,blender_exe: Path,worker_script: Path,
                       cancel: Event | None=None,timeout_s: float=300) -> NativeFitPreview:
    allowed,reason=permission.allow('local_preview')
    if not allowed:raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Target fitting cancelled; originals unchanged')
    check_cancel();project=store.load()
    if project.master_blend is None:raise ValidationError('Target fitting requires a saved Blender character master')
    master,master_sha=_master_file(store,project.master_blend)
    if (project.project_id!=preview.project_id or project.revision!=preview.revision or master_sha!=preview.master_sha256):
        raise ProjectConflict('Saved character changed since source FK verification')
    jobs=store.root/'.ucc-jobs';folder=Path(preview.private_timeline).parent
    if (jobs.is_symlink() or folder.is_symlink() or folder.resolve().parent!=jobs.resolve() or preview.worker_report is None):
        raise ValidationError('Original source-FK review folder is redirected or missing')
    raw=preview.worker_report;bindings=dict(raw.get('bindings',{}))
    if bindings.get('source_sha256')!=preview.source_sha256 or bindings.get('master_sha256')!=master_sha:
        raise ValidationError('Original source-FK identity differs from this saved character')
    timeline=bound_file(folder,raw['timeline'],'target_timeline.json',64*1024*1024,cancel_check=check_cancel)
    review=bound_file(folder,raw['visual_review_blend'],'review_motion.blend',512*1024*1024,cancel_check=check_cancel)
    profile_path=Path(preview.mapping_profile_used)
    profile,map_sha=read_native_profile(profile_path,preview.source_sha256,bindings['snapshot_sha256'],master_sha)
    if map_sha!=bindings['mapping_sha256']:raise ValidationError('Original native map changed before target fitting')
    snapshot=folder/'source_snapshot.json'
    if snapshot.is_symlink() or not snapshot.is_file():raise ValidationError('Missing original source snapshot')
    source,_=read_json_record(folder,{'name':snapshot.name,'bytes':snapshot.stat().st_size,'sha256':bindings['snapshot_sha256']},
                               snapshot.name,64*1024*1024,cancel_check=check_cancel)
    validate_snapshot(source,preview.source_sha256,cancel_check=check_cancel)
    baseline,_=read_native_timeline(folder,raw,source,profile,bindings,cancel_check=check_cancel)
    options={**bindings,'review_sha256':raw['visual_review_blend']['sha256'],'timeline_sha256':raw['timeline']['sha256']}
    if fit_policy.is_symlink() or not fit_policy.is_file() or not 0<fit_policy.stat().st_size<=MAX_FIT_BYTES:
        raise ValidationError('Select a bounded regular target-fitting policy')
    fit_sha=_digest(fit_policy,cancel)
    policy,_=read_json_record(fit_policy.parent,{'name':fit_policy.name,'bytes':fit_policy.stat().st_size,'sha256':fit_sha},
                             fit_policy.name,MAX_FIT_BYTES,cancel_check=check_cancel)
    if type(policy) is not dict or policy.get('bindings')!=options:
        raise ValidationError('Target-fitting policy does not bind this exact original source FK review')
    options['fit_sha256']=fit_sha
    staged={'candidate.blend':master,'review_motion.blend':review,'target_timeline.json':timeline,
            'source_snapshot.json':snapshot,'native_mapping.json':profile_path,'contact_fit.json':fit_policy}
    expected={'candidate.blend':master_sha,'review_motion.blend':options['review_sha256'],
              'target_timeline.json':options['timeline_sha256'],'source_snapshot.json':bindings['snapshot_sha256'],
              'native_mapping.json':map_sha,'contact_fit.json':fit_sha}
    metadata=store.root/'project.ucc.json'
    originals=[(p,expected[n]) for n,p in staged.items()]+[(metadata,_digest(metadata,cancel)),(source_fbx,preview.source_sha256)]
    runner=BlenderJobRunner(blender_exe,jobs,worker_script);ids=[]
    def unchanged():
        check_cancel()
        if store.load()!=project:raise ProjectConflict('Saved character changed while fitting; candidate not published')
        for path,digest in originals:
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Original source/master/policy/evidence changed during target fitting')
    def run(operation):
        unchanged();request=JobRequest.new(operation,input_project='candidate.blend',options=dict(options))
        result,output=runner.run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs=dict(staged))
        unchanged()
        if output.is_symlink() or output.resolve().parent!=jobs.resolve():raise ValidationError('Fitting worker folder is redirected')
        for name,digest in expected.items():
            path=output/name
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Fitting worker changed a bound staged input')
        ids.append(request.job_id);return result.details,output
    stage,stage_folder=run('fit_native_fbx_body')
    validate_fit_stage(stage,options,baseline)
    # Independently validate the policy against the first worker's measured tree
    # before trusting any saved fitted geometry or requesting its canonical report.
    read_contact_fit(fit_policy,fit_sha,{k:options[k] for k in HASHES},baseline,profile,
                     rest_parents(stage['target_rest_frames'],baseline),cancel_check=check_cancel)
    fitted=bound_file(stage_folder,stage['fitted_scene'],'fitted_motion.blend',512*1024*1024,cancel_check=check_cancel)
    options['fitted_sha256']=stage['fitted_scene']['sha256'];staged['fitted_motion.blend']=fitted
    expected['fitted_motion.blend']=options['fitted_sha256'];originals.append((fitted,options['fitted_sha256']))
    measured,measure_folder=run('measure_native_fit')
    data,fit_timeline,plan,surface,angular=read_fitted_timeline(measure_folder,measured,options,baseline,profile,fit_policy,
                                                            stage['target_rest_frames'],cancel_check=check_cancel)
    if surface.status!='CHECKED' or surface.flagged_frames:
        raise ValidationError('Fitted candidate has unresolved or unavailable hand/arm intersection review; not published')
    options['fit_report_sha256']=measured['timeline']['sha256'];staged['fitted_timeline.json']=fit_timeline
    expected['fitted_timeline.json']=options['fit_report_sha256'];originals.append((fit_timeline,options['fit_report_sha256']))
    verified,verify_folder=run('verify_native_fit')
    index=verify_fit_renders(verify_folder,verified,options,data,baseline,plan,cancel_check=check_cancel)
    unchanged()
    bound_file(stage_folder,stage['fitted_scene'],'fitted_motion.blend',512*1024*1024,cancel_check=check_cancel)
    bound_file(measure_folder,measured['timeline'],'fitted_timeline.json',64*1024*1024,cancel_check=check_cancel)
    return NativeFitPreview(project.project_id,project.revision,master_sha,preview.source_sha256,options['fitted_sha256'],fit_sha,
                            str(fitted),str(fit_timeline),index,tuple(ids),data,surface,angular,verified,preview,str(fit_policy))
