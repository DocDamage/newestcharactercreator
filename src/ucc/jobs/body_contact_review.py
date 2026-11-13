"""Two-process complete body contact inspection on private source/fitted copies."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy,AssetPolicyError
from ucc.preview.body_contacts import BodyContacts,read_body_contacts,validate_body_measurement
from ucc.preview.central_enclosure import CentralEnclosure
from ucc.preview.contact_areas import BodyContactAreas,read_body_contact_areas
from ucc.preview.skin_inclusion import read_skin_inclusion,validate_skin_measurement
from .contact_fit_context import contact_context
from .body_contact_context import fitted_body_context
from .native_body import NativeBodyPreview
from .native_playback import NativePlayback
from .fitted_playback import FittedPlayback
from .master_preview import _digest
from .native_evidence import bound_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class BodyContactReview:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    contacts: BodyContacts
    original_playback: NativePlayback
    fitted_playback: FittedPlayback | None
    worker_job_ids: tuple[str,str]
    private_report: str
    report_sha256: str
    bindings: tuple[tuple[str,str],...]
    metadata_sha256: str
    areas: BodyContactAreas | None=None
    enclosure: CentralEnclosure | None=None
    private_enclosure_report: str=''
    enclosure_report_sha256: str=''
    private_anatomical_verification: str=''
    anatomical_verification_sha256: str=''


def review_body_contacts(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                         permission: LicensePolicy,blender_exe: Path,worker_script: Path,fitted: FittedPlayback | None=None,
                         cancel: Event | None=None,timeout_s: float=900) -> BodyContactReview:
    return _review_body(store,preview,playback,source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,
        worker_script=worker_script,fitted=fitted,cancel=cancel,timeout_s=timeout_s)


def review_body_contact_areas(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                              permission: LicensePolicy,blender_exe: Path,worker_script: Path,fitted: FittedPlayback | None=None,
                              cancel: Event | None=None,timeout_s: float=900) -> BodyContactReview:
    return _review_body(store,preview,playback,source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,
        worker_script=worker_script,fitted=fitted,cancel=cancel,timeout_s=timeout_s,stable_areas=True)


def review_anatomical_safety(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                             permission: LicensePolicy,blender_exe: Path,worker_script: Path,fitted: FittedPlayback | None=None,
                             cancel: Event | None=None,timeout_s: float=900) -> BodyContactReview:
    return _review_body(store,preview,playback,source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,
        worker_script=worker_script,fitted=fitted,cancel=cancel,timeout_s=timeout_s,stable_areas=True,anatomical_safety=True)


def _review_body(store,preview,playback,*,source_fbx,permission,blender_exe,worker_script,fitted=None,
                 cancel=None,timeout_s=900,stable_areas=False,skin_inclusion=False,anatomical_safety=False):
    if stable_areas and skin_inclusion:raise ValueError('Choose one explicit inspection policy')
    allowed,reason=permission.allow('local_preview')
    if not allowed:raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Body contact review cancelled; playable motion retained')
    ctx=contact_context(store,preview,playback,source_fbx=source_fbx,cancel=cancel,cancel_check=check_cancel,require_crossings=False)
    options=dict(ctx.bindings);staged={n:p for n,p in ctx.staged.items() if n!='motion_contacts.json'}
    expected={n:ctx.expected[n] for n in staged};fitted_data=None;variant=fitted
    metadata_sha=_digest(store.root/'project.ucc.json',cancel)
    originals=[(p,ctx.expected[n]) for n,p in ctx.staged.items()]+[(source_fbx,preview.source_sha256),
        (store.root/'project.ucc.json',metadata_sha)]
    if fitted is not None:
        options,paths,hashes,fitted_data,variant=fitted_body_context(store,ctx,preview,fitted,cancel=cancel,cancel_check=check_cancel)
        staged.update(paths);expected.update(hashes);originals.extend((p,hashes[n]) for n,p in paths.items())
    def unchanged():
        check_cancel()
        if store.load()!=ctx.project:raise ProjectConflict('Saved character changed during body contact inspection')
        for path,digest in originals:
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Body inspection source/master/policy/evidence changed')
    runner=BlenderJobRunner(blender_exe,store.root/'.ucc-jobs',worker_script);ids=[]
    def run(operation):
        unchanged();request=JobRequest.new(operation,input_project='candidate.blend',options=dict(options))
        result,folder=runner.run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs=dict(staged));unchanged()
        if folder.is_symlink() or folder.resolve().parent!=(store.root/'.ucc-jobs').resolve():
            raise ValidationError('Body contact inspection output is redirected')
        for name,digest in expected.items():
            path=folder/name
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError('Body contact worker changed a bound staged input')
        ids.append(request.job_id);return result.details,folder
    kind='fitted' if fitted is not None else 'native'
    suffix='_anatomical_safety' if anatomical_safety else '_skin_inclusion' if skin_inclusion else '_body_areas' if stable_areas else '_body_contacts'
    limit=(64 if skin_inclusion else 40 if stable_areas else 32)*1024*1024
    measured,folder=run('inspect_'+kind+suffix)
    from ucc.preview.central_enclosure import validate_anatomical_measurement,read_central_enclosure
    (validate_anatomical_measurement if anatomical_safety else validate_skin_measurement if skin_inclusion else validate_body_measurement)(
        measured,options,ctx.baseline,fitted is not None)
    report=bound_file(folder,measured['report'],'body_contacts.json',limit,cancel_check=check_cancel)
    staged['body_contacts.json']=report;expected['body_contacts.json']=measured['report']['sha256']
    originals.append((report,measured['report']['sha256']));options['body_review_sha256']=measured['report']['sha256']
    if anatomical_safety:
        enclosure_path=bound_file(folder,measured['enclosure_report'],'central_enclosure.json',64*1024*1024,cancel_check=check_cancel)
        enclosure_sha=measured['enclosure_report']['sha256']
        staged['central_enclosure.json']=enclosure_path;expected['central_enclosure.json']=enclosure_sha
        originals.append((enclosure_path,enclosure_sha));options['enclosure_review_sha256']=enclosure_sha
    verified,_verify_folder=run('verify_'+kind+suffix)
    base={k:v for k,v in options.items() if k not in {'body_review_sha256','enclosure_review_sha256'}}
    parser=read_skin_inclusion if skin_inclusion else read_body_contact_areas if stable_areas else read_body_contacts
    if anatomical_safety:
        from ucc.jobs.native_fit_evidence import read_json_record
        from ucc.preview.contact_areas import parse_body_contact_areas
        area_data,_=read_json_record(folder,measured['report'],'body_contacts.json',40*1024*1024,cancel_check=check_cancel)
        parsed=parse_body_contact_areas(area_data,base,ctx.baseline,ctx.profile,ctx.playback.cache,
            fitted_timeline=fitted_data,fitted_cache=variant.cache if variant is not None else None,cancel_check=check_cancel)
        enclosure=read_central_enclosure(folder,measured,verified,base,ctx.baseline,ctx.profile,ctx.playback.cache,area_data,
            fitted_cache=variant.cache if variant is not None else None,cancel_check=check_cancel)
        verification_path=_verify_folder/'result.json'
        if verification_path.is_symlink() or not verification_path.is_file():raise ValidationError('Anatomical receipt is redirected')
        verification_sha=_digest(verification_path,cancel)
        unchanged()
        return BodyContactReview(ctx.project.project_id,ctx.project.revision,preview.master_sha256,preview.source_sha256,
            parsed.contacts,ctx.playback,variant,tuple(ids),str(report),measured['report']['sha256'],tuple(sorted(base.items())),metadata_sha,
            parsed,enclosure,str(enclosure_path),enclosure_sha,str(verification_path),verification_sha)
    parsed=parser(folder,measured,verified,base,ctx.baseline,ctx.profile,ctx.playback.cache,
        fitted_timeline=fitted_data,fitted_cache=variant.cache if variant is not None else None,cancel_check=check_cancel)
    if skin_inclusion:
        from .skin_inclusion import SkinInclusionReview
        unchanged();bound_file(folder,measured['report'],'body_contacts.json',limit,cancel_check=check_cancel)
        return SkinInclusionReview(ctx.project.project_id,ctx.project.revision,preview.master_sha256,preview.source_sha256,
            parsed,ctx.playback,variant,tuple(ids),str(report),measured['report']['sha256'],tuple(sorted(base.items())),metadata_sha)
    contacts=parsed.contacts if stable_areas else parsed
    unchanged();bound_file(folder,measured['report'],'body_contacts.json',limit,cancel_check=check_cancel)
    return BodyContactReview(ctx.project.project_id,ctx.project.revision,preview.master_sha256,preview.source_sha256,
        contacts,ctx.playback,variant,tuple(ids),str(report),measured['report']['sha256'],tuple(sorted(base.items())),metadata_sha,
        parsed if stable_areas else None)
