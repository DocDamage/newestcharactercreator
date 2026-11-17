"""Same-buffer reads and immutable authority for private source playback."""
from hashlib import sha256
import os
import stat
from pathlib import Path

from ucc.core.errors import ProjectStorageError
from .target_action_context import protected


def stamp(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def watch_identity(path: Path):
    """Cheap filesystem-only stamp; directories retain identity, not write time."""
    path = protected(Path(path))
    if not path.exists(): return (0, 0, 0, 0)
    value = path.stat()
    if stat.S_ISDIR(value.st_mode): return value.st_dev, value.st_ino, 0, 0
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ProjectStorageError('Source playback path is not an exclusively owned regular file')
    return stamp(value)


def capture(path: Path, maximum: int, budget, *, expected: str, retain=False):
    path = protected(path); budget.check(); before = path.stat()
    if not path.is_file() or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise ProjectStorageError('Source playback file is missing, shared or oversized')
    digest = sha256(); chunks = []; size = 0
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        for block in iter(lambda: stream.read(1024*1024), b''):
            budget.check(); size += len(block)
            if size > maximum: raise ProjectStorageError('Source playback file grew beyond its bound')
            digest.update(block)
            if retain: chunks.append(block)
        finished = os.fstat(stream.fileno())
    after = protected(path).stat(); budget.check()
    if (len({stamp(s) for s in (before, opened, finished, after)}) != 1
            or any(s.st_nlink != 1 for s in (opened, finished, after))
            or before.st_ctime_ns != after.st_ctime_ns
            or opened.st_ctime_ns != finished.st_ctime_ns
            or size != before.st_size or digest.hexdigest() != expected):
        raise ProjectStorageError('Source playback bytes or identity changed')
    return b''.join(chunks) if retain else None, stamp(after)


def check_identities(identities, budget):
    for path, expected in identities.items():
        budget.check(); protected(path)
        if expected == (0, 0, 0, 0):
            if path.exists(): raise ProjectStorageError('Source playback namespace changed')
        elif (not path.exists() or watch_identity(path) != expected
              or path.is_file() and path.stat().st_nlink != 1):
            raise ProjectStorageError('Source playback identity changed: '+str(path))
