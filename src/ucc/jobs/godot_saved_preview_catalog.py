"""Fence catalog semantic files around the final logical permission guard."""
from pathlib import Path
from ucc.core.errors import ProjectStorageError
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import hash_file
from .target_action_context import protected

MAX_CATALOG_BYTES=512*1024*1024


def coordination_paths(database:Path) -> tuple[Path,...]:
    return (database,*[database.with_name(database.name+suffix) for suffix in ('-wal','-shm','-journal')])


def _snapshot(database,budget):
    rows={}
    for path in coordination_paths(database):
        budget.check();protected(path)
        if not path.exists():
            if path==database:raise ProjectStorageError('Saved-preview catalog disappeared')
            rows[path]=None;continue
        before=identity(path)
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ProjectStorageError('Saved-preview catalog coordination path changed ownership')
        if path.name==database.name+'-shm':
            # Read marks are coordination, never authority for permissions.
            rows[path]=(before,None,before[2]);continue
        digest,size=hash_file(path,MAX_CATALOG_BYTES,budget)
        if identity(protected(path))!=before:
            raise ProjectStorageError('Saved-preview catalog changed during byte fence')
        rows[path]=(before,digest,size)
    return rows


def _identities(rows,budget):
    for path,row in rows.items():
        budget.check();protected(path)
        if row is None:
            if path.exists():raise ProjectStorageError('Saved-preview catalog namespace changed after permission guard')
        elif (identity(path)!=row[0] or path.stat().st_nlink!=1):
            raise ProjectStorageError('Saved-preview catalog identity changed after permission guard')


def final_catalog_guard(database,budget,logical_guard):
    """Return only identities associated with a fenced logical rights check.

    A read-only SQLite connection may create/remove an EMPTY WAL and alter SHM
    read marks. Only absent/zero-byte WAL transitions are allowed. Main/journal
    bytes and ownership cannot change; any nonempty WAL change fails closed.
    """
    parent=identity(protected(database.parent));before=_snapshot(database,budget)
    logical_guard()
    after=_snapshot(database,budget)
    for path in (database,database.with_name(database.name+'-wal'),database.with_name(database.name+'-journal')):
        if before[path]==after[path]:continue
        empty_wal=(path.name==database.name+'-wal'
                   and all(row is None or row[2]==0 for row in (before[path],after[path])))
        if not empty_wal:
            raise ProjectStorageError('Saved-preview catalog semantic bytes changed during final permission guard')
    if identity(protected(database.parent))!=parent:
        raise ProjectStorageError('Saved-preview catalog parent replaced during final permission guard')
    _identities(after,budget)
    return {path:row[0] if row is not None else (0,0,0,0) for path,row in after.items()}
