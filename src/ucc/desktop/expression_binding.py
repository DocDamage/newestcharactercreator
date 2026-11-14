"""Publish only current complete evidence; revoke CPU/GPU data on disk changes."""
from PySide6.QtCore import QFileSystemWatcher

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.expression_clip import build_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import TARGETS
from ucc.jobs.expression_verification import registered_expression_source
from ucc.jobs.master_preview import _digest
from ucc.preview.expression_cache import read_expression_cache, read_json


def clear_expression(window):
    watcher = getattr(window, '_expression_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files()+watcher.directories()
        if paths: watcher.removePaths(paths)
    window._expression_preview = None
    viewer = getattr(window, 'expression_viewer', None)
    if viewer is not None: viewer.clear()
    dock = getattr(window, 'expression_dock', None)
    if dock is not None: dock.hide()


def _paths(store, result):
    paths = {store.root, store.file}
    for directory in (store.root/'master', store.root/'expressions', store.root/'parts',
                      result.workdir, result.verify_dir):
        if not directory.exists(): continue
        paths.add(directory); paths.add(directory.parent)
        # Directory watchers are not recursive. Every descendant is registered.
        for path in directory.rglob('*'):
            if len(paths) > 20000: raise ProjectStorageError('Expression watch set exceeds its safety bound')
            paths.add(path)
    for path in paths:
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(store.root):
            raise ProjectStorageError('Expression playback input is redirected outside the project')
    return paths


def _snapshot(paths):
    return {str(path): (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino) for path in paths}


def bind_expression(window, result):
    store = window.controller.store
    if store is None or window.controller.dirty:
        raise ProjectConflict('Expression preview requires the unchanged saved project')
    paths = _paths(store, result); before = _snapshot(paths)

    def unchanged():
        project = store.load()
        if (project != window.controller.require_project() or project.project_id != result.project_id
                or project.revision != result.revision or project.master_blend != result.master_blend
                or project.expression is None or project.expression.library_sha256 != result.library_sha256):
            raise ProjectConflict('Saved expression project changed before preview publication')
        registered_expression_source(store, project)
        for directory in (result.workdir, result.verify_dir):
            for target in TARGETS:
                path = directory/target.staged_name
                if path.is_symlink() or _digest(path) != result.bindings[target.role+'_'+target.family+'_sha256']:
                    raise ProjectStorageError('Expression target changed before publication')
            clip = read_json(directory/'expression_clip.json', result.clip_sha256, 128*1024)
            if canonical_digest(clip) != canonical_digest(build_expression_clip(project, result.master_sha256)):
                raise ProjectConflict('Expression preview strengths differ from the saved project')
            for name, field in (('candidate.blend', 'master_sha256'), ('expression_motion.blend', 'motion_sha256')):
                if _digest(directory/name) != result.bindings[field]:
                    raise ProjectStorageError('Expression saved scene changed before publication')
            report = read_json(directory/'expression_motion.json', result.bindings['motion_report_sha256'], 4*1024*1024)
            checked = read_expression_cache(directory, result.bindings, result.observed, report)
            if checked != result.cache:
                raise ProjectStorageError('Expression CPU buffers differ from independently verified disk evidence')

    unchanged()
    watcher = getattr(window, '_expression_watcher', None)
    if watcher is None:
        watcher = QFileSystemWatcher(window)
        watcher.fileChanged.connect(lambda _: clear_expression(window))
        watcher.directoryChanged.connect(lambda _: clear_expression(window))
        window._expression_watcher = watcher
    clear_expression(window); watcher.blockSignals(False)
    try:
        if watcher.addPaths(sorted(str(p) for p in paths)):
            raise ProjectStorageError('Cannot watch every expression playback input')
        unchanged()
        if _paths(store, result) != paths or _snapshot(paths) != before:
            raise ProjectConflict('Expression files changed while attaching playback watchers')
    except BaseException:
        clear_expression(window); raise
    window._expression_preview = result
