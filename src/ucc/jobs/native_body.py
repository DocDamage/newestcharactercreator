"""Project-bound native body preview: imports, two FK workers, private evidence."""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Callable
import json
import re

from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.animations.native_preview_adjustments import preview_adjustment_declarations
from ucc.animations.native_family import measured_body_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from .fbx_intake import inspect_selected_fbx
from .master_preview import _digest, _master_file
from .native_evidence import read_native_timeline, bound_file
from .private_render_evidence import verify_native_renders
from .native_skin_evidence import validate_reopen_report
from ucc.animations.native_skin_policy import BOUND_V1, CORRECTIVE_POLICIES
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .native_source_authority import NativeSourceAuthority, NativeProofReceipt, NativeProofCapture
from .target_action_context import operation_budget


@dataclass(frozen=True,slots=True)
class NativeBodyPreview:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    evidence: dict
    private_visual_review_blend: str
    private_render_review: str
    private_timeline: str
    worker_job_ids: tuple[str,str]
    mapping_profile_used: str = ""
    worker_report: dict | None = None
    private_reopen_job_id: str = ""
    reopen_evidence: dict | None = None
    source_intake_worker_job_ids: tuple[str, ...] = ()
    source_authority: NativeSourceAuthority | None = None
    proof_receipt: NativeProofReceipt | None = None

    @property
    def retargeting_verified(self): return False


