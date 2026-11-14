"""Project-bound native body preview: imports, two FK workers, private evidence."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import json

from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.animations.native_family import measured_body_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from .fbx_intake import inspect_selected_fbx
from .master_preview import _digest, _master_file
from .native_evidence import read_native_timeline, bound_file
from .private_render_evidence import verify_native_renders
from .protocol import JobRequest
from .runner import BlenderJobRunner


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

    @property
    def retargeting_verified(self): return False


def preview_native_body(store: ProjectStore, *, source_fbx: Path, mapping_profile: Path | None=None,
                        blender_exe: Path, worker_script: Path, permission: LicensePolicy,
                        expected_project_id: str, expected_revision: int, expected_master_blend: str,
                        cancel: Event | None=None, timeout_s: float=300) -> NativeBodyPreview:
    allowed,reason=permission.allow("local_preview")
    if not allowed: raise AssetPolicyError(reason)
    def check_cancel():
        if cancel is not None and cancel.is_set(): raise ProjectStorageError("Native body preview cancelled; originals unchanged")
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
    intake=inspect_selected_fbx(source_fbx,blender_exe=blender_exe,worker_script=worker_script,
        jobs_root=store.root/".ucc-jobs",permission=permission,cancel=cancel,timeout_s=timeout_s)
    snapshot_path=Path(intake["private_snapshot"])
    source,_=read_snapshot(snapshot_path.parent,intake,intake["source_sha256"],cancel_check=check_cancel)
    snapshot_sha=intake["snapshot"]["sha256"]
    if mapping_profile is None:
        generated=measured_body_profile(source,intake["source_sha256"],snapshot_sha,master_sha)
        mapping_profile=snapshot_path.parent/"native_mapping.json"
        if mapping_profile.exists() or mapping_profile.is_symlink():raise ValidationError("Refuse to replace an automatic native body map")
        with mapping_profile.open("x",encoding="utf-8") as stream:
            json.dump(generated,stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    profile,mapping_sha=read_native_profile(mapping_profile,intake["source_sha256"],snapshot_sha,master_sha)
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
        request=JobRequest.new("verify_native_fbx_body",input_project="candidate.blend",
            options={**bindings,"render_private_frames":run==0})
        result,folder=runner.run(request,timeout_s=timeout_s,cancel=cancel,
            staged_inputs={"candidate.blend":master,"source_snapshot.json":snapshot_path,"native_mapping.json":mapping_profile})
        unchanged()
        if folder.is_symlink() or folder.resolve().parent!=(store.root/".ucc-jobs").resolve():
            raise ProjectStorageError("Native worker folder is redirected")
        for name,digest in (("candidate.blend",master_sha),("source_snapshot.json",snapshot_sha),("native_mapping.json",mapping_sha)):
            path=folder/name
            if path.is_symlink() or not path.is_file() or _digest(path,cancel)!=digest:
                raise ProjectStorageError("Native staged input changed during Blender evaluation")
        data,path=read_native_timeline(folder,result.details,source,profile,bindings,cancel_check=check_cancel)
        if run==0:
            if result.details.get("private_review_renders") is None:raise ValidationError("Native first worker did not render private skin views")
            first_data,first_report,first_folder,first_path=data,result.details,folder,path
        else:
            if result.details.get("private_review_renders") is not None:raise ValidationError("Native second worker rendered without request")
            # Saved Blender copies contain save metadata; compare every actual
            # matrix/skin/root/quality value, excluding only distinct copy IDs.
            if ({k:v for k,v in first_data.items() if k!="visual_review_blend"}!=
                    {k:v for k,v in data.items() if k!="visual_review_blend"}):
                raise ValidationError("Independent native target workers disagree on complete poses/skin/root evidence")
        ids.append(request.job_id)
    unchanged()
    bound_file(first_folder,first_report["timeline"],"target_timeline.json",64*1024*1024,cancel_check=check_cancel)
    action=bound_file(first_folder,first_report["visual_review_blend"],"review_motion.blend",512*1024*1024,cancel_check=check_cancel)
    review=verify_native_renders(first_folder,first_report,first_data)
    unchanged()
    return NativeBodyPreview(project.project_id,project.revision,master_sha,intake["source_sha256"],first_data,
                             str(action),review,str(first_path),tuple(ids),str(mapping_profile),first_report)
