"""Local inline preview mappings pinned to the source, snapshot, and saved master."""

from hashlib import sha256
from pathlib import Path
from stat import S_ISDIR, S_ISREG

from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError

from .native_source_authority import NativeSourceAuthority
from .target_action_context import protected


def catalog_preview_profile_path(database: Path, source_sha256: str, snapshot_sha256: str,
                                 master_sha256: str) -> Path:
    pins = (source_sha256, snapshot_sha256, master_sha256)
    if not all(is_sha256(pin) for pin in pins):
        raise ValidationError('Local preview body map needs exact source, snapshot, and master hashes')
    key = sha256(''.join(pins).encode('ascii')).hexdigest()
    return database.parent / 'native-preview-maps' / (key + '.json')


def find_catalog_preview_profile(authority: NativeSourceAuthority, master_sha256: str) -> Path | None:
    path = catalog_preview_profile_path(authority.database_path, authority.source_sha256,
                                        authority.snapshot_sha256, master_sha256)
    folder = protected(path.parent)
    try:
        folder_stat = folder.lstat()
    except FileNotFoundError:
        return None
    if not S_ISDIR(folder_stat.st_mode):
        raise ValidationError('Local preview body map folder is not a directory')
    protected(path)
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return None
    if not S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
        raise ValidationError('Local preview body map must be a regular file with one link')
    return path
