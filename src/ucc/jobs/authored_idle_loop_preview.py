"""Read-only authority for an explicitly selected private authored-idle loop."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import stat

from ucc.animations.target_action_diagnostic_contract import TargetActionDiagnosticSelection
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action import TargetActionBinding, TargetActionSource
from ucc.core.target_action_format import MAX_BYTES, MAX_FILE_BYTES, checked_sha, checked_text, closed, read_document
from .authored_idle_policy import IdleSourcePolicyRecord
from .authored_idle_receipt import _admitted_idle_candidate, _current_idle_mapping
from .godot_saved_preview_catalog import coordination_paths, final_catalog_guard
from .godot_saved_preview_files import ProofReads
from .target_action_context import operation_budget, protected
from .target_action_storage import load_target_action


POLICY = 'UCC_PRIVATE_AUTHORED_IDLE_LOOP_PREVIEW_V1'
_MISSING = (0, 0, 0, 0)
_REPARSE_POINT = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
_CATALOG_SIDE_SUFFIXES = ('-wal', '-shm', '-journal')
_POINTER_FIELDS = {'schema_version', 'policy', 'project_root', 'catalog_path', 'candidate_directory',
                   'receipt_sha256', 'source_policy_records', 'blender_executable', 'worker_script'}


def _catalog_paths(databases):
    return {path: suffix for database in databases
            for path, suffix in zip(coordination_paths(database)[1:], _CATALOG_SIDE_SUFFIXES)}


def _normalized(stamp, coordination):
    if stamp is None or coordination == '-shm' or coordination == '-wal' and stamp[2] == 0:
        return _MISSING
    return stamp


def _filesystem_stamp(path, coordination=None):
    """Stat one entry. Its ancestors are checked separately before it."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _MISSING
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
        raise ProjectStorageError('Authored idle loop authority path was redirected')
    if stat.S_ISDIR(info.st_mode) and coordination is None:
        return info.st_dev, info.st_ino, 0, 0
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProjectStorageError('Authored idle loop authority path is not an exclusively owned file')
    return _normalized((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns), coordination)


def _check_stamps(stamps, databases):
    catalog = _catalog_paths(databases)
    for path, stamp in stamps:
        if _filesystem_stamp(path, catalog.get(path)) != stamp:
            raise ProjectStorageError('Authored idle loop authority changed; repeat private review')


@dataclass(frozen=True, slots=True)
class AuthoredIdleReviewIdentity:
    selection: TargetActionDiagnosticSelection
    proof_sha256: str
    receipt_sha256: str
    mapping_sha256: str
    cache_sha256: str

    def __post_init__(self) -> None:
        if type(self.selection) is not TargetActionDiagnosticSelection:
            raise ValidationError('An authored idle review needs the exact saved target selection')
        for digest in (self.proof_sha256, self.receipt_sha256, self.mapping_sha256, self.cache_sha256):
            checked_sha(digest)

    def to_dict(self) -> dict:
        return {'selection': self.selection.to_dict(), 'proof_sha256': self.proof_sha256,
                'receipt_sha256': self.receipt_sha256, 'mapping_sha256': self.mapping_sha256,
                'cache_sha256': self.cache_sha256}


@dataclass(frozen=True, slots=True)
class AuthoredIdleLoopPreview:
    binding_sha256: str
    cache_sha256: str
    watch_paths: tuple[Path, ...]
    watched_identities: tuple[tuple[Path, tuple[int, int, int, int]], ...] = field(repr=False)
    database_path: Path
    _original_catalog: Path = field(repr=False)
    review_identity: AuthoredIdleReviewIdentity
    _candidate_directory: Path = field(repr=False)
    _protected_output_scopes: tuple[Path, ...] = field(repr=False)
    _target_source: TargetActionSource = field(repr=False)

    def assert_current(self) -> None:
        """Filesystem-only fence for transfer and playback; no cache reads or SQL."""
        try:
            _check_stamps(self.watched_identities, (self.database_path, self._original_catalog))
        except OSError as error:
            raise ProjectStorageError('Authored idle loop authority cannot be checked') from error

    def identities_current(self) -> bool:
        try:
            self.assert_current()
        except ProjectStorageError:
            return False
        return True


