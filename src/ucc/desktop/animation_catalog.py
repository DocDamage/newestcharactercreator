"""Existing catalog controls: metadata indexing or explicitly reviewed FBX intake."""
import os
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog

from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError, LicensePolicy
from .generation import bundled_worker_path


def start_index(window, file: str, asset_id: str, provider: str, license_name: str, uri: str) -> None:
    if window.jobs.busy:
        window._error('Another local task is still running'); return
    asset_id, provider, license_name, uri = (v.strip() for v in (asset_id, provider, license_name, uri))
    if not file or not asset_id or not provider or not uri:
        window._error('Choose a source and enter an asset ID, provider and actual source URI'); return
    source = Path(file)
    database = window._catalog_path()
    if source.suffix.lower() != '.fbx' or not window.animations.local_preview_review.isChecked():
        def metadata_only():
            with AnimationCatalog(database) as catalog:
                return catalog.index_file(asset_id, source, LicensePolicy(provider, license_name, uri)).to_dict()
        window._submit('index', metadata_only)
        return
    if license_name.casefold() in {'', 'unknown', 'unreviewed', 'n/a'}:
        window._error('Enter the actual FBX license before confirming local Blender rights'); return
    if not source.is_file() or source.is_symlink():
        window._error('Choose a regular local FBX animation file'); return
    if window.controller.store is None:
        window._error('Open a project to hold the private FBX measurement jobs'); return
    executable = window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        selected, _ = QFileDialog.getOpenFileName(window, 'Choose installed Blender for FBX catalog intake', '',
            'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
        if not selected: return
        executable = Path(selected)
        if executable.is_symlink() or not executable.is_file():
            window._error('Choose a regular installed Blender executable'); return
        window._blender_executable = executable
    try:
        worker = bundled_worker_path()
        policy = LicensePolicy(provider, license_name, uri, reviewed=True, local_preview_allowed=True, no_ai=True)
    except (UCCError, ValueError) as error:
        window._error(str(error)); return
    jobs_root = window.controller.store.root/'.ucc-jobs'
    cancel = Event()

    def measured():
        if cancel.is_set():
            raise WorkerFailure('FBX catalog indexing cancelled; previous catalog retained')
        with AnimationCatalog(database) as catalog:
            previous = catalog.library.get(asset_id)
            if previous is not None and previous.policy != policy:
                raise AssetPolicyError('This asset ID has a different saved license review. '
                                       'Keep it unchanged and choose a new asset ID for the reviewed source.')
            catalog.index_file(asset_id, source, policy)
        result = measure_catalog_fbx(database, asset_id, blender_exe=executable, worker_script=worker,
            jobs_root=jobs_root, cancel=cancel)
        with AnimationCatalog(database) as catalog:
            rows = [item.to_dict() for item in catalog.list_sources()]
        return {'source': result, 'catalog': rows}

    window._submit('fbx_catalog', measured, cancel=cancel)


def finish_index(window, result: dict) -> None:
    source = result['source']; clip, = source['clips']
    window.animations.display_catalog(result['catalog'])
    window.log.setPlainText(f"Indexed {source['asset_id']}: {clip['name']}\n"
        f"Complete source clip: {clip['frame_count']} frames at {clip['fps']:g} fps.\n"
        'Two independent Blender runs agree; the original source is unchanged.\n'
        'No animation was applied to the character. Character preview, visual quality and engine import remain unverified.')
