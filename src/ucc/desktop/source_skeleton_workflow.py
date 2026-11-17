"""Explicit local source preview; GUI guards only inspect bounded path identities."""
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMessageBox

from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError, ValidationError
from ucc.jobs.runner import WorkerFailure
from ucc.jobs.source_skeleton_files import watch_identity
from ucc.jobs.source_skeleton_preview import LoadedSourceSkeletonPreview, prepare_source_skeleton_preview
from .generation import bundled_worker_path
from .source_skeleton_viewer import SourceSkeletonViewer


@dataclass(frozen=True, slots=True)
class SourceSkeletonCompletion:
    token: object
    prepared: LoadedSourceSkeletonPreview


def clear_source_skeleton(window, message=None, *, cancel_pending=True) -> None:
    if cancel_pending:
        pending = getattr(window, '_source_skeleton_pending', None)
        if pending is not None:
            pending[2].set()
        window._source_skeleton_pending = None
    watcher = getattr(window, '_source_skeleton_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files()+watcher.directories()
        if paths:
            watcher.removePaths(paths)
    viewer = getattr(window, '_source_skeleton_viewer', None)
    if viewer is not None:
        viewer.clear()
        window._source_skeleton_dock.hide()
    window._source_skeleton_result = None
    window._source_skeleton_owner = None
    if message:
        window.log.setPlainText(message+'\nValidate the selected source again to reopen its skeleton.')


def _selected_asset(window):
    table = window.animations.catalog
    item = table.item(table.currentRow(), 0)
    return item.text() if item is not None else None


def _current(window) -> bool:
    result = getattr(window, '_source_skeleton_result', None)
    selected = _selected_asset(window)
    if (result is None or window.controller.store is not window._source_skeleton_owner
            or not selected or selected+'#clip-0000' != result.clip_id):
        return False
    try:
        return all(watch_identity(path) == identity for path, identity in result.watched_identities.items())
    except (UCCError, OSError, ValueError):
        return False


class SourceSkeletonDock(QDockWidget):
    def __init__(self, window):
        super().__init__('Private measured source skeleton', window)
        self.owner = window

    def closeEvent(self, event):
        clear_source_skeleton(self.owner)
        event.accept()


def start_source_skeleton(window) -> None:
    if window.jobs.busy:
        window._error('Another local task is still running'); return
    if not window.controller.has_project or window.controller.store is None:
        window._error('Open a saved project to hold private source-preview jobs'); return
    asset_id = _selected_asset(window)
    if not asset_id:
        window._error('Select a measured FBX source from the animation catalog'); return
    answer = QMessageBox.question(window, 'Private source skeleton preview',
        'Read the selected source in two local Blender workers and show its measured skeleton? '
        'The existing reviewed local-preview policy must permit this operation. '
        'Private job snapshots stay in the current project. No character animation is applied.',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
    if answer != QMessageBox.StandardButton.Yes:
        return
    executable = window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        selected, _ = QFileDialog.getOpenFileName(window, 'Choose installed Blender for source preview', '',
            'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
        if not selected:
            return
        executable = Path(selected)
        if executable.is_symlink() or not executable.is_file():
            window._error('Choose a regular installed Blender executable'); return
        window._blender_executable = executable
    try:
        worker = bundled_worker_path()
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error)); return
    clear_source_skeleton(window)
    database = window._catalog_path()
    store = window.controller.store
    cancel = Event()
    token = object()
    window._source_skeleton_pending = (token, store, cancel)

    def prepare():
        if cancel.is_set():
            raise WorkerFailure('Source-skeleton preview cancelled')
        with AnimationCatalog(database, read_only=True) as catalog:
            entry = catalog.library.get(asset_id)
            if entry is None:
                raise ValidationError('Selected source is no longer in the catalog')
            catalog.library.require_permission(asset_id, 'local_preview')
        result = prepare_source_skeleton_preview(database, asset_id+'#clip-0000',
            expected_source_sha256=entry.sha256, expected_policy=entry.policy,
            local_preview_confirmed=True, blender_exe=executable, worker_script=worker,
            jobs_root=store.root/'.ucc-jobs', cancel=cancel)
        if cancel.is_set():
            raise WorkerFailure('Source-skeleton preview cancelled; private jobs are retained')
        return SourceSkeletonCompletion(token, result)

    window._submit('source_skeleton', prepare, cancel=cancel)


def finish_source_skeleton(window, result) -> None:
    pending = getattr(window, '_source_skeleton_pending', None)
    if (pending is None or not isinstance(result, SourceSkeletonCompletion)
            or result.token is not pending[0]):
        return
    window._source_skeleton_pending = None
    _, owner, cancel = pending
    if cancel.is_set():
        clear_source_skeleton(window)
        window.log.setPlainText('Source-skeleton preview cancelled; private jobs are retained')
        return
    result = result.prepared
    if not isinstance(result, LoadedSourceSkeletonPreview):
        clear_source_skeleton(window)
        window._error('Source-preview preparation returned an invalid result'); return
    if owner is None or window.controller.store is not owner:
        window._error('The source-preview project changed; validate the selected source again'); return
    window._source_skeleton_result = result
    window._source_skeleton_owner = owner
    if not _current(window):
        clear_source_skeleton(window, 'The source-preview inputs changed before display'); return
    if getattr(window, '_source_skeleton_viewer', None) is None:
        viewer = SourceSkeletonViewer(lambda: _current(window))
        dock = SourceSkeletonDock(window)
        dock.setObjectName('SourceSkeletonPreviewDock')
        dock.setWidget(viewer)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        viewer.invalidated.connect(lambda: clear_source_skeleton(window, 'Source-preview inputs changed'))
        window._source_skeleton_viewer = viewer
        window._source_skeleton_dock = dock
    watcher = getattr(window, '_source_skeleton_watcher', None)
    if watcher is None:
        watcher = QFileSystemWatcher(window)
        watcher.fileChanged.connect(lambda _: clear_source_skeleton(window, 'A source-preview input changed'))
        watcher.directoryChanged.connect(lambda _: clear_source_skeleton(window, 'A source-preview directory changed'))
        window._source_skeleton_watcher = watcher
    watcher.blockSignals(False)
    rejected = watcher.addPaths([str(path) for path in result.watch_paths])
    if rejected or not _current(window):
        clear_source_skeleton(window, 'Source-preview inputs could not be monitored'); return
    window._source_skeleton_viewer.show_cache(result.cache)
    if getattr(window, '_source_skeleton_result', None) is None:
        return
    window._source_skeleton_dock.show()
    window.log.setPlainText('Private source skeleton loaded from two agreeing Blender measurements.\n'
        'Front and side views show measured bone endpoints. No skin or character mapping is applied.\n'
        'Retargeting, visual quality, loop quality, usable-motion and engine acceptance remain unverified.')


def source_skeleton_error(window, error: str) -> None:
    clear_source_skeleton(window)
    window._error(error)