class _Authority:
    def __init__(self, budget, databases):
        self._budget = budget
        self._databases = databases
        self._catalog = _catalog_paths(databases)
        self._stamps = {}
        self._paths = set()

    def remember(self, rows):
        for path, stamp in rows.items():
            self._budget.check()
            coordination = self._catalog.get(path)
            current = _normalized(stamp, coordination)
            # Sidecar ownership is checked even when its coordination stamp is ignored.
            if _filesystem_stamp(path, coordination) != current:
                raise ProjectStorageError('Authored idle loop authority changed while authenticating')
            if self._stamps.setdefault(path, current) != current:
                raise ProjectStorageError('Authored idle loop reads disagree on original authority')
            if current != _MISSING and current[2:] != (0, 0):
                self._paths.update((path, path.parent))
            elif path.parent not in self._stamps:
                self._paths.add(path.parent)
        # Imported snapshots include their captured ancestors where available.
        # Check the remaining ancestor identities as well for later cheap transfer.
        for path in rows:
            for parent in path.parents:
                if parent not in self._stamps:
                    self._budget.check()
                    self._stamps[parent] = _filesystem_stamp(parent)

    def assert_current(self):
        self._budget.check()
        _check_stamps(self._stamps.items(), self._databases)
        self._budget.check()

    def freeze(self, review, database, inputs, scopes, target_source):
        stamps = tuple(sorted(self._stamps.items(), key=lambda row: (len(row[0].parts), str(row[0]))))
        paths = tuple(sorted((path for path in self._paths
                              if self._stamps.get(path, _MISSING) != _MISSING), key=str))
        result = AuthoredIdleLoopPreview(review.selection.binding_sha256, review.cache_sha256,
            paths, stamps, database, inputs.database, review, inputs.candidate_directory, scopes, target_source)
        self._budget.check()
        result.assert_current()
        self._budget.check()
        return result


def _path(value):
    path = Path(checked_text(value, 4096))
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ValidationError('Choose an absolute local authored idle proof path')
    return protected(path)


def _pointer(raw):
    value = closed(read_document(raw), _POINTER_FIELDS)
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['policy'] != POLICY:
        raise ValidationError('Unsupported private authored idle loop proof')
    records = value['source_policy_records']
    if type(records) is not list or not 1 <= len(records) <= 3:
        raise ValidationError('Choose the exact authored idle source-policy records')
    return value


def _tool(pointer, reads):
    pointer = closed(pointer, {'path', 'sha256'})
    path = _path(pointer['path'])
    reads.record(path, MAX_FILE_BYTES, checked_sha(pointer['sha256']))
    return path


@dataclass(frozen=True, slots=True)
class _IdleProofInputs:
    project_root: Path
    candidate_directory: Path
    database: Path
    blender: Path
    worker: Path
    proof_sha256: str


@contextmanager
def _source_from_idle_proof(proof_file, database, budget, expected_sha256=None):
    reads = ProofReads(budget)
    raw = reads.capture(_path(str(proof_file)), MAX_BYTES, expected_sha256)
    pointer = _pointer(raw)
    original = _path(pointer['catalog_path'])
    source_store = ProjectStore(_path(pointer['project_root']))
    directory = _path(pointer['candidate_directory'])
    records = tuple(IdleSourcePolicyRecord(row['asset_id'], _path(row['path']), row['sha256'])
                    for row in (closed(item, {'asset_id', 'path', 'sha256'}) for item in pointer['source_policy_records']))
    blender, worker = (_tool(pointer[name], reads) for name in ('blender_executable', 'worker_script'))
    authority = _Authority(budget, (database, original))
    authority.remember(reads.authority)
    with _admitted_idle_candidate(source_store, directory, checked_sha(pointer['receipt_sha256']),
            records, original, blender, worker, budget.cancel, budget.remaining(),
            capture_authority=authority.remember) as (admitted, verifier, source_budget):
        yield admitted, verifier, source_budget, authority, _IdleProofInputs(
            source_store.root, directory, original, blender, worker, sha256(raw).hexdigest())
    authority.assert_current()


