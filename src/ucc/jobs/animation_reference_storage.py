"""Immutable project source bindings; no motion data and no master promotion."""
from hashlib import sha256
import json
from pathlib import Path
from threading import Event

from ucc.animations.catalog_clip import VerifiedCatalogClip
from ucc.animations.project_references import MAX_REFERENCE_BYTES, build_source_binding, validate_source_binding
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.storage import ProjectStore, _unique_project_fields, _nonfinite_project_number
from ucc.library.provenance import LicensePolicy
from .catalog_clip import _saved_reference
from .expression_storage import check_cancel, safe_directory, _install_bytes
from .master_preview import _digest


def _binding_path(store: ProjectStore, clip_id: str, *, create=False) -> Path:
    if type(clip_id) is not str or not clip_id or len(clip_id) > 138:
        raise ValidationError('Select a bounded catalog clip identifier')
    key = sha256(clip_id.encode('utf-8')).hexdigest()
    return safe_directory(store, 'animations', 'references', create=create)/(key+'.json')


def load_source_binding(store: ProjectStore, project_id: str, clip_id: str,
                         cancel: Event | None = None) -> dict:
    check_cancel(cancel); path = _binding_path(store, clip_id)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_REFERENCE_BYTES:
        raise ProjectStorageError('Registered animation source binding is missing, redirected or oversized')
    with path.open('rb') as stream:
        payload = stream.read(MAX_REFERENCE_BYTES+1)
    if len(payload) > MAX_REFERENCE_BYTES:
        raise ProjectStorageError('Registered animation source binding grew while reading')
    try:
        raw = json.loads(payload, object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
        record = validate_source_binding(raw, project_id, clip_id)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, ValidationError) as error:
        raise ProjectStorageError('Registered animation source binding is malformed or belongs to another project') from error
    if sha256(payload).hexdigest() != canonical_digest(record):
        raise ProjectStorageError('Registered animation source binding differs from its immutable encoding')
    check_cancel(cancel)
    return record


def publish_source_binding(store: ProjectStore, project_id: str, reference: VerifiedCatalogClip,
                            cancel: Event | None = None) -> dict:
    record = build_source_binding(project_id, reference)
    path = _binding_path(store, reference.clip_id, create=True)
    data = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(data) > MAX_REFERENCE_BYTES: raise ValidationError('Project source binding exceeds its metadata budget')
    _install_bytes(path.parent, canonical_digest(record), data, cancel, basename=path.name)
    if load_source_binding(store, project_id, reference.clip_id, cancel) != record:
        raise ProjectStorageError('Published animation source binding differs')
    return record


def check_registered_source(store: ProjectStore, database: Path, project_id: str, clip_id: str,
                             cancel: Event | None = None) -> dict:
    """Recheck immutable source identity; applying motion still needs fresh intake."""
    record = load_source_binding(store, project_id, clip_id, cancel)
    policy = LicensePolicy.from_dict(record['license'])
    entry, indexed, receipt, receipt_sha = _saved_reference(database, clip_id, record['source_sha256'], policy)
    cached = VerifiedCatalogClip(clip_id, entry.asset_id, entry.sha256, entry.policy,
        receipt['snapshot_sha256'], receipt_sha, receipt['skeleton_fingerprint'],
        receipt['observation']['first_frame'], receipt['observation']['last_frame'], indexed.clips[0])
    expected = build_source_binding(project_id, cached)
    if canonical_digest(record) != canonical_digest(expected):
        raise ProjectStorageError('Project animation binding differs from the exact registered catalog source')
    source = Path(entry.source_path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size != entry.size_bytes or _digest(source, cancel) != entry.sha256:
        raise ProjectStorageError('Registered animation source is missing, redirected or changed')
    check_cancel(cancel)
    return record
