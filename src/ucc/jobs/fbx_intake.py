"""Two-process native FBX intake in private jobs; never changes a project master."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from threading import Event

from ucc.animations.fbx_snapshot import MAX_SOURCE_BYTES, read_snapshot
from ucc.core.errors import ValidationError
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from .protocol import JobRequest
from .runner import BlenderJobRunner, WorkerFailure


def inspect_selected_fbx(source: Path, *, blender_exe: Path, worker_script: Path,
                         jobs_root: Path, permission: LicensePolicy,
                         cancel: Event | None=None, timeout_s: float=300) -> dict:
    allowed,reason=permission.allow("local_preview")
    if not allowed:
        raise AssetPolicyError(reason)
    source=Path(source)
    if (source.suffix.lower() != ".fbx" or source.is_symlink() or not source.is_file() or
            not 0 < source.stat().st_size <= MAX_SOURCE_BYTES):
        raise ValidationError("Select a regular local FBX up to 256 MiB")
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise WorkerFailure("FBX intake cancelled; original source untouched")
    def digest(path):
        check_cancel()
        h=sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):
                check_cancel()
                h.update(chunk)
        return h.hexdigest()
    before=digest(source)
    runner=BlenderJobRunner(blender_exe,jobs_root,worker_script)
    first_report=first_data=first_path=None
    for _ in range(2):
        check_cancel()
        request=JobRequest.new("inspect_fbx_animation",options={"source_sha256":before})
        result,folder=runner.run(request,timeout_s=timeout_s,cancel=cancel,staged_inputs={"source.fbx":source})
        staged=folder/"source.fbx"
        if (source.is_symlink() or staged.is_symlink() or not source.is_file() or not staged.is_file() or
                digest(source) != before or digest(staged) != before):
            raise ValidationError("FBX source/staged bytes changed during intake")
        data,path=read_snapshot(folder,result.details,before,cancel_check=check_cancel)
        if first_report is None:
            first_report,first_data,first_path=result.details,data,path
        elif first_report != result.details or first_data != data:
            raise ValidationError("Independent Blender workers disagree on FBX rest/pose transforms")
    check_cancel()
    if source.is_symlink() or not source.is_file() or digest(source) != before:
        raise ValidationError("FBX original changed before intake completion")
    if (first_path.is_symlink() or not first_path.is_file() or
            digest(first_path) != first_report["snapshot"]["sha256"]):
        raise ValidationError("Private FBX snapshot changed before intake completion")
    return {**first_report,"format":"fbx","source_path":str(source.resolve()),"policy":permission.to_dict(),
            "private_snapshot":str(first_path),"two_workers_agree":True,"source_bytes_unchanged":True,
            "note":"Native source skeleton and all frames measured; target retargeting and visual quality unverified."}
