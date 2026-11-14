"""Read fixed installed MPFB assets through the selected Blender; never scan/install."""
from pathlib import Path
from threading import Event

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.facial import FACE_BASE_SHA256, FACE_RIG_SHA256, NOSE_TARGETS, MPFB_VERSION
from .face_revision import bundled_face_assets
from .geometry_evidence import EvidenceError
from .protocol import JobRequest
from .runner import BlenderJobRunner


def discover_face_data(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
                       cancel: Event | None = None, timeout_s: float = 300) -> Path:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Facial asset inspection cancelled')
    for path in (Path(blender_exe), Path(worker_script)):
        if path.is_symlink() or not path.is_file():
            raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    jobs = store.root/'.ucc-jobs'
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError('Facial asset inspection jobs directory is redirected')
    result, _ = BlenderJobRunner(blender_exe, jobs, worker_script).run(
        JobRequest.new('inspect_mpfb_face_assets'), cancel=cancel, timeout_s=timeout_s)
    info = result.details
    if (set(info) != {'schema_version', 'mpfb_version', 'data_directory', 'asset_sha256', 'installed_or_downloaded'}
            or type(info['schema_version']) is not int or info['schema_version'] != 1
            or info['mpfb_version'] != MPFB_VERSION or info['installed_or_downloaded'] is not False
            or type(info['data_directory']) is not str or not Path(info['data_directory']).is_absolute()
            or info['asset_sha256'] != {'base': FACE_BASE_SHA256, 'rig': FACE_RIG_SHA256,
                                       **{t.role: t.sha256 for t in NOSE_TARGETS}}):
        raise EvidenceError('Selected Blender did not identify the exact installed MPFB facial assets')
    data = Path(info['data_directory'])
    bundled_face_assets(data, cancel)
    return data
