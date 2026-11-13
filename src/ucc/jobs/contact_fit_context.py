"""Revalidate an existing original preview/cache before proposing any correction."""
from dataclasses import dataclass,replace
from pathlib import Path
from threading import Event

from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ValidationError,ProjectConflict
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.preview.motion_cache import read_motion_cache
from .master_preview import _master_file,_digest
from .native_evidence import bound_file,read_native_timeline
from .native_fit_evidence import read_json_record
from .cached_job_evidence import cached_job_details
from .native_body import NativeBodyPreview
from .native_playback import NativePlayback


@dataclass(frozen=True,slots=True)
class ContactFitContext:
    project: CharacterProject
    baseline: dict
    profile: dict
    bindings: dict
    staged: dict
    expected: dict
    playback: NativePlayback


def contact_context(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                    cancel: Event | None=None,cancel_check=lambda:None,require_crossings: bool=True) -> ContactFitContext:
    cancel_check();project=store.load()
    if project.master_blend is None:raise ValidationError('Contact fitting requires a saved character master')
    master,master_sha=_master_file(store,project.master_blend)
    for result in (preview,playback):
        if (result.project_id!=project.project_id or result.revision!=project.revision or
            result.master_sha256!=master_sha or result.source_sha256!=preview.source_sha256):
            raise ProjectConflict('Character/source changed since original motion verification')
    if source_fbx.is_symlink() or _digest(source_fbx,cancel)!=preview.source_sha256:
        raise ValidationError('Selected source changed before contact fitting')
    jobs=store.root/'.ucc-jobs';folder=Path(preview.private_timeline).parent
    def job_folder(path):
        if jobs.is_symlink() or path.is_symlink() or path.resolve().parent!=jobs.resolve():
            raise ValidationError('Contact fitting evidence folder is redirected')
    job_folder(folder)
    raw=preview.worker_report
    if type(raw) is not dict:raise ValidationError('Contact fitting requires original source-FK evidence')
    timeline=bound_file(folder,raw['timeline'],'target_timeline.json',64*1024*1024,cancel_check=cancel_check)
    review=bound_file(folder,raw['visual_review_blend'],'review_motion.blend',512*1024*1024,cancel_check=cancel_check)
    if Path(preview.private_timeline)!=timeline or Path(preview.private_visual_review_blend)!=review:
        raise ValidationError('Original preview paths differ from their bound worker records')
    bindings=dict(raw['bindings'])
    if bindings.get('master_sha256')!=master_sha or bindings.get('source_sha256')!=preview.source_sha256:
        raise ValidationError('Original source-FK character identity differs')
    profile_path=Path(preview.mapping_profile_used)
    profile,map_sha=read_native_profile(profile_path,preview.source_sha256,bindings['snapshot_sha256'],master_sha)
    if map_sha!=bindings['mapping_sha256']:raise ValidationError('Contact fitting original mapping changed')
    snapshot=folder/'source_snapshot.json'
    if snapshot.is_symlink() or not snapshot.is_file():raise ValidationError('Missing source snapshot for contact fitting')
    source,_=read_json_record(folder,{'name':snapshot.name,'bytes':snapshot.stat().st_size,'sha256':bindings['snapshot_sha256']},
        snapshot.name,64*1024*1024,cancel_check=cancel_check)
    validate_snapshot(source,preview.source_sha256,cancel_check=cancel_check)
    baseline,_=read_native_timeline(folder,raw,source,profile,bindings,cancel_check=cancel_check)
    options={**bindings,'review_sha256':raw['visual_review_blend']['sha256'],'timeline_sha256':raw['timeline']['sha256']}
    def worker_result(path,operation):
        return cached_job_details(jobs,path,operation,cancel=cancel,cancel_check=cancel_check)
    cache_folder=Path(playback.private_manifest).parent
    if cache_folder.name!=playback.job_id or Path(playback.private_manifest)!=cache_folder/'motion_skin.json':
        raise ValidationError('Original cache job identity or manifest path differs')
    report=worker_result(cache_folder,'cache_native_fbx_body')
    if not playback.surface_verification_job_id:raise ValidationError('Contact fitting requires full independent hand/arm surface review')
    verified=worker_result(jobs/playback.surface_verification_job_id,'verify_native_surface_review')
    cache=read_motion_cache(cache_folder,report,options,baseline,profile=profile,surface_verification=verified,cancel_check=cancel_check)
    if cache.surface_review is None or cache.surface_review.status!='CHECKED':
        raise ValidationError('Contact inspection requires complete independently verified source geometry')
    if require_crossings and not cache.surface_review.flagged_frames:
        raise ValidationError('No checked hand/arm crossings to fit; original motion retained')
    contacts=bound_file(cache_folder,report['surface_review'],'motion_contacts.json',16*1024*1024,cancel_check=cancel_check)
    staged={'candidate.blend':master,'review_motion.blend':review,'target_timeline.json':timeline,
            'source_snapshot.json':snapshot,'native_mapping.json':profile_path,'motion_contacts.json':contacts}
    expected={'candidate.blend':master_sha,'review_motion.blend':options['review_sha256'],'target_timeline.json':options['timeline_sha256'],
              'source_snapshot.json':options['snapshot_sha256'],'native_mapping.json':map_sha,'motion_contacts.json':report['surface_review']['sha256']}
    return ContactFitContext(project,baseline,profile,options,staged,expected,replace(playback,cache=cache))
