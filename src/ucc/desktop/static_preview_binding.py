"""Invalidate a complete static preview when its saved authority changes."""
from PySide6.QtCore import QFileSystemWatcher

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.master_preview import _digest, _master_file


def clear_binding(window):
    window._static_preview_directory_guard = None
    watcher = getattr(window, '_static_preview_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files()+watcher.directories()
        if paths:
            watcher.removePaths(paths)


def _directory_changed(window):
    guard = getattr(window, '_static_preview_directory_guard', None)
    if guard is not None:
        try:
            guard()
            return
        except (UCCError, OSError, ValueError):
            pass
    window._clear_preview()


def bind_preview(window, result, *, isolate_workspace=False):
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
        watcher.directoryChanged.connect(lambda _path: _directory_changed(window))
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
        if isolate_workspace:
            from pathlib import Path
            stamps = {Path(path): identity(Path(path)) for path in paths}

            def directory_guard():
                if (window.controller.store is not store or window.controller.dirty
                        or any(path.is_symlink() or identity(path) != stamp for path, stamp in stamps.items())):
                    raise ProjectConflict('Saved workspace preview inputs changed')
                unchanged()

            directory_guard()
            window._static_preview_directory_guard = directory_guard
    except BaseException:
        clear_binding(window)
        raise
