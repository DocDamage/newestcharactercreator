"""Filesystem-only admission of an explicitly selected session catalog."""
from pathlib import Path
import stat

from ucc.core.errors import ValidationError


def existing_catalog_path(path: Path) -> Path:
    """Select one existing local file without SQL, creation or alias expansion.

    This checks location only. Existing catalog consumers validate the SQLite
    schema and permissions when the user runs a catalog operation.
    """
    if not isinstance(path, Path):
        raise ValidationError('Catalog location must be an absolute local file path')
    if not path.is_absolute() or path.anchor.startswith(('//', '\\\\')):
        raise ValidationError('Catalog location must be an absolute local file path')
    if path.drive and any(':' in part for part in path.parts[1:]):
        raise ValidationError('Catalog location cannot use an alternate data stream')
    try:
        if any(entry.is_symlink() or getattr(entry, 'is_junction', lambda: False)()
               for entry in (path, *path.parents)):
            raise ValidationError('Catalog location and its parents cannot be redirected')
        if path.resolve(strict=True) != path:
            raise ValidationError('Catalog location must use its canonical path')
        value = path.stat()
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1 or value.st_size <= 0:
            raise ValidationError('Choose an existing nonempty, single-link regular catalog file')
    except (OSError, RuntimeError, ValueError) as error:
        raise ValidationError('Catalog location is unavailable or noncanonical') from error
    return path
