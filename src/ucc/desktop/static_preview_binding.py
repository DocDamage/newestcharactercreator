"""Invalidate a complete static preview when its saved authority changes."""
from PySide6.QtCore import QFileSystemWatcher

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.jobs.master_preview import _digest, _master_file


def clear_binding(window):
    watcher = getattr(window, '_static_preview_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files()+watcher.directories()
        if paths:
            watcher.removePaths(paths)


def bind_preview(window, result):
    store = window.controller.store
    if store is None:
        raise ProjectConflict('Saved static preview no longer has an open project')
    def unchanged():
        actual = store.load()
        if (actual.project_id != result.project_id or actual.revision != result.revision
                or actual.master_blend != result.master_blend):
            raise ProjectConflict('Saved project changed before complete static preview publication')
        path, expected = _master_file(store, actual.master_blend)
        if expected != result.master_sha256 or _digest(path) != result.master_sha256:
            raise ProjectStorageError('Saved master changed before complete static preview publication')
        for name,sha in result.watched_inputs:
            from pathlib import Path
            source=Path(name)
            if source.is_symlink() or not source.is_file() or _digest(source)!=sha:
                raise ProjectStorageError('Saved material preview proof or source changed before publication')
        return path
    master = unchanged()
    watcher = getattr(window, '_static_preview_watcher', None)
    if watcher is None:
        watcher = QFileSystemWatcher(window)
        watcher.fileChanged.connect(lambda _path: window._clear_preview())
        watcher.directoryChanged.connect(lambda _path: window._clear_preview())
        window._static_preview_watcher = watcher
    clear_binding(window)
    watcher.blockSignals(False)
    paths = {str(store.file), str(master), str(store.root), str(master.parent), str(master.parent.parent)}
    for name,_ in result.watched_inputs:
        from pathlib import Path
        paths.update((name,str(Path(name).parent)))
    paths=sorted(paths)
    if watcher.addPaths(paths):
        clear_binding(window)
        raise ProjectStorageError('Cannot watch every complete static preview input')
    try:
        unchanged()
    except BaseException:
        clear_binding(window)
        raise
