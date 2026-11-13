"""Two-process read-only closed-skin diagnostic; no automatic fit approval."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy
from ucc.preview.skin_inclusion import SkinInclusion
from .native_body import NativeBodyPreview
from .native_playback import NativePlayback
from .fitted_playback import FittedPlayback


@dataclass(frozen=True,slots=True)
class SkinInclusionReview:
    project_id: str
    revision: int
    master_sha256: str
    source_sha256: str
    observations: SkinInclusion
    original_playback: NativePlayback
    fitted_playback: FittedPlayback | None
    worker_job_ids: tuple[str,str]
    private_report: str
    report_sha256: str
    bindings: tuple[tuple[str,str],...]
    metadata_sha256: str


def review_skin_inclusion(store: ProjectStore,preview: NativeBodyPreview,playback: NativePlayback,*,source_fbx: Path,
                          permission: LicensePolicy,blender_exe: Path,worker_script: Path,fitted: FittedPlayback | None=None,
                          cancel: Event | None=None,timeout_s: float=1800) -> SkinInclusionReview:
    from .body_contact_review import _review_body
    return _review_body(store,preview,playback,source_fbx=source_fbx,permission=permission,blender_exe=blender_exe,
        worker_script=worker_script,fitted=fitted,cancel=cancel,timeout_s=timeout_s,skin_inclusion=True)
