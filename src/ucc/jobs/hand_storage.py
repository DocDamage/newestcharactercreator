"""Project-local immutable hand assets; no downloads or permission expansion."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from threading import Event

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.facial import FACE_BASE_SHA256, FACE_RIG_SHA256
from ucc.core.hand_parts import (
    TARGETS, METADATA_SHA256, canonical_digest, is_sha256, validate_hand_manifest, validate_hand_receipt,
)
from ucc.core.master_versions import _copy_staged
from ucc.core.storage import ProjectStore, _unique_project_fields, _nonfinite_project_number
from .master_preview import _digest, _master_file

MAX_HAND_ASSET_BYTES = 128*1024*1024


@dataclass(frozen=True, slots=True)
class HandLibrary:
    manifest: dict
    sha256: str
    manifest_path: Path
    source_master: Path
    assets: dict[str, Path]


def check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Hand operation cancelled; original project/master remain authoritative')


def installed_inputs(data_dir: Path, cancel: Event | None = None) -> dict[str, Path]:
    root = Path(data_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValidationError('Select the existing installed MPFB data directory')
    resolved = root.resolve(strict=True)
    entries = {'base.obj': (root/'3dobjs/base.obj', FACE_BASE_SHA256),
               'rig.default.json': (root/'rigs/standard/rig.default.json', FACE_RIG_SHA256),
               'basemesh_vertex_groups.json': (root/'mesh_metadata/basemesh_vertex_groups.json', METADATA_SHA256),
               **{t.filename: (root/'targets/hands'/t.filename, t.sha256) for t in TARGETS}}
    for name, (path, expected) in entries.items():
        check_cancel(cancel)
        if (path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(resolved)
                or _digest(path, cancel) != expected):
            raise ValidationError('Installed MPFB hand data is missing, redirected or changed: '+name)
    return {name: path for name, (path, _) in entries.items()}


def safe_directory(store: ProjectStore, *parts: str, create: bool = False) -> Path:
    store._check_safety()
    path = store.root
    for part in parts:
        path = path/part
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ProjectStorageError('Hand directory is redirected or invalid')
        if create and not path.exists():
            path.mkdir(exist_ok=False)
        if not path.resolve(strict=False).is_relative_to(store.root):
            raise ProjectStorageError('Hand directory escaped the project')
    return path


def _bound_asset(path: Path, expected: str, root: Path, cancel: Event | None) -> Path:
    if (path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root)
            or not 1024 <= path.stat().st_size <= MAX_HAND_ASSET_BYTES or _digest(path, cancel) != expected):
        raise ProjectStorageError('Registered hand asset is missing, redirected, oversized or changed')
    with path.open('rb') as stream:
        if stream.read(7) != b'BLENDER':
            raise ProjectStorageError('Registered hand asset is not an uncompressed Blender library')
    return path


def publish_asset(store: ProjectStore, source: Path, expected: str, authorized_root: Path,
                  cancel: Event | None = None) -> Path:
    if not is_sha256(expected):
        raise ValidationError('Hand publication requires a verified asset digest')
    check_cancel(cancel)
    allowed = authorized_root.resolve(strict=True)
    _bound_asset(source, expected, allowed, cancel)
    directory = safe_directory(store, 'parts', 'objects', create=True)
    temporary, actual, _ = _copy_staged(source, directory, MAX_HAND_ASSET_BYTES)
    try:
        if actual != expected:
            raise ProjectStorageError('Verified hand changed during registration')
        check_cancel(cancel)
        destination = directory/(expected+'.blend')
        if not destination.exists():
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        return _bound_asset(destination, expected, store.root, cancel)
    finally:
        temporary.unlink(missing_ok=True)


def publish_manifest(store: ProjectStore, manifest: dict, cancel: Event | None = None) -> str:
    checked = validate_hand_manifest(manifest); identity = canonical_digest(checked)
    directory = safe_directory(store, 'parts', 'manifests', create=True)
    destination = directory/(identity+'.json')
    data = json.dumps(checked, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    fd, name = tempfile.mkstemp(prefix='.ucc-hand-', suffix='.tmp', dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        check_cancel(cancel)
        if not destination.exists():
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        if destination.is_symlink() or not destination.is_file() or _digest(destination, cancel) != identity:
            raise ProjectStorageError('Existing hand manifest has an unexpected identity')
    finally:
        temporary.unlink(missing_ok=True)
    return identity


def read_hand_manifest(store: ProjectStore, identity: str, cancel: Event | None = None) -> tuple[dict,Path]:
    if not is_sha256(identity):
        raise ValidationError('Select a content-addressed project hand library')
    directory = safe_directory(store, 'parts', 'manifests')
    path = directory/(identity+'.json')
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > 64*1024
            or not path.resolve(strict=True).is_relative_to(store.root) or _digest(path, cancel) != identity):
        raise ProjectStorageError('Hand manifest is missing, redirected, oversized or changed')
    try:
        raw = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_project_fields,
                         parse_constant=_nonfinite_project_number)
    except (ValueError, RecursionError) as error:
        raise ValidationError('Hand manifest contains invalid JSON') from error
    manifest = validate_hand_manifest(raw)
    if canonical_digest(manifest) != identity:
        raise ValidationError('Hand manifest must retain its exact canonical content identity')
    return manifest,path


def load_hand_library(store: ProjectStore, identity: str, cancel: Event | None = None) -> HandLibrary:
    manifest,path=read_hand_manifest(store,identity,cancel)
    source_sha = manifest['recipe']['bindings']['master_sha256']
    source, _ = _master_file(store, 'master/versions/'+source_sha+'.blend')
    if _digest(source, cancel) != source_sha:
        raise ProjectStorageError('Original hand-library source master changed')
    objects = safe_directory(store, 'parts', 'objects')
    assets = {variant: _bound_asset(objects/(row['sha256']+'.blend'), row['sha256'], store.root, cancel)
              for variant, row in manifest['assets'].items()}
    check_cancel(cancel)
    return HandLibrary(manifest, identity, path, source, assets)


def publish_hand_receipt(store: ProjectStore, receipt: dict, cancel: Event | None = None) -> Path:
    checked=validate_hand_receipt(receipt)
    directory=safe_directory(store,'parts','revisions',create=True)
    path=directory/(checked['master_sha256']+'.json'); identity=canonical_digest(checked)
    fd,name=tempfile.mkstemp(prefix='.ucc-hand-revision-',suffix='.tmp',dir=directory)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(json.dumps(checked,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
            stream.flush();os.fsync(stream.fileno())
        check_cancel(cancel)
        if not path.exists():
            try:os.link(temporary,path)
            except FileExistsError:pass
        if path.is_symlink() or not path.is_file() or _digest(path,cancel) != identity:
            raise ProjectStorageError('Existing hand revision receipt has different bindings')
        return path
    finally:
        temporary.unlink(missing_ok=True)


def load_hand_receipt(store: ProjectStore, library: HandLibrary, master_sha256: str,
                      selection: str, cancel: Event | None = None) -> dict:
    if not is_sha256(master_sha256):
        raise ValidationError('Hand revision requires an immutable current master')
    directory=safe_directory(store,'parts','revisions');path=directory/(master_sha256+'.json')
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > 64*1024
            or not path.resolve(strict=True).is_relative_to(store.root)):
        raise ProjectStorageError('Current hand master has no registered revision receipt; external adoption is unsupported')
    try:
        raw=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_unique_project_fields,
                       parse_constant=_nonfinite_project_number)
    except (ValueError,RecursionError) as error:
        raise ValidationError('Invalid hand revision receipt JSON') from error
    checked=validate_hand_receipt(raw)
    if (checked['master_sha256'] != master_sha256 or checked['manifest_sha256'] != library.sha256
            or checked['selection'] != selection
            or checked['original_master_sha256'] != library.manifest['recipe']['bindings']['master_sha256']
            or _digest(path,cancel) != canonical_digest(checked)):
        raise ProjectStorageError('Current hand revision does not match its registered library/selection')
    check_cancel(cancel)
    return checked
