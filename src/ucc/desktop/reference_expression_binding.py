"""Bounded source-aware publication of an explicitly owner-bound facial cache."""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.jobs.reference_expression_evidence import check_referenced_expression_preview
from ucc.jobs.master_preview import _digest
from .expression_binding import clear_expression

MAX_PATHS = 20000


def _stat(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino


def catalog_signature(database: Path):
    """SHM is coordination, and an empty WAL has no committed data pages."""
    try:
        canonical = database.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ProjectStorageError('Expression source catalog disappeared or was redirected') from error
    if database.is_symlink() or not database.is_file() or canonical != database:
        raise ProjectStorageError('Expression source catalog disappeared or was redirected')
    wal = Path(str(database)+'-wal')
    if wal.is_symlink(): raise ProjectStorageError('Expression catalog WAL is redirected')
    return (_stat(database), _digest(database)), ((_stat(wal), _digest(wal))
            if wal.is_file() and wal.stat().st_size > 32 else None)


def _owned_paths(store, result):
    database = result.database_path
    coordination = {database, Path(str(database)+'-wal'), Path(str(database)+'-shm')}
    paths = {store.root, store.file}
    for directory in (store.root/'master', store.root/'expressions', store.root/'parts',
                      store.root/'animations', result.context.store.root):
        if not directory.exists(): continue
        paths.update((directory, directory.parent))
        for path in directory.rglob('*'):
            if path not in coordination: paths.add(path)
            if len(paths) > MAX_PATHS:
                raise ProjectStorageError('Referenced expression watch set exceeds its safety bound')
    for path in paths:
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(store.root):
            raise ProjectStorageError('Referenced expression dependency escapes its owner')
    return paths-coordination


def _files_snapshot(paths):
    return {str(p): _stat(p) for p in paths if p.is_file()}


def _ancestors(paths) -> set[Path]:
    """Watch directory entries along authorized paths; never enumerate them."""
    parents = set()
    for path in paths:
        for parent in path.parents:
            parents.add(parent)
            if len(parents) > MAX_PATHS:
                raise ProjectStorageError('Referenced expression watch set exceeds its safety bound')
    return parents


def _directory_ids(paths) -> dict[str, tuple[int, int]]:
    identities = {}
    for value in paths:
        path = Path(value)
        if path.is_dir():
            info = path.stat(); identities[str(path)] = (info.st_dev, info.st_ino)
    return identities


def _canonical_sources(result) -> bool:
    try:
        return all(not p.is_symlink() and p.resolve(strict=True) == p for p in result.source_paths)
    except (OSError, RuntimeError):
        return False


def _arm_wal(window, state):
    wal = Path(str(state['database'])+'-wal')
    if wal.exists():
        if wal.is_symlink(): raise ProjectStorageError('Expression catalog WAL is redirected')
        watcher = window._reference_expression_watcher
        if str(wal) not in watcher.files():
            if len(watcher.files())+len(watcher.directories()) >= MAX_PATHS or not watcher.addPath(str(wal)):
                if not wal.exists(): return  # Transient empty coordination file already closed.
                raise ProjectStorageError('Cannot watch the source catalog WAL')
        state['watched'].add(str(wal))


def _changed(window, path):
    state = getattr(window, '_reference_expression_state', None)
    if state is None or path not in state['watched']: return
    database = state['database']; wal = Path(str(database)+'-wal')
    if Path(path) in (database, wal) or path in state['directories']:
        try:
            _arm_wal(window, state)
            if (catalog_signature(database) == state['catalog']
                    and _canonical_sources(state['result'])
                    and _directory_ids(state['directories']) == state['directory_ids']
                    and _owned_paths(window.controller.store, state['result']) == state['owned']
                    and all(Path(p).is_file() and _stat(Path(p)) == signature
                            for p, signature in state['files'].items())):
                return
        except (OSError, RuntimeError, ProjectStorageError):
            pass
    clear_expression(window)


def bind_referenced_expression(window, result):
    store = window.controller.store
    if (store is None or window.controller.dirty or window.controller.require_project() != result.project
            or window._catalog_path().resolve(strict=True) != result.database_path):
        raise ProjectConflict('Referenced expression requires the unchanged saved owner and selected catalog')
    check_referenced_expression_preview(store, result.database_path, result)
    owned = _owned_paths(store, result)
    external = set(result.source_paths)
    # Exact registered files and ancestor directory entries are watched.
    # A parent handle alone can follow a renamed directory and miss its alias.
    # External directories are never enumerated, recursively or otherwise.
    for path in external:
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
            raise ProjectStorageError('Registered expression source is missing or redirected')
    paths = owned | external | {result.database_path} | _ancestors((store.root, result.database_path, *external))
    if len(paths) >= MAX_PATHS:
        raise ProjectStorageError('Referenced expression watch set exceeds its safety bound')
    files = _files_snapshot(owned | external); catalog = catalog_signature(result.database_path)
    directory_ids = _directory_ids(paths)
    watcher = getattr(window, '_reference_expression_watcher', None)
    if watcher is None:
        watcher = QFileSystemWatcher(window)
        watcher.fileChanged.connect(lambda path: _changed(window, path))
        watcher.directoryChanged.connect(lambda path: _changed(window, path))
        window._reference_expression_watcher = watcher
    clear_expression(window)
    state = {'database': result.database_path, 'catalog': catalog, 'files': files,
             'result': result, 'owned': owned, 'directories': set(directory_ids), 'directory_ids': directory_ids,
             'watched': {str(p) for p in paths}}
    window._reference_expression_state = state; watcher.blockSignals(False)
    try:
        if watcher.addPaths(sorted(state['watched'])):
            raise ProjectStorageError('Cannot watch every referenced expression input')
        _arm_wal(window, state)
        check_referenced_expression_preview(store, result.database_path, result)
        if (window.controller.dirty or window.controller.require_project() != result.project
                or not _canonical_sources(result)
                or _owned_paths(store, result) != owned or _files_snapshot(owned | external) != files
                or _directory_ids(paths) != directory_ids
                or catalog_signature(result.database_path) != catalog):
            raise ProjectConflict('Referenced expression inputs changed while attaching playback watchers')
        window._expression_preview = result
    except BaseException:
        clear_expression(window); raise
