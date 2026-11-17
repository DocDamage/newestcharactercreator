"""Frozen catalog authority and pre-read proof receipts for private native preview."""
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from ucc.animations.catalog_clip import text
from ucc.animations.fbx_snapshot import MAX_SOURCE_BYTES
from ucc.animations.source_clip_clock import SourceClipClock
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ProjectStorageError, UCCError, ValidationError
from ucc.library.provenance import AssetPolicyError, LicensePolicy
from .catalog_clip import _saved_reference
from .godot_saved_preview_catalog import coordination_paths, final_catalog_guard
from .source_skeleton_files import capture, watch_identity
from .target_action_context import operation_budget, protected

MAX_PROOF_BYTES = 512*1024*1024
CONTEXT_POLICY = 'REGISTERED_NATIVE_SOURCE_CONTEXT_V1'


def _normalized(path, value, database=None):
    if database is not None:
        if path == Path(str(database)+'-wal') and value[2] == 0:
            return (0, 0, 0, 0)  # Only absent/empty, already ownership checked.
        if path == Path(str(database)+'-shm') and value != (0, 0, 0, 0):
            return value[:3]+(0,)  # Read marks are not policy authority.
    return value


def _identity(path, database=None):
    if database is not None and path in coordination_paths(database):
        protected(path)
        if path.exists() and not path.is_file():
            raise ProjectStorageError('Native catalog coordination path is not a regular file')
    return _normalized(path, watch_identity(path), database)


def _check(identities, budget=None, database=None):
    for path, expected in identities.items():
        if budget is not None:
            budget.check()
        if _identity(path, database) != expected:
            raise ProjectStorageError('Registered native input identity changed: '+str(path))


def _current(identities, database=None):
    try:
        _check(identities, database=database)
        return True
    except (UCCError, OSError, ValueError):
        return False


def _parents(paths):
    return {parent for path in paths for parent in path.parents}


def _watches(files, identities):
    wanted = set(files) | {path.parent for path in files}
    return tuple(sorted((p for p in wanted if identities[p] != (0, 0, 0, 0)), key=str))


@dataclass(frozen=True, slots=True)
class NativeSourceAuthority:
    database_path: Path
    clip_id: str
    source_path: Path
    source_sha256: str
    policy: LicensePolicy
    snapshot_sha256: str
    receipt_sha256: str
    clock: SourceClipClock
    watch_paths: tuple[Path, ...]
    watched_identities: Mapping[Path, tuple[int, int, int, int]] = field(repr=False)
    guard: Callable = field(repr=False, compare=False)

    def identities_current(self) -> bool:
        """Cheap GUI-safe namespace checks; no SQL or content hashing."""
        return _current(self.watched_identities, self.database_path)

    def require_source(self, source, permission) -> None:
        if (protected(Path(source)) != self.source_path or permission != self.policy):
            raise AssetPolicyError('Registered native source or exact catalog policy differs')

    def require_snapshot(self, data, snapshot_sha256) -> None:
        if (type(data) is not dict or data.get('source_sha256') != self.source_sha256
                or snapshot_sha256 != self.snapshot_sha256 or type(data.get('frames')) is not list
                or SourceClipClock(data.get('first_frame'), data.get('last_frame'),
                                   len(data['frames']), data.get('fps')) != self.clock):
            raise ValidationError('Fresh native snapshot or clock differs from its catalog authority')


