"""Project/revision/license-bound cached animation preparation on private copies."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from threading import Event

from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import AssetPolicyError, LicensePolicy
from ucc.preview.motion_cache import MotionCache, read_motion_cache, _pairs
from .master_preview import _digest, _master_file
from .native_body import NativeBodyPreview
from .native_evidence import bound_file, read_native_timeline
from .native_skin_evidence import validate_reopen_report
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class NativePlayback:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    cache: MotionCache
    job_id: str
    private_manifest: str
    surface_verification_job_id: str=""


def prepare_native_playback(store: ProjectStore, preview: NativeBodyPreview, *, source_fbx: Path,
                            permission: LicensePolicy, blender_exe: Path, worker_script: Path,
                            cancel: Event | None=None, timeout_s: float=300) -> NativePlayback:
    allowed,reason=permission.allow("local_preview")
    if not allowed:raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise ProjectStorageError("Animation preparation cancelled; originals unchanged")
    project=store.load()
    if project.master_blend is None:raise ValidationError("Cached animation needs a saved Blender character master")
    master,master_sha=_master_file(store,project.master_blend)
    if (project.project_id!=preview.project_id or project.revision!=preview.revision or
            master_sha!=preview.master_sha256):raise ProjectConflict("Saved character changed since animation verification")
    folder=Path(preview.private_timeline).parent
    jobs_root=store.root/".ucc-jobs"
    if (jobs_root.is_symlink() or folder.is_symlink() or folder.resolve().parent!=jobs_root.resolve() or preview.worker_report is None):
        raise ValidationError("Animation verification folder is redirected or missing")
    report=preview.worker_report
    bindings=dict(report.get("bindings",{}))
    if bindings.get("source_sha256")!=preview.source_sha256 or bindings.get("master_sha256")!=master_sha:
        raise ValidationError("Animation preview identity differs")
    timeline=bound_file(folder,report["timeline"],"target_timeline.json",64*1024*1024,cancel_check=check_cancel)
    review=bound_file(folder,report["visual_review_blend"],"review_motion.blend",512*1024*1024,cancel_check=check_cancel)
    snapshot=folder/"source_snapshot.json";profile_path=Path(preview.mapping_profile_used)
    profile,map_sha=read_native_profile(profile_path,preview.source_sha256,bindings["snapshot_sha256"],master_sha)
    if profile.get("skin_deformation_policy")!="BOUND_CORRECTIVE_SMOOTH_V1" or map_sha!=bindings["mapping_sha256"]:
        raise ValidationError("In-UCC playback currently requires the audited bound-skin preview policy")
    if snapshot.is_symlink() or not snapshot.is_file() or not 0<snapshot.stat().st_size<=64*1024*1024:
        raise ValidationError("Missing or oversized animation source snapshot")
    with snapshot.open("rb") as stream:payload=stream.read(64*1024*1024+1)
    if sha256(payload).hexdigest()!=bindings["snapshot_sha256"]:raise ValidationError("Animation snapshot SHA differs")
    try:source=json.loads(payload,object_pairs_hook=_pairs)
    except (ValueError,UnicodeError,RecursionError) as error:raise ValidationError("Invalid animation snapshot JSON") from error
    validate_snapshot(source,preview.source_sha256,cancel_check=check_cancel)
    data,_=read_native_timeline(folder,report,source,profile,bindings,cancel_check=check_cancel)
    options={**bindings,"review_sha256":report["visual_review_blend"]["sha256"],"timeline_sha256":report["timeline"]["sha256"]}
    staged={"candidate.blend":master,"review_motion.blend":review,"target_timeline.json":timeline,
            "source_snapshot.json":snapshot,"native_mapping.json":profile_path}
    expected={"candidate.blend":master_sha,"review_motion.blend":options["review_sha256"],
              "target_timeline.json":options["timeline_sha256"],"source_snapshot.json":bindings["snapshot_sha256"],"native_mapping.json":map_sha}
    originals=[(path,expected[name]) for name,path in staged.items()]+[(source_fbx,preview.source_sha256),
               (store.root/"project.ucc.json",_digest(store.root/"project.ucc.json",cancel))]
    def unchanged():
        check_cancel()
        if store.load()!=project:raise ProjectConflict("Character project changed while preparing animation")
        for path,digest in originals:
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError("Original animation/master/evidence changed while preparing playback")
    unchanged()
    request=JobRequest.new("cache_native_fbx_body",input_project="candidate.blend",options=options)
    result,output=BlenderJobRunner(blender_exe,jobs_root,worker_script).run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs=staged)
    unchanged()
    if output.is_symlink() or output.resolve().parent!=jobs_root.resolve():raise ValidationError("Playback worker folder is redirected")
    for name,digest in expected.items():
        if (output/name).is_symlink() or not (output/name).is_file() or _digest(output/name,cancel)!=digest:
            raise ProjectStorageError("Playback worker changed staged originals")
    validate_reopen_report(result.details.get("saved_review_verification"),options,data)
    surface_report=None;surface_job_id=""
    if "surface_review" in result.details:
        record=result.details["surface_review"]
        contact=bound_file(output,record,"motion_contacts.json",16*1024*1024,cancel_check=check_cancel)
        check=JobRequest.new("verify_native_surface_review",input_project="candidate.blend",
            options={**options,"surface_review_sha256":record["sha256"]})
        verified,verify_folder=BlenderJobRunner(blender_exe,jobs_root,worker_script).run(check,timeout_s=timeout_s,cancel=cancel,
            staged_inputs={**staged,"motion_contacts.json":contact})
        unchanged()
        if verify_folder.is_symlink() or verify_folder.resolve().parent!=jobs_root.resolve():raise ValidationError("Surface verifier folder is redirected")
        for name,digest in {**expected,"motion_contacts.json":record["sha256"]}.items():
            if (verify_folder/name).is_symlink() or not (verify_folder/name).is_file() or _digest(verify_folder/name,cancel)!=digest:
                raise ProjectStorageError("Surface verifier changed staged originals")
        surface_report=verified.details;surface_job_id=check.job_id
    cache=read_motion_cache(output,result.details,options,data,cancel_check=check_cancel,profile=profile,surface_verification=surface_report)
    unchanged()
    return NativePlayback(project.project_id,project.revision,master_sha,preview.source_sha256,cache,request.job_id,str(output/"motion_skin.json"),surface_job_id)