def _preview_native_body(store: ProjectStore, *, source_fbx: Path, mapping_profile: Path | None=None,
                        blender_exe: Path, worker_script: Path, permission: LicensePolicy,
                        expected_project_id: str, expected_revision: int, expected_master_blend: str,
                        cancel: Event | None=None, timeout_s: float=300, include_hands: bool=False, skin_policy: str | None=None,
                        source_intake_observer: Callable | None=None, source_guard=None,
                        render_private_frames: bool=True, progress: Callable[[str], None] | None=None,
                        _source_authority=None, _proof=None) -> NativeBodyPreview:
    if source_intake_observer is not None and not callable(source_intake_observer):
        raise ValidationError('Native source intake observer must be callable')
    if type(render_private_frames) is not bool or (progress is not None and not callable(progress)):
        raise ValidationError('Native preview render selection or progress callback differs')
    allowed,reason=permission.allow("local_preview")
    if not allowed: raise AssetPolicyError(reason)
    if type(include_hands) is not bool or (include_hands and mapping_profile is not None):
        raise ValidationError("Automatic hand mapping needs a boolean selection and no explicit map; explicit maps define their own joints")
    def check_cancel():
        if cancel is not None and cancel.is_set(): raise ProjectStorageError("Native body preview cancelled; originals unchanged")
    if (skin_policy is not None and (type(skin_policy) is not str or skin_policy not in CORRECTIVE_POLICIES or mapping_profile is not None)):
        raise ValidationError("An explicit corrective skin policy requires automatic mapping and a supported policy")
    project=store.load()
    def current():
        check_cancel()
        p=store.load()
        if (p.project_id!=expected_project_id or p.revision!=expected_revision or p.master_blend!=expected_master_blend):
            raise ProjectConflict("Saved character changed during native body preview")
    current()
    master,master_sha=_master_file(store,expected_master_blend)
    if _digest(master,cancel)!=master_sha: raise ProjectStorageError("Native target master hash differs")
    metadata=store.root/"project.ucc.json"
    metadata_sha=_digest(metadata,cancel)
    intake_ids=[]
    def observe(request, result, folder):
        expected=store.root/'.ucc-jobs'/request.job_id
        if (folder != expected or folder.resolve() != folder or folder.is_symlink()
                or getattr(folder, 'is_junction', lambda:False)()):
            raise ProjectStorageError('Observed native intake escaped its actual worker folder')
        intake_ids.append(request.job_id)
        source_intake_observer(request,result,folder)
    observer_options={} if source_intake_observer is None else {'observer':observe}
    if source_guard is not None: observer_options['source_guard']=source_guard
    if progress is not None:
        progress('INSPECT_SOURCE')
    intake=inspect_selected_fbx(source_fbx,blender_exe=blender_exe,worker_script=worker_script,
        jobs_root=store.root/".ucc-jobs",permission=permission,cancel=cancel,timeout_s=timeout_s,**observer_options)
    if source_intake_observer is not None and (len(intake_ids)!=2 or len(set(intake_ids))!=2):
        raise ValidationError('Native source observer did not capture two distinct actual workers')
    snapshot_path=Path(intake["private_snapshot"])
    if _proof is not None: _proof.before(snapshot_path)
    source,_=read_snapshot(snapshot_path.parent,intake,intake["source_sha256"],cancel_check=check_cancel)
    snapshot_sha=intake["snapshot"]["sha256"]
    if _source_authority is not None:
        _source_authority.require_snapshot(source, snapshot_sha)
        _proof.admit(snapshot_path, snapshot_sha)
    if mapping_profile is None:
        generated=measured_body_profile(source,intake["source_sha256"],snapshot_sha,master_sha,include_hands=include_hands,skin_policy=skin_policy or BOUND_V1)
        mapping_profile=snapshot_path.parent/"native_mapping.json"
        if mapping_profile.exists() or mapping_profile.is_symlink():raise ValidationError("Refuse to replace an automatic native body map")
        with mapping_profile.open("x",encoding="utf-8") as stream:
            json.dump(generated,stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    if _proof is not None: _proof.before(mapping_profile)
    profile,mapping_sha=read_native_profile(mapping_profile,intake["source_sha256"],snapshot_sha,master_sha)
    if preview_adjustment_declarations(profile) and (_source_authority is None or render_private_frames):
        raise ValidationError("Source pose adjustments require an authenticated animation-library preview")
    if _proof is not None: _proof.admit(mapping_profile, mapping_sha)
    bindings={"source_sha256":intake["source_sha256"],"snapshot_sha256":snapshot_sha,
              "mapping_sha256":mapping_sha,"master_sha256":master_sha}
    runner=BlenderJobRunner(blender_exe,store.root/".ucc-jobs",worker_script)
    first_data=first_report=first_folder=first_path=None
    ids=[]
    def unchanged():
        current()
        for path,digest in ((master,master_sha),(metadata,metadata_sha),(source_fbx,intake["source_sha256"]),
                            (mapping_profile,mapping_sha),(snapshot_path,snapshot_sha)):
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError("Native original/master/profile/snapshot changed during verification")
    for run in range(2):
        unchanged()
        render = run == 0 and render_private_frames
        request=JobRequest.new("verify_native_fbx_body",input_project="candidate.blend",
            options={**bindings,"render_private_frames":render})
        if source_guard is not None: source_guard()
        if progress is not None:
            progress('VERIFY_BODY_FIRST' if run == 0 else 'VERIFY_BODY_SECOND')
        result,folder=runner.run(request,timeout_s=timeout_s,cancel=cancel,
            staged_inputs={"candidate.blend":master,"source_snapshot.json":snapshot_path,"native_mapping.json":mapping_profile})
        unchanged()
        if folder.is_symlink() or folder.resolve().parent!=(store.root/".ucc-jobs").resolve():
            raise ProjectStorageError("Native worker folder is redirected")
        for name,digest in (("candidate.blend",master_sha),("source_snapshot.json",snapshot_sha),("native_mapping.json",mapping_sha)):
            path=folder/name
            if _proof is not None: _proof.before(path)
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError("Native staged input changed during Blender evaluation")
            if _proof is not None: _proof.admit(path, digest)
        if _proof is not None:
            _proof.before(folder/'target_timeline.json')
            _proof.before(folder/'review_motion.blend')
        data,path=read_native_timeline(folder,result.details,source,profile,bindings,cancel_check=check_cancel)
        if _proof is not None:
            _proof.admit(path, result.details['timeline']['sha256'])
            _proof.admit(folder/'review_motion.blend', result.details['visual_review_blend']['sha256'])
        rendered = result.details.get('private_review_renders') is not None
        if render and not rendered:
            raise ValidationError("Native first worker did not render private skin views")
        if rendered and not render:
            raise ValidationError("Native body worker rendered without request")
        if run==0:
            first_data,first_report,first_folder,first_path=data,result.details,folder,path
        else:
            # Saved Blender copies contain save metadata; compare every actual
            # matrix/skin/root/quality value, excluding only distinct copy IDs.
            if ({k:v for k,v in first_data.items() if k!="visual_review_blend"}!=
                    {k:v for k,v in data.items() if k!="visual_review_blend"}):
                raise ValidationError("Independent native target workers disagree on complete poses/skin/root evidence")
        ids.append(request.job_id)
    unchanged()
    bound_file(first_folder,first_report["timeline"],"target_timeline.json",64*1024*1024,cancel_check=check_cancel)
    action=bound_file(first_folder,first_report["visual_review_blend"],"review_motion.blend",512*1024*1024,cancel_check=check_cancel)
    review=verify_native_renders(first_folder,first_report,first_data) if render_private_frames else ''
    reopen_id="";reopened=None
    if profile.get("skin_deformation_policy") in CORRECTIVE_POLICIES:
        unchanged()
        reopen_bindings={**bindings,"review_sha256":first_report["visual_review_blend"]["sha256"],"timeline_sha256":first_report["timeline"]["sha256"]}
        request=JobRequest.new("reopen_native_fbx_body",input_project="candidate.blend",options=reopen_bindings)
        staged={"candidate.blend":master,"review_motion.blend":action,"target_timeline.json":first_path,
                "source_snapshot.json":snapshot_path,"native_mapping.json":mapping_profile}
        if source_guard is not None: source_guard()
        if progress is not None:
            progress('REOPEN_BODY')
        result,reopen_folder=runner.run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs=staged)
        unchanged()
        if reopen_folder.is_symlink() or reopen_folder.resolve().parent!=(store.root/".ucc-jobs").resolve():
            raise ProjectStorageError("Native reopen folder is redirected")
        hashes={"candidate.blend":master_sha,"review_motion.blend":reopen_bindings["review_sha256"],
                "target_timeline.json":reopen_bindings["timeline_sha256"],"source_snapshot.json":snapshot_sha,"native_mapping.json":mapping_sha}
        for name,digest in hashes.items():
            if _proof is not None: _proof.before(reopen_folder/name)
            if (reopen_folder/name).is_symlink() or not (reopen_folder/name).is_file() or _digest(reopen_folder/name,cancel)!=digest:
                raise ProjectStorageError("Native reopen changed staged evidence")
            if _proof is not None: _proof.admit(reopen_folder/name, digest)
        validate_reopen_report(result.details,reopen_bindings,first_data)
        reopen_id=request.job_id;reopened=result.details
        bound_file(first_folder,first_report["timeline"],"target_timeline.json",64*1024*1024,cancel_check=check_cancel)
        bound_file(first_folder,first_report["visual_review_blend"],"review_motion.blend",512*1024*1024,cancel_check=check_cancel)
        if render_private_frames:
            review=verify_native_renders(first_folder,first_report,first_data)
    unchanged()
    return NativeBodyPreview(project.project_id,project.revision,master_sha,intake["source_sha256"],first_data,
                             str(action),review,str(first_path),tuple(ids),str(mapping_profile),first_report,reopen_id,reopened,tuple(intake_ids))