def _target(store, selection, database, budget):
    # Fence the existing current loader, including its logical permission
    # checks, with the semantic catalog bytes it actually used.
    loaded = None

    def load():
        nonlocal loaded
        loaded = load_target_action(store, **selection.loader_args(), database_path=database,
                                    cancel=budget.cancel, timeout_s=budget.remaining())

    coordinated = final_catalog_guard(database, budget, load)
    reads = ProofReads(budget)
    stamps = dict(loaded.watched_identities)
    raw = reads.capture(loaded.binding_path, MAX_BYTES, selection.binding_sha256)
    if reads.authority.get(loaded.binding_path) != stamps.get(loaded.binding_path):
        raise ProjectConflict('Authored idle target binding changed after the typed load')
    binding = TargetActionBinding.from_bytes(raw)
    if (binding.sha256 != selection.binding_sha256 or loaded.binding_sha256 != selection.binding_sha256
            or loaded.directory != store.root/'animations/actions'/selection.binding_sha256
            or loaded.binding_path != loaded.directory/'binding.json'
            or stamps.get(database, _MISSING)[:2] != coordinated[database][:2]):
        raise ProjectConflict('Authored idle loop target differs from the exact typed selection')
    stamps.update(coordinated)
    return loaded.cache, binding, stamps


def _match(admitted, mapping, binding, cache):
    recorded, target = admitted.candidate.target, binding.target
    if (recorded.project_id, recorded.master_sha256, recorded.neutral_state_sha256, recorded.rest_sha256) != (
            target.project_id, target.master_sha256, target.neutral_state_sha256, target.rest_sha256):
        raise ProjectConflict('Authored idle and saved target differ in project, neutral master, or rest')
    if ((admitted.candidate.source_sha256, admitted.candidate.snapshot_sha256, mapping.mapping_sha256)
            != (binding.source.source_sha256, binding.source.snapshot_sha256, binding.mapping_sha256)
            or binding.root_motion_policy != 'ARMATURE_ORIGIN_DISPLACEMENT_V1'):
        raise ValidationError('Saved target did not use the exact authored idle source and mapping')
    if ((cache.source_first_frame, cache.frame_count, cache.fps) != (2, 300, 30)
            or cache.surface_review is None):
        raise ValidationError('Authored idle loop requires the complete surface-bound target clock')
    cache_row = binding.file_map['playback/motion_skin.bin']
    if len(cache.packed) != cache_row.bytes or sha256(cache.packed).hexdigest() != cache_row.sha256:
        raise ValidationError('Authored idle loop cache differs from its retained binding')
    return cache_row.sha256


def load_authored_idle_loop_preview(store, *, proof_file: Path, selection: TargetActionDiagnosticSelection,
        database_path: Path, local_preview_confirmed: bool, cancel=None, timeout_s=300) -> AuthoredIdleLoopPreview:
    """Check the original authoring proof and current target for private preview."""
    if type(selection) is not TargetActionDiagnosticSelection or local_preview_confirmed is not True:
        raise ValidationError('Choose an exact saved target and confirm private authored idle loop preview')
    return authenticate_authored_idle_target(store, proof_file=proof_file, selection=selection,
        database_path=database_path, cancel=cancel, timeout_s=timeout_s)


def authenticate_authored_idle_target(store, *, proof_file: Path, selection: TargetActionDiagnosticSelection,
        database_path: Path, expected_proof_sha256: str | None = None,
        cancel=None, timeout_s=300) -> AuthoredIdleLoopPreview:
    """Authenticate original and saved target evidence without authorizing a new use."""
    if type(selection) is not TargetActionDiagnosticSelection:
        raise ValidationError('Choose the exact saved authored idle target')
    if expected_proof_sha256 is not None:
        checked_sha(expected_proof_sha256)
    try:
        with operation_budget(cancel, timeout_s) as budget:
            database = _path(str(database_path))
            with _source_from_idle_proof(proof_file, database, budget, expected_proof_sha256) as (
                    admitted, verifier, source_budget, authority, inputs):
                mapping = _current_idle_mapping(admitted, verifier, source_budget)
                cache, binding, stamps = _target(store, selection, database, source_budget)
                authority.remember(stamps)
                cache_sha = _match(admitted, mapping, binding, cache)
                review = AuthoredIdleReviewIdentity(selection, inputs.proof_sha256, admitted.candidate.receipt_sha256,
                                                    mapping.mapping_sha256, cache_sha)
                dependencies = json.loads(admitted.receipt_json)['worker_dependencies']
                scopes = (inputs.project_root, inputs.candidate_directory, inputs.blender.parent, inputs.worker.parent,
                    *coordination_paths(database), *coordination_paths(inputs.database),
                    *(Path(name).parent for name in dependencies))
            return authority.freeze(review, database, inputs, scopes, binding.source)
    except OSError as error:
        raise ProjectStorageError('Cannot read the private authored idle loop proof') from error
