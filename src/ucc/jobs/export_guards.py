"""Bounded source identities and cancellation shared by new export adapters.

These preserve the accepted Character traversal/budget algorithms. Existing Character
entry points remain unchanged while other adapters use this neutral boundary.
"""
from pathlib import Path
from threading import Event
from collections.abc import Iterator
import math
import os
import time
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from .godot_candidate_inputs import identity
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel


def bounded_paths(root: Path, cancel=None, *, maximum_entries: int=8192,
        counter: list[int] | None=None, allowed_directories: frozenset[str] | None=None) -> Iterator[Path]:
    """Stream a canonical tree without queuing children or following redirects.

    The entry budget includes directories and missing selected roots. Shared
    counters bound a multi-root closure. Check before requesting each next entry,
    so reaching the hard limit rejects conservatively without probing further.
    """
    used = [0] if counter is None else counter

    def check() -> None:
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError('Character input traversal cancelled or total deadline exceeded')
        if used[0] >= maximum_entries:
            raise ProjectStorageError('Character input traversal reached its bounded entry limit')

    def canonical(path: Path) -> None:
        if path.is_symlink() or getattr(path, 'is_junction', lambda:False)() or path.resolve() != path:
            raise ProjectStorageError('Character input traversal contains a redirected path')

    def visit(path: Path, depth: int) -> Iterator[Path]:
        check(); used[0] += 1
        canonical(path)
        directory = path.is_dir()
        if directory:
            if (path != root and allowed_directories is not None
                    and path.relative_to(root).as_posix() not in allowed_directories):
                raise ProjectStorageError('Character export contains an unlisted directory or cache')
            if depth >= 128:
                raise ProjectStorageError('Character input traversal exceeds its bounded directory depth')
        elif path.exists() and not path.is_file():
            raise ProjectStorageError('Character input traversal contains an unsupported filesystem entry')
        yield path
        if directory:
            check(); canonical(path)
            with os.scandir(path) as children:
                while True:
                    check()
                    try:
                        entry = next(children)
                    except StopIteration:
                        break
                    yield from visit(path/entry.name, depth+1)

    yield from visit(root, 0)



def protected_file(path: Path) -> None:
    # Empty Python package markers are valid protected inputs too.
    if (path.is_symlink() or not path.is_file() or path.resolve() != path
            or path.stat().st_size > 512*1024*1024
            or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)() for p in path.parents)):
        raise ProjectStorageError('Character export protected input is missing, redirected or oversized')



def source_snapshot(store: ProjectStore, cancel) -> dict:
    """Freeze all saved provenance/ancestry, including identical-byte replacements."""
    result = {}
    counter = [0]
    for name in ('master', 'expressions', 'parts', 'materials', 'history'):
        root = store.root/name
        for path in bounded_paths(root, cancel, counter=counter):
            key = path.relative_to(store.root).as_posix()
            if not path.exists():
                result[key] = None
            elif path.is_file():
                protected_file(path)
                result[key] = (identity(path), _digest(path, cancel))
            elif path.is_dir():
                result[key] = identity(path)
            else:
                raise ProjectStorageError('Character source closure contains an unsupported filesystem entry')
    return result



def cancel_context(cancel, deadline: float) -> tuple[float, bool]:
    """Separate actual user flags from deadlines in known nested cancel budgets."""
    current = cancel
    seen = set()
    user_cancelled = False
    while isinstance(current, _BudgetCancel):
        if id(current) in seen or len(seen) >= 64:
            raise ValidationError('Character export cancellation budget chain is cyclic or too deep')
        seen.add(id(current))
        if Event.is_set(current):
            user_cancelled = True
        if type(current.deadline) not in (int, float) or not math.isfinite(current.deadline):
            raise ValidationError('Character export cancellation budget has an invalid deadline')
        deadline = min(deadline, current.deadline)
        current = current.user
    if current is not None and current.is_set():
        user_cancelled = True
    return deadline, user_cancelled



def failure_reason(cancel, deadline: float) -> tuple[str | None, str | None]:
    deadline, user_cancelled = cancel_context(cancel, deadline)
    if user_cancelled:
        return 'user_cancel', 'Character export cancelled by caller; saved character preserved'
    if time.monotonic() >= deadline:
        return 'total_deadline', 'Character export total deadline exceeded; saved character preserved'
    return None, None



from .receipt_ownership import invalidate_owned_receipt