def preview_native_body(store: ProjectStore, *, source_fbx: Path, mapping_profile: Path | None=None,
        blender_exe: Path, worker_script: Path, permission: LicensePolicy,
        expected_project_id: str, expected_revision: int, expected_master_blend: str,
        cancel: Event | None=None, timeout_s: float=300, include_hands: bool=False,
        skin_policy: str | None=None, source_intake_observer: Callable | None=None,
        source_guard=None, source_authority: NativeSourceAuthority | None=None,
        render_private_frames: bool=True, progress: Callable[[str], None] | None=None) -> NativeBodyPreview:
    options = dict(source_fbx=source_fbx, mapping_profile=mapping_profile, blender_exe=blender_exe,
        worker_script=worker_script, permission=permission, expected_project_id=expected_project_id,
        expected_revision=expected_revision, expected_master_blend=expected_master_blend,
        cancel=cancel, timeout_s=timeout_s, include_hands=include_hands, skin_policy=skin_policy,
        source_intake_observer=source_intake_observer, source_guard=source_guard,
        render_private_frames=render_private_frames, progress=progress)
    if source_authority is None:
        return _preview_native_body(store, **options)
    if type(source_authority) is not NativeSourceAuthority:
        raise ValidationError('Registered native source authority type differs')
    if (type(expected_master_blend) is not str
            or re.fullmatch(r'master/versions/[0-9a-f]{64}\.blend', expected_master_blend) is None):
        raise ValidationError('Registered native preview requires the saved content-addressed master path')
    source_authority.require_source(source_fbx, permission)
    with operation_budget(cancel, timeout_s) as budget:
        proof = NativeProofCapture(budget)
        metadata = proof.before(store.root/'project.ucc.json')
        master = proof.before(store.root/expected_master_blend)
        proof.admit(metadata, _digest(metadata, budget.cancel))
        proof.admit(master, _digest(master, budget.cancel))
        proof.before(source_authority.source_path)
        proof.admit(source_authority.source_path, source_authority.source_sha256)

        def guarded():
            budget.check()
            if source_guard is not None: source_guard()
            proof.check()
            source_authority.guard(cancel=budget.cancel, timeout_s=budget.remaining())
            budget.check()

        guarded()
        options.update(cancel=budget.cancel, timeout_s=budget.remaining(), source_guard=guarded,
                       _source_authority=source_authority, _proof=proof)
        result = _preview_native_body(store, **options)
        receipt = proof.seal()
        source_authority.guard(cancel=budget.cancel, timeout_s=budget.remaining())
        if not receipt.identities_current():
            raise ProjectStorageError('Native proof changed at final source permission fence')
        budget.check()
        return replace(result, source_authority=source_authority, proof_receipt=receipt)