def bind_native_catalog_source(database_path: Path, clip_id: str, *,
        expected_source_sha256: str, expected_policy: LicensePolicy,
        local_preview_confirmed: bool, cancel=None, timeout_s=300) -> NativeSourceAuthority:
    """Bind selected stored identity; fresh native measurement remains separate."""
    if (local_preview_confirmed is not True or not text(clip_id, 138)
            or not is_sha256(expected_source_sha256) or not isinstance(expected_policy, LicensePolicy)):
        raise ValidationError('Registered native preview requires exact source selection and local consent')
    allowed, reason = expected_policy.allow('local_preview')
    if not allowed:
        raise AssetPolicyError(reason)
    database = protected(Path(database_path))
    with operation_budget(cancel, timeout_s) as budget:
        original = _saved_reference(database, clip_id, expected_source_sha256, expected_policy)
        entry, indexed, receipt, receipt_sha = original
        source = protected(Path(entry.source_path))
        _, source_identity = capture(source, MAX_SOURCE_BYTES, budget, expected=entry.sha256)
        if source_identity[2] != entry.size_bytes:
            raise ProjectStorageError('Registered source size differs from its catalog')
        observed = receipt['observation']
        clock = SourceClipClock(observed['first_frame'], observed['last_frame'],
                                observed['frame_count'], observed['fps'])
        files = {source, *coordination_paths(database)}
        identities = {p: _identity(p, database) for p in _parents(files)}
        identities[source] = source_identity

        def logical():
            budget.check()
            if _saved_reference(database, clip_id, entry.sha256, expected_policy) != original:
                raise AssetPolicyError('Registered native catalog source, receipt or policy changed')

        # Heavy source work precedes the final fenced logical permission check.
        _check(identities, budget, database)
        fenced = final_catalog_guard(database, budget, logical)
        identities.update({p: _normalized(p, value, database) for p, value in fenced.items()})
        _check(identities, budget, database)
        frozen = MappingProxyType(dict(identities))
        budget.check()

    def guard(*, cancel=None, timeout_s=300):
        with operation_budget(cancel, timeout_s) as fresh:
            _check(frozen, fresh, database)
            capture(source, MAX_SOURCE_BYTES, fresh, expected=entry.sha256)

            def current_logical():
                fresh.check()
                if _saved_reference(database, clip_id, entry.sha256, expected_policy) != original:
                    raise AssetPolicyError('Registered native source policy or receipt changed')

            final_catalog_guard(database, fresh, current_logical)
            _check(frozen, fresh, database)
        return True

    return NativeSourceAuthority(database, clip_id, source, entry.sha256, expected_policy,
        receipt['snapshot_sha256'], receipt_sha, clock, _watches(files, frozen), frozen, guard)


@dataclass(frozen=True, slots=True)
class NativeProofReceipt:
    watch_paths: tuple[Path, ...]
    watched_identities: Mapping[Path, tuple[int, int, int, int]] = field(repr=False)
    guard: Callable = field(repr=False, compare=False)
    file_hashes: Mapping[Path, str] = field(default_factory=lambda: MappingProxyType({}), repr=False)

    def identities_current(self) -> bool:
        return _current(self.watched_identities)


class NativeProofCapture:
    """Backend-only collector: record identity BEFORE parsing/validation reads."""
    def __init__(self, budget, previous=None):
        self.budget = budget
        if previous is not None and type(previous) is not NativeProofReceipt:
            raise ValidationError('Registered native proof receipt type differs')
        self.identities = dict(previous.watched_identities) if previous is not None else {}
        self.hashes = dict(previous.file_hashes) if previous is not None else {}
        self.check()

    def before(self, path):
        self.budget.check()
        path = protected(Path(path))
        value = watch_identity(path)
        if value == (0, 0, 0, 0) or not path.is_file() or value[2] > MAX_PROOF_BYTES:
            raise ProjectStorageError('Native proof is missing or exceeds its bound')
        for parent in path.parents:
            stamp = watch_identity(parent)
            if self.identities.setdefault(parent, stamp) != stamp:
                raise ProjectStorageError('Native proof parent changed')
        if self.identities.setdefault(path, value) != value:
            raise ProjectStorageError('Native proof replaced before validation')
        return path

    def admit(self, path, expected_sha256):
        path = protected(Path(path))
        if path not in self.identities:
            raise ProjectStorageError('Native proof was not captured before validation')
        capture(path, MAX_PROOF_BYTES, self.budget, expected=expected_sha256)
        _check(self.identities, self.budget)
        if self.hashes.setdefault(path, expected_sha256) != expected_sha256:
            raise ProjectStorageError('Native proof hash binding changed')

    def check(self):
        _check(self.identities, self.budget)
        for path, expected in self.hashes.items():
            capture(path, MAX_PROOF_BYTES, self.budget, expected=expected)

    def seal(self) -> NativeProofReceipt:
        self.check()
        files = dict(self.hashes)
        if any(path.is_file() and path not in files for path in self.identities):
            raise ProjectStorageError('Native proof validation did not complete')
        frozen = MappingProxyType(dict(self.identities))

        def guard(*, cancel=None, timeout_s=300):
            with operation_budget(cancel, timeout_s) as budget:
                _check(frozen, budget)
                for path, expected in files.items():
                    capture(path, MAX_PROOF_BYTES, budget, expected=expected)
                _check(frozen, budget)
            return True

        return NativeProofReceipt(_watches(files, frozen), frozen, guard, MappingProxyType(files))
