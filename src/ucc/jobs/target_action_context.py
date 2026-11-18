"""Read-only registered source context and a single inherited operation budget."""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from threading import Event
import time
import sqlite3

from ucc.animations.catalog import IndexedAnimation
from ucc.animations.catalog_clip import VerifiedCatalogClip, checked_receipt
from ucc.animations.metadata import ClipMetadata
from ucc.animations.project_references import build_source_binding
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action import TargetActionSource
from ucc.core.target_action_format import document_sha256
from ucc.library.provenance import LicensePolicy, AssetPolicyError, AssetEntry
from .animation_reference_storage import load_source_binding, _binding_path
from .godot_candidate_inputs import identity
from .master_preview import _digest, _master_file
from .skin_material_preparation import _BudgetCancel
from .export_guards import cancel_context, failure_reason


_MIN_TIMEOUT_S = .05
_MAX_TIMEOUT_S = 3600


class Budget:
    def __init__(self, cancel, timeout_s):
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not _MIN_TIMEOUT_S <= timeout_s <= _MAX_TIMEOUT_S):
            raise ValidationError('Target preview requires a bounded total deadline')
        self.user = cancel
        self.deadline, _ = cancel_context(cancel, time.monotonic() + timeout_s)
        self.cancel = _BudgetCancel(cancel, self.deadline)

    def reason(self):
        return failure_reason(self.user, self.deadline)[0]

    def check(self):
        reason = self.reason()
        if reason:
            raise ProjectStorageError('Target preview '+('cancelled by caller' if reason == 'user_cancel'
                else 'total deadline exceeded')+'; original project preserved')

    def remaining(self):
        self.check()
        # Subtracting a rounded absolute deadline can exceed the cap on the same clock tick.
        return min(_MAX_TIMEOUT_S, max(_MIN_TIMEOUT_S, self.deadline - time.monotonic()))


@contextmanager
def operation_budget(cancel, timeout_s):
    budget = Budget(cancel, timeout_s)
    try:
        budget.check()
        yield budget
    except BaseException as error:
        if budget.reason() is None:
            raise
        try:
            budget.check()
        except ProjectStorageError as normalized:
            for note in getattr(error, '__notes__', ()):
                normalized.add_note(note)
            normalized.add_note('Underlying failure: '+type(error).__name__+': '+str(error)[:1500])
            raise normalized from error


def protected(path):
    path = Path(path)
    if (path.resolve() != path or path.is_symlink() or getattr(path, 'is_junction', lambda:False)()
            or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)() for p in path.parents)):
        raise ProjectStorageError('Target preview input is redirected or noncanonical')
    return path


def _catalog_rows(database_path, asset_id, clip_id):
    """Hash the four selected logical rows, including committed WAL content."""
    database_path = protected(Path(database_path))
    for attempt in range(2):
        try:
            return _catalog_rows_once(database_path, asset_id, clip_id)
        except sqlite3.Error as error:
            code = getattr(error, 'sqlite_errorcode', None)
            transient = (isinstance(error, sqlite3.OperationalError) and type(code) is int
                         and (code & 0xff) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_INTERRUPT))
            if attempt or not transient:
                raise ProjectStorageError(
                    'Registered catalog is busy, unreadable or exceeds the bounded metadata query; retry preview'
                ) from error
            # Retry a whole read-only snapshot, never individual rows from a
            # transaction that may have been interrupted halfway through.
            database_path = protected(database_path)


def _catalog_rows_once(database_path, asset_id, clip_id):
    stop = time.monotonic()+.1
    db = None
    try:
        db = sqlite3.connect(database_path.as_uri()+'?mode=ro', uri=True, timeout=.02)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2*1024*1024)
        db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 32)
        db.set_progress_handler(lambda:int(time.monotonic() >= stop), 100)
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        rows = {}
        for table, column, key in (
            ('asset_sources', 'asset_id', asset_id), ('animation_sources', 'asset_id', asset_id),
            ('animation_clips', 'clip_id', clip_id), ('animation_fbx_intakes', 'asset_id', asset_id)):
            if db.execute('SELECT type FROM sqlite_master WHERE name=?', (table,)).fetchone() != ('table',):
                raise ValidationError('Registered catalog table is missing or not a table')
            columns = [r[1] for r in db.execute('PRAGMA table_info('+table+')')]
            expected = {
                'asset_sources':['asset_id','source_path','content_sha256','size_bytes','license_json','indexed_utc'],
                'animation_sources':['asset_id','format','status','fingerprint','bone_names_json','warnings_json'],
                'animation_clips':['clip_id','asset_id','ordinal','metadata_json'],
                'animation_fbx_intakes':['asset_id','receipt_json']}[table]
            if columns != expected:
                raise ValidationError('Registered catalog schema differs from its fixed row contract')
            sizes = ','.join("CASE WHEN typeof("+c+")='text' THEN length(CAST("+c+
                " AS BLOB)) WHEN typeof("+c+") IN ('integer','real','null') THEN 0 ELSE 2097153 END" for c in columns)
            lengths = db.execute('SELECT '+sizes+' FROM '+table+' WHERE '+column+'=?', (key,)).fetchmany(2)
            if len(lengths) != 1 or sum(lengths[0]) > 2*1024*1024:
                raise ValidationError('Registered catalog row is missing or oversized')
            values = db.execute('SELECT * FROM '+table+' WHERE '+column+'=?', (key,)).fetchmany(2)
            if len(values) != 1:
                raise ValidationError('Registered catalog identity is not unique')
            row = values[0]
            rows[table] = row
        token = sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return token, rows
    finally:
        if db is not None: db.close()


