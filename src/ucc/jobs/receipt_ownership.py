"""Ownership-safe invalidation of withdrawn export receipts; no engine imports."""
from pathlib import Path
import os


def invalidate_owned_receipt(path: Path, expected: bytes, owner: tuple[int, int]) -> bool:
    """Withdraw only our exact receipt (or its incomplete write), never a replacement.

    Use the opened inode rather than replacing a pathname after checking it.
    Invalidate JSON before rewriting so a later write/flush failure cannot leave
    our prior success claim readable. This runs only after folder withdrawal.
    """
    import json
    import stat
    from ucc.export.godot_candidate_contract import canonical_bytes
    if (path.resolve() != path or any(p.is_symlink()
            or getattr(p, 'is_junction', lambda:False)() for p in path.parents)):
        return False
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != owner:
        return False
    with path.open('r+b', buffering=0) as stream:
        info = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino) != owner:
            return False
        actual = stream.read(len(expected)+1)
        if not expected.startswith(actual):
            return False
        record = json.loads(expected)
        record.update(export_published=False, final_payload_verified=False,
            private_static_native_verified=False, publication_rolled_back=True)
        # A failed first receipt digest may simply mean the original total
        # budget expired. Bounded ownership repair must not reuse that budget.
        replacement = canonical_bytes(record)
        def write_all(data: bytes) -> None:
            remaining = memoryview(data)
            while remaining:
                count = stream.write(remaining)
                if type(count) is not int or not 0 < count <= len(remaining):
                    raise OSError('Owned receipt invalidation made no write progress')
                remaining = remaining[count:]
        stream.seek(0)
        write_all(b'\0')
        # Keep the opening byte invalid until the ENTIRE false-claim body is
        # present and flushed. A partial tail write can never restore old JSON.
        stream.seek(1)
        write_all(replacement[1:])
        stream.truncate(len(replacement))
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        write_all(replacement[:1])
        stream.flush()
        os.fsync(stream.fileno())
    return True
