"""Canonical immutable retained target-preview folders and restart loading."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import MAX_BYTES, RETAINED_FILES, checked_sha
from ucc.preview.motion_cache import MotionCache
from .animation_reference_storage import _binding_path
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .master_preview import _digest, _master_file
from .target_action_context import operation_budget, protected, source_review, require_review
from .export_guards import bounded_paths
from .target_action_resources import host_code_snapshot
import json


@dataclass(frozen=True, slots=True)
class PreparedTargetAction:
    project_id: str
    revision: int
    project_sha256: str
    master_sha256: str
    clip_id: str
    source_sha256: str
    directory: Path
    binding_path: Path
    binding_sha256: str
    cache: MotionCache
    watched_inputs: tuple[tuple[Path, str], ...]
    watched_identities: tuple[tuple[Path, tuple[int, int, int, int]], ...]
    workdir: Path | None = None


@dataclass(frozen=True, slots=True)
class TargetActionSummary:
    binding_sha256: str
    project_id: str
    prepared_revision: int
    master_sha256: str
    clip_id: str
    source_sha256: str
    mapping_sha256: str
    source_first_frame: int
    target_first_frame: int
    frame_count: int
    fps: float
    root_motion_policy: str
    skin_deformation_policy: str
    local_preview_only: bool = True


def action_root(store, create=False):
    return safe_directory(store, 'animations', 'actions', create=create)


def ancestry(paths):
    result = {}
    for path in paths:
        for item in (path, *path.parents):
            protected(item)
            if item.exists(): result[item] = identity(item)
    return result


def read_target_action_binding(store, binding_sha256, *, cancel=None):
    checked_sha(binding_sha256)
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Target preview metadata read cancelled')
    path = protected(action_root(store)/binding_sha256/'binding.json')
    with path.open('rb') as stream:
        payload = stream.read(MAX_BYTES+1)
    binding = TargetActionBinding.from_bytes(payload)
    if binding.sha256 != binding_sha256:
        raise ProjectStorageError('Target preview binding content differs from its selected identity')
    return binding


def list_target_action_bindings(store, *, clip_id=None, cancel=None, timeout_s=30):
    with operation_budget(cancel, timeout_s) as budget:
        store._check_safety()
        root = store.root/'animations/actions'
        protected(root)
        if not root.exists():
            return ()
        import os
        result = []
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries):
                budget.check()
                if count >= 256:
                    raise ProjectStorageError('Target preview listing exceeds 256 retained bindings')
                path = protected(root/entry.name)
                checked_sha(path.name)
                if not path.is_dir():
                    raise ProjectStorageError('Target preview store contains a non-directory entry')
                binding = read_target_action_binding(store, path.name, cancel=budget.cancel)
                if clip_id is None or binding.source.clip_id == clip_id:
                    result.append(TargetActionSummary(binding.sha256, binding.target.project_id,
                        binding.target.revision, binding.target.master_sha256, binding.source.clip_id,
                        binding.source.source_sha256, binding.mapping_sha256, 2, 1, 300, 30.,
                        binding.root_motion_policy, 'BOUND_CORRECTIVE_SMOOTH_V1'))
        return tuple(sorted(result, key=lambda row:row.binding_sha256))


def seal(directory, binding, budget):
    """Enumerate exact files/dirs and bind identities as well as every byte."""
    expected = set(RETAINED_FILES)|{'binding.json'}
    dirs = {p.as_posix() for name in expected for p in Path(name).parents if p != Path('.')}
    records = {}
    for path in bounded_paths(directory, budget.cancel, maximum_entries=128,
            allowed_directories=frozenset(dirs)):
        budget.check()
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            if name not in expected:
                raise ProjectStorageError('Target preview retained an unlisted file')
            size = path.stat().st_size
            if name == 'binding.json':
                if size > MAX_BYTES or _digest(path, budget.cancel) != binding.sha256:
                    raise ProjectStorageError('Target preview binding changed')
                digest = binding.sha256
            else:
                row = binding.file_map[name]
                if size != row.bytes or _digest(path, budget.cancel) != row.sha256:
                    raise ProjectStorageError('Target preview retained proof bytes changed: '+name)
                digest = row.sha256
            records[name] = (identity(path), digest)
        elif path.is_dir():
            records[path.relative_to(directory).as_posix()+'/'] = identity(path)
        else:
            raise ProjectStorageError('Target preview retained payload is missing')
    if {name for name in records if not name.endswith('/')} != expected:
        raise ProjectStorageError('Target preview retained proof inventory is incomplete')
    return records


def source_state(store, budget, exclude=None):
    result = {}
    counter = [0]
    for name in ('master', 'expressions', 'parts', 'materials', 'history', 'animations'):
        root = store.root/name
        for path in bounded_paths(root, budget.cancel, counter=counter):
            budget.check()
            if exclude is not None and path.is_relative_to(exclude):
                continue
            key = path.relative_to(store.root).as_posix()
            if not path.exists():
                result[key] = None
            elif path.is_file():
                result[key] = (identity(path), _digest(path, budget.cancel))
            elif path.is_dir():
                result[key] = identity(path)
    return result


def load_target_action(store, *, binding_sha256, database_path, expected_project_id,
        expected_revision, expected_master_blend, expected_project_sha256, expected_clip_id,
        expected_source_binding_sha256, expected_catalog_record_sha256,
        cancel=None, timeout_s=300, progress: Callable | None=None):
    with operation_budget(cancel, timeout_s) as budget:
        from .target_action_evidence import validate_retained_target_action
        host_state=host_code_snapshot(budget)
        if progress: progress('SOURCE_REVIEW')
        review = source_review(store, Path(database_path), expected_clip_id, expected_project_id,
            expected_revision, expected_master_blend, expected_project_sha256, budget)
        require_review(review, expected_source_binding_sha256, expected_catalog_record_sha256)
        binding = read_target_action_binding(store, binding_sha256, cancel=budget.cancel)
        if (binding.source != review.source or binding.target.project_id != review.project_id
                or binding.target.revision != review.revision or binding.target.project_sha256 != review.project_sha256
                or binding.target.master_sha256 != review.master_sha256):
            raise ProjectConflict('Selected saved target preview belongs to a different character/source context')
        directory = action_root(store)/binding_sha256
        database = protected(Path(database_path))
        authority = ancestry((store.root, review.source_path, database))
        authority[database] = (*identity(database)[:2], 0, 0)
        initial = source_state(store, budget)
        before = seal(directory, binding, budget)
        if progress: progress('RETAINED_VALIDATION')
        for role in ('first', 'second'):
            with (directory/'neutral'/f'{role}_result.json').open('rb') as stream:
                raw = stream.read(MAX_BYTES+1)
            if len(raw) > MAX_BYTES:
                raise ValidationError('Saved neutral proof exceeds its metadata byte limit')
            data = json.loads(raw,
                object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
            if (not isinstance(data, dict) or not isinstance(data.get('details'), dict)
                    or data['details'].get('expression_key_count') != (12 if store.load().expression else 0)):
                raise ValidationError('Saved neutral proof expression domain differs from the current character')
        cache = validate_retained_target_action(directory, binding, cancel_check=budget.check)
        current = source_review(store, Path(database_path), expected_clip_id, expected_project_id,
            expected_revision, expected_master_blend, expected_project_sha256, budget)
        if current != review or source_state(store, budget) != initial or seal(directory, binding, budget) != before:
            raise ProjectStorageError('Target preview input or retained proof closure changed during loading')
        paths = {store.file, review.source_path, _master_file(store, expected_master_blend)[0],
            _binding_path(store, expected_clip_id)}
        paths.update(directory/name for name in set(RETAINED_FILES)|{'binding.json'})
        identities = []
        hashes = []
        for path in sorted(paths, key=str):
            protected(path); budget.check()
            identities.append((path, identity(path))); hashes.append((path, _digest(path, budget.cancel)))
        for path, stamp in ancestry(paths).items():
            if path.is_dir(): identities.append((path, stamp))
        identities.extend((path, stamp) for path, stamp in authority.items()
                          if path.is_dir() or path == database)
        from .target_action_context import check_target_action_catalog
        check_target_action_catalog(database, review.source,
            expected_database_identity=authority[database][:2], expected_parent_identity=authority[database.parent][:2])
        budget.check()
        if progress: progress('COMPLETE')
        budget.check()
        for path, stamp in authority.items():
            now = identity(protected(path))
            if (now[:2] != stamp[:2] if path == database else now != stamp):
                raise ProjectStorageError('Target preview source/catalog ancestry changed during loading')
        if (source_review(store, database, expected_clip_id, expected_project_id, expected_revision,
                expected_master_blend, expected_project_sha256, budget) != review
                or source_state(store, budget) != initial or seal(directory, binding, budget) != before):
            raise ProjectStorageError('Target preview context changed before cache handoff')
        if host_code_snapshot(budget) != host_state:
            raise ProjectStorageError('Target preview host code or executable closure changed during loading')
        return PreparedTargetAction(review.project_id, review.revision, review.project_sha256,
            review.master_sha256, review.source.clip_id, review.source.source_sha256,
            directory, directory/'binding.json', binding_sha256, cache, tuple(hashes),
            tuple(sorted(dict(identities).items(), key=lambda row:str(row[0]))))
