"""Measure one already-indexed reviewed FBX before atomically publishing metadata."""
from pathlib import Path
from threading import Event

from ucc.animations.catalog import AnimationCatalog
from ucc.animations.fbx_snapshot import read_snapshot
from ucc.core.errors import ValidationError
from ucc.jobs.fbx_intake import inspect_selected_fbx
from ucc.jobs.master_preview import _digest
from ucc.jobs.runner import WorkerFailure


def measure_catalog_fbx(database_path: Path, asset_id: str, *, blender_exe: Path,
                        worker_script: Path, jobs_root: Path, cancel: Event | None = None,
                        timeout_s: float = 300) -> dict:
    """Register source metadata only; never attach an Action or edit a project."""
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise WorkerFailure('FBX catalog measurement cancelled; catalog metadata unchanged')

    check_cancel()
    with AnimationCatalog(database_path) as catalog:
        entry = catalog.library.get(asset_id)
        indexed = catalog.get(asset_id)
        if entry is None or indexed is None or indexed.source_format != 'fbx':
            raise ValidationError('Select an existing indexed FBX asset ID')
        catalog.library.require_permission(asset_id, 'local_preview')
        source = Path(entry.source_path)
        if source.is_symlink() or not source.is_file() or _digest(source, cancel) != entry.sha256:
            raise ValidationError('Indexed FBX source is missing, redirected or changed')
        intake = inspect_selected_fbx(source, blender_exe=blender_exe, worker_script=worker_script,
            jobs_root=jobs_root, permission=entry.policy, cancel=cancel, timeout_s=timeout_s)
        check_cancel()
        if (intake.get('two_workers_agree') is not True or intake.get('source_bytes_unchanged') is not True
                or intake.get('source_sha256') != entry.sha256 or intake.get('policy') != entry.policy.to_dict()
                or intake.get('source_path') != str(source.resolve())):
            raise ValidationError('FBX intake differs from the exact indexed source and permissions')
        snapshot = Path(intake['private_snapshot'])
        if snapshot.parent.is_symlink() or not snapshot.resolve().is_relative_to(Path(jobs_root).resolve()):
            raise ValidationError('FBX catalog snapshot escaped its private jobs directory')
        data, _ = read_snapshot(snapshot.parent, intake, entry.sha256, cancel_check=check_cancel)
        catalog.record_fbx_intake(asset_id, data, intake, expected_entry=entry, cancel_check=check_cancel)
        return catalog.get(asset_id).to_dict()