def catalog_record(database_path, asset_id, clip_id):
    return _catalog_rows(database_path, asset_id, clip_id)[0]


def _reference_rows(rows, clip_id, expected_source, policy):
    """Materialize the bounded SQL snapshot using the existing receipt validator."""
    from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
    def parse(raw):
        return json.loads(raw, object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
    try:
        asset = rows['asset_sources']; source = rows['animation_sources']; clip = rows['animation_clips']
        entry = AssetEntry(asset[0], asset[1], asset[2], asset[3], LicensePolicy.from_dict(parse(asset[4])), asset[5])
        if (clip[0] != clip_id or clip[1] != entry.asset_id or type(clip[2]) is not int or clip[2] != 0
                or entry.sha256 != expected_source or entry.policy != policy
                or type(entry.source_path) is not str or not 0 < len(entry.source_path.encode()) <= 128*1024):
            raise ValidationError('Registered catalog source/clip/policy differs from its immutable binding')
        raw = parse(clip[3])
        metadata = ClipMetadata(**(raw|{'animated_bones':tuple(raw['animated_bones']), 'warnings':tuple(raw['warnings'])}))
        indexed = IndexedAnimation(entry.asset_id, entry.sha256, source[1], source[2], source[3],
            tuple(parse(source[4])), (metadata,), tuple(parse(source[5])), {})
        receipt_raw = rows['animation_fbx_intakes'][1]
        receipt = checked_receipt(indexed, receipt_raw, expected_source)
        return entry, indexed, receipt, sha256(receipt_raw.encode()).hexdigest()
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise ValidationError('Registered target catalog metadata is malformed') from error


@dataclass(frozen=True, slots=True)
class TargetActionSourceReview:
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    source: TargetActionSource
    policy: LicensePolicy
    source_path: Path
    source_binding: dict


def review_target_action_source(store, *, database_path, clip_id, expected_project_id,
        expected_revision, expected_master_blend, expected_project_sha256, cancel=None, timeout_s=30):
    with operation_budget(cancel, timeout_s) as budget:
        return source_review(store, Path(database_path), clip_id, expected_project_id,
            expected_revision, expected_master_blend, expected_project_sha256, budget)


def source_review(store, database_path, clip_id, project_id, revision, master_blend, project_sha, budget):
    budget.check(); store._check_safety(); project = store.load()
    if (project.project_id != project_id or project.revision != revision or project.master_blend != master_blend
            or _digest(store.file, budget.cancel) != project_sha or clip_id not in project.animations):
        raise ProjectConflict('Saved character or registered clip selection changed; review it again')
    if project.family != 'humanoid.v1' or project.base_provider != 'mpfb':
        raise ValidationError('Registered target preview requires an MPFB humanoid')
    master, master_sha = _master_file(store, project.master_blend)
    protected(master)
    record = load_source_binding(store, project_id, clip_id, budget.cancel)
    policy = LicensePolicy.from_dict(record['license'])
    allowed, reason = policy.allow('local_preview')
    if not allowed:
        raise AssetPolicyError(reason)
    before, rows = _catalog_rows(database_path, record['asset_id'], clip_id)
    entry, indexed, receipt, receipt_sha = _reference_rows(rows, clip_id, record['source_sha256'], policy)
    reference = VerifiedCatalogClip(clip_id, entry.asset_id, entry.sha256, entry.policy,
        receipt['snapshot_sha256'], receipt_sha, receipt['skeleton_fingerprint'],
        receipt['observation']['first_frame'], receipt['observation']['last_frame'], indexed.clips[0])
    if build_source_binding(project_id, reference) != record:
        raise ProjectStorageError('Registered source binding differs from current catalog metadata or policy')
    if (reference.first_frame, reference.last_frame, reference.clip.fps, reference.clip.frame_count) != (2, 301, 30, 300):
        raise ValidationError('This target-preview profile requires the complete source frames 2–301 at 30 FPS')
    source = protected(Path(entry.source_path))
    if not source.is_file() or source.stat().st_size != entry.size_bytes or _digest(source, budget.cancel) != entry.sha256:
        raise ProjectStorageError('Registered source file is missing or changed')
    if catalog_record(database_path, entry.asset_id, clip_id) != before:
        raise ProjectConflict('Registered catalog rows changed during source review')
    budget.check()
    core = TargetActionSource(entry.asset_id, clip_id, entry.sha256, _digest(_binding_path(store, clip_id), budget.cancel),
        receipt_sha, document_sha256(policy.to_dict()), before, receipt['snapshot_sha256'], receipt['skeleton_fingerprint'])
    return TargetActionSourceReview(project_id, revision, project_sha, master_sha, core, policy, source, record)


def require_review(review, expected_source_binding_sha256, expected_catalog_record_sha256):
    if (review.source.source_binding_sha256 != expected_source_binding_sha256
            or review.source.catalog_record_sha256 != expected_catalog_record_sha256):
        raise ProjectConflict('Registered source or catalog review changed; review the exact clip again')


def check_target_action_catalog(database_path, source, *, expected_database_identity, expected_parent_identity):
    """Bounded GUI-safe semantic recheck; SQLite coordination files are not inputs."""
    database = protected(Path(database_path))
    if (identity(database)[:2] != tuple(expected_database_identity)[:2]
            or identity(database.parent)[:2] != tuple(expected_parent_identity)[:2]
            or catalog_record(database, source.asset_id, source.clip_id) != source.catalog_record_sha256
            or identity(protected(database))[:2] != tuple(expected_database_identity)[:2]
            or identity(protected(database.parent))[:2] != tuple(expected_parent_identity)[:2]):
        raise ProjectConflict('Registered target preview catalog source, policy or ancestry changed')
