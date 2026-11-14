"""Immutable expression provenance and copied masters; never changes a pointer."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from threading import Event

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest, validate_expression_manifest
from ucc.core.expressions import is_sha256
from ucc.core.master_versions import MAX_BLEND_BYTES, _copy_staged
from ucc.core.storage import ProjectStore, _unique_project_fields, _nonfinite_project_number
from .master_preview import _digest, _master_file


def check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Expression preparation cancelled; original project/master remain authoritative')


def safe_directory(store: ProjectStore, *parts: str, create: bool = False) -> Path:
    store._check_safety(); path = store.root
    if path.is_symlink() or path.resolve(strict=False) != store.root:
        raise ProjectStorageError('Expression project root is redirected')
    for part in parts:
        if type(part) is not str or not part or Path(part).name != part or part in ('.', '..'):
            raise ValidationError('Expression directory requires fixed single path components')
        path = path/part
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ProjectStorageError('Expression directory is redirected or invalid')
        if create:
            path.mkdir(exist_ok=True)
        if not path.resolve(strict=False).is_relative_to(store.root):
            raise ProjectStorageError('Expression directory escaped the project')
    return path


def install_master_copy(store: ProjectStore, source: Path, expected: str, authorized_root: Path,
                        cancel: Event | None = None) -> Path:
    """Install verified immutable bytes as provenance; leave project JSON untouched."""
    if not is_sha256(expected):
        raise ValidationError('Expression source publication requires a verified master hash')
    check_cancel(cancel)
    if (authorized_root.is_symlink() or not authorized_root.is_dir() or source.is_symlink()
            or not source.is_file() or not source.resolve(strict=True).is_relative_to(authorized_root.resolve(strict=True))):
        raise ProjectStorageError('Expression master must be inside its explicit verified source directory')
    directory = safe_directory(store, 'master', 'versions', create=True)
    temporary, actual, size = _copy_staged(source, directory, MAX_BLEND_BYTES)
    try:
        if actual != expected or size < 1024:
            raise ProjectStorageError('Verified expression master changed during immutable copying')
        check_cancel(cancel)
        destination = directory/(expected+'.blend')
        if not destination.exists():
            try: os.link(temporary, destination)
            except FileExistsError: pass
        path, _ = _master_file(store, 'master/versions/'+expected+'.blend')
        if _digest(path, cancel) != expected:
            raise ProjectStorageError('Existing expression source version has an unexpected identity')
        return path
    finally:
        temporary.unlink(missing_ok=True)


def _install_bytes(directory: Path, identity: str, data: bytes, cancel: Event | None,
                    *, basename: str | None = None) -> Path:
    from hashlib import sha256
    if not is_sha256(identity) or sha256(data).hexdigest() != identity:
        raise ValidationError('Expression immutable JSON bytes differ from their identity')
    if basename is not None and (type(basename) is not str or not basename.endswith('.json') or not is_sha256(basename[:-5])):
        raise ValidationError('Expression object basename must be one content-addressed JSON component')
    destination = directory/(basename if basename is not None else identity+'.json')
    fd, name = tempfile.mkstemp(prefix='.ucc-expression-', suffix='.tmp', dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        check_cancel(cancel)
        if not destination.exists():
            try: os.link(temporary, destination)
            except FileExistsError: pass
        if destination.is_symlink() or not destination.is_file() or _digest(destination, cancel) != identity:
            raise ProjectStorageError('Existing expression JSON object differs from its immutable identity')
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def publish_library(store: ProjectStore, manifest: dict, report: Path,
                    cancel: Event | None = None) -> str:
    checked = validate_expression_manifest(manifest)
    if (report.is_symlink() or not report.is_file() or report.stat().st_size > 4*1024*1024
            or _digest(report, cancel) != checked['report_sha256']):
        raise ProjectStorageError('Verified expression preparation report is missing or changed')
    _install_bytes(safe_directory(store, 'expressions', 'reports', create=True),
                   checked['report_sha256'], report.read_bytes(), cancel)
    data = json.dumps(checked, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    identity = canonical_digest(checked)
    _install_bytes(safe_directory(store, 'expressions', 'manifests', create=True), identity, data, cancel)
    return identity


def _read_json(path: Path, expected: str, limit: int, cancel: Event | None) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit or _digest(path, cancel) != expected:
        raise ProjectStorageError('Registered expression provenance is missing, redirected or changed')
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_project_fields,
                          parse_constant=_nonfinite_project_number)
    except (ValueError, RecursionError) as error:
        raise ValidationError('Invalid expression provenance JSON') from error


@dataclass(frozen=True, slots=True)
class ExpressionLibrary:
    manifest: dict
    sha256: str
    manifest_path: Path
    original_master: Path
    prepared_master: Path
    report_path: Path


def load_expression_library(store: ProjectStore, identity: str,
                            cancel: Event | None = None) -> ExpressionLibrary:
    if not is_sha256(identity):
        raise ValidationError('Select an immutable expression-library identity')
    path = safe_directory(store, 'expressions', 'manifests')/(identity+'.json')
    manifest = validate_expression_manifest(_read_json(path, identity, 128*1024, cancel))
    if canonical_digest(manifest) != identity:
        raise ValidationError('Expression manifest must retain its canonical identity')
    if manifest['source']['project_id'] != store.load().project_id:
        raise ValidationError('Expression library belongs to another character project')
    masters = []
    for sha in (manifest['recipe']['bindings']['master_sha256'], manifest['prepared_master_sha256']):
        master, _ = _master_file(store, 'master/versions/'+sha+'.blend')
        if _digest(master, cancel) != sha:
            raise ProjectStorageError('Expression original or prepared provenance master changed')
        masters.append(master)
    report_path = safe_directory(store, 'expressions', 'reports')/(manifest['report_sha256']+'.json')
    report = _read_json(report_path, manifest['report_sha256'], 4*1024*1024, cancel)
    if (type(report) is not dict or report.get('source_master_sha256') != manifest['recipe']['bindings']['master_sha256']
            or report.get('prepared_sha256') != manifest['prepared_master_sha256']
            or report.get('policy') != manifest['policy']
            or canonical_digest(report.get('observation')) != manifest['observation_sha256']
            or report.get('visual_quality_approved') is not False or report.get('engine_import_verified') is not False):
        raise ValidationError('Expression report differs from registered source/template provenance')
    check_cancel(cancel)
    return ExpressionLibrary(manifest, identity, path, *masters, report_path)
