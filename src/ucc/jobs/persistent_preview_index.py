"""Local authenticated index for already verified private animation previews."""

from collections.abc import Iterator
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
from tempfile import mkstemp
import time

from ucc.core.errors import ProjectStorageError, UCCError, ValidationError
from .export_destination import rename_new
from .target_action_context import protected


_MAX_PAYLOAD = 2 * 1024**2
_MAX_ENVELOPE = _MAX_PAYLOAD + 256
_SECRET_BYTES = 32
_SECRET_NAME = 'signing.key'
_DOMAIN = b'UCC_PERSISTENT_PREVIEW_INDEX_V1\x00'
_FIELDS = {'schema_version', 'key', 'payload', 'tag'}


def _key(value) -> bool:
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _require_key(value: str) -> None:
    if not _key(value):
        raise ValidationError('Persistent preview index key must be a SHA-256 digest')


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False,
                      ensure_ascii=False).encode('utf-8')


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _stamp(info: os.stat_result) -> tuple[int, int, int, int]:
    return (*_identity(info), info.st_size, info.st_mtime_ns)


def _namespace(root: Path, *, create: bool = False) -> tuple[tuple[int, int], ...]:
    protected(root)
    result = []
    for directory in (*reversed(root.parents), root):
        try:
            info = directory.lstat()
        except FileNotFoundError:
            if not create:
                raise
            directory.mkdir(mode=0o700, exist_ok=True)
            info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or _reparse(info):
            raise ProjectStorageError('Persistent preview index directory is redirected or unavailable')
        result.append(_identity(info))
    return tuple(result)


def _require_namespace(root: Path, expected: tuple[tuple[int, int], ...]) -> None:
    if _namespace(root) != expected:
        raise ProjectStorageError('Persistent preview index directory changed')


def _regular(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not _reparse(info)


def _file_info(path: Path) -> os.stat_result:
    info = protected(path).lstat()
    if not _regular(info):
        raise ProjectStorageError('Persistent preview index file is redirected, shared or irregular')
    return info


def _read_bytes(path: Path, maximum: int) -> bytes:
    before = _file_info(path)
    if not 0 < before.st_size <= maximum:
        raise ProjectStorageError('Persistent preview index file exceeds its size bound')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if not _regular(opened) or _stamp(opened) != _stamp(before):
            raise ProjectStorageError('Persistent preview index file changed before reading')
        result = stream.read(maximum + 1)
        closing = os.fstat(stream.fileno())
    if (not _regular(closing) or _stamp(closing) != _stamp(before)
            or len(result) != before.st_size or _stamp(_file_info(path)) != _stamp(before)):
        raise ProjectStorageError('Persistent preview index file changed while reading')
    return result


@contextmanager
def _temporary(root: Path, namespace: tuple[tuple[int, int], ...], data: bytes) -> Iterator[Path]:
    _require_namespace(root, namespace)
    descriptor, name = mkstemp(prefix='.preview-index-', suffix='.tmp', dir=root)
    path = Path(name)
    owner = None
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            owner = _identity(os.fstat(stream.fileno()))
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _require_namespace(root, namespace)
        if _identity(_file_info(path)) != owner or _read_bytes(path, len(data)) != data:
            raise ProjectStorageError('Persistent preview index temporary file changed')
        yield path
    finally:
        # Only our original temporary name, identity, and bytes can be removed.
        try:
            _require_namespace(root, namespace)
            info = _file_info(path)
            if _identity(info) == owner and info.st_size <= len(data):
                if not info.st_size or data.startswith(_read_bytes(path, len(data))):
                    if _identity(_file_info(path)) == owner:
                        path.unlink()
        except (UCCError, OSError):
            pass


def _secret(root: Path, namespace: tuple[tuple[int, int], ...], *, create: bool) -> bytes:
    path = root / _SECRET_NAME
    try:
        result = _read_bytes(path, _SECRET_BYTES)
    except FileNotFoundError:
        if not create:
            raise
        with _temporary(root, namespace, secrets.token_bytes(_SECRET_BYTES)) as staged:
            try:
                rename_new(staged, protected(path))
            except FileExistsError:
                pass  # Another complete key was published first.
        result = _read_bytes(path, _SECRET_BYTES)
    _require_namespace(root, namespace)
    if len(result) != _SECRET_BYTES:
        raise ProjectStorageError('Persistent preview index key size differs')
    return result


def _signed(secret: bytes, key: str, payload: dict) -> dict:
    envelope = {'schema_version': 1, 'key': key, 'payload': payload}
    tag = hmac.digest(secret, _DOMAIN + _canonical(envelope), 'sha256').hex()
    return {**envelope, 'tag': tag}


def read_index(root: Path, key: str) -> dict | None:
    """Return an authenticated record without creating any files."""
    _require_key(key)
    root = Path(root)
    try:
        namespace = _namespace(root)
        secret = _secret(root, namespace, create=False)
        raw = _read_bytes(root / (key + '.json'), _MAX_ENVELOPE)
        record = json.loads(raw.decode('utf-8'))
        if (type(record) is not dict or set(record) != _FIELDS
                or type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['key'] != key or not _key(record['tag']) or type(record['payload']) is not dict
                or len(_canonical(record['payload'])) > _MAX_PAYLOAD
                or raw != _canonical(record)):
            return None
        expected = _signed(secret, key, record['payload'])
        if not hmac.compare_digest(record['tag'], expected['tag']):
            return None
        if secret != _secret(root, namespace, create=False):
            return None
        return record['payload']
    except (UCCError, OSError, ValueError, RecursionError):
        return None


def write_index(root: Path, key: str, payload: dict) -> None:
    """Atomically store a record admitted by the caller after native verification."""
    _require_key(key)
    if type(payload) is not dict:
        raise ValidationError('Persistent preview index payload must be a JSON object')
    try:
        data = _canonical(payload)
        if len(data) > _MAX_PAYLOAD:
            raise ValidationError('Persistent preview index payload exceeds its size bound')
        copy = json.loads(data)
        if copy != payload:
            raise ValidationError('Persistent preview index payload must contain JSON values')
    except (TypeError, ValueError, RecursionError) as error:
        raise ValidationError('Persistent preview index payload must contain JSON values') from error
    root = Path(root)
    namespace = _namespace(root, create=True)
    secret = _secret(root, namespace, create=True)
    target = root / (key + '.json')
    with _temporary(root, namespace, _canonical(_signed(secret, key, copy))) as staged:
        for attempt in range(10):
            if secret != _secret(root, namespace, create=False):
                raise ProjectStorageError('Persistent preview index signing key changed')
            try:
                _file_info(target)
            except FileNotFoundError:
                pass
            try:
                os.replace(staged, target)
            except PermissionError:
                # Windows readers can briefly prevent replacing an open entry.
                if os.name != 'nt' or attempt == 9:
                    raise
                time.sleep(.01)
                continue
            _require_namespace(root, namespace)
            return
