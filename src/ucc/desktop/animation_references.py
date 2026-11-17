"""Explicit source-reference controls; master and source geometry stay unchanged."""
import os
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog

from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError, ValidationError
from ucc.jobs.project_animation_references import attach_catalog_reference, detach_catalog_reference
from .generation import bundled_worker_path


def refresh_reference_controls(window) -> None:
    ready = (window.controller.has_project and window.controller.store is not None and not window.controller.dirty
             and window.controller.require_project().master_blend is not None and not window.jobs.busy)
    window.animations.set_reference_target_ready(ready)


def start_reference(window, *, remove: bool = False) -> None:
    if window.jobs.busy:
        window._error('Another local task is still running'); return
    if not window.controller.has_project or window.controller.store is None:
        window._error('Open a saved character project first'); return
    snapshot = window.controller.require_project()
    if window.controller.dirty or snapshot.master_blend is None:
        window._error('Save the character and generate its neutral master before changing source references'); return
    pane = window.animations; database = None
    try:
        if remove:
            selected = pane.references.currentItem()
            if selected is None: raise ValidationError('Select a character source reference to detach')
            clip_id = selected.text()
            if clip_id not in snapshot.animations: raise ValidationError('Selected reference is no longer attached')
            entry = None
        else:
            database = window._catalog_path()
            row = pane.catalog.currentRow()
            if row < 0 or pane.catalog.item(row, 0) is None:
                raise ValidationError('Select one measured FBX source from the catalog')
            asset_id = pane.catalog.item(row, 0).text()
            with AnimationCatalog(database, **({'read_only': True} if getattr(window, '_catalog_override', None) is not None else {})) as catalog:
                entry = catalog.library.get(asset_id); indexed = catalog.get(asset_id)
                if (entry is None or indexed is None or indexed.source_format != 'fbx'
                        or indexed.status != 'METADATA_EXTRACTED' or len(indexed.clips) != 1
                        or indexed.clips[0].ordinal != 0):
                    raise ValidationError('Choose a measured single-Action FBX source; index it with reviewed local rights first')
                catalog.library.require_permission(asset_id, 'local_preview')
            clip_id = asset_id+'#clip-0000'
        executable = window._blender_executable
        if executable is None or executable.is_symlink() or not executable.is_file():
            selected, _ = QFileDialog.getOpenFileName(window, 'Choose installed Blender for source-reference checks', '',
                'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
            if not selected: return
            executable = Path(selected)
            if executable.is_symlink() or not executable.is_file():
                raise ValidationError('Choose a regular installed Blender executable')
            window._blender_executable = executable
        worker = bundled_worker_path()
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error)); return
    store = window.controller.store; cancel = Event()
    common = dict(blender_exe=executable, worker_script=worker, expected_project_id=snapshot.project_id,
                  expected_revision=snapshot.revision, expected_master_blend=snapshot.master_blend, cancel=cancel)
    if remove:
        window._submit('animation_reference_detach', lambda: detach_catalog_reference(store, clip_id, **common), cancel=cancel)
    else:
        window._submit('animation_reference_attach', lambda: attach_catalog_reference(store, database, clip_id,
            expected_source_sha256=entry.sha256, expected_policy=entry.policy, **common), cancel=cancel)


def finish_reference(window, result) -> None:
    try:
        window.controller.accept_saved_animation_references(result.project)
        window._clear_preview(); window.refresh_project()
    except (UCCError, OSError, ValueError) as error:
        window._error('Reference result was saved but the desktop changed. Reopen the saved project. '+str(error)); return
    action = ('Source reference attached' if result.operation == 'attach' else 'Source reference detached') if result.changed else 'Source references already match'
    window.log.setPlainText(action+': '+result.clip_id+'\n'
        'The editable master, body, parts and expressions are unchanged.\n'
        'Source references are saved with the character. Target playback, editing with references and engine acceptance remain unverified.')


def show_reference_error(window, error: str) -> None:
    window._clear_preview()
    window.refresh_project()
    window._error(error)
