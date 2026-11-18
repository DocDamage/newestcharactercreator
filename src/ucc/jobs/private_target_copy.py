"""Copy a saved neutral MPFB baseline into its own private working folder."""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from ucc.core.authored_idle import saved_authoring_sources
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import (MAX_JSON_BYTES, PROJECT_FILE, ProjectStore, _nonfinite_project_number,
                              _unique_project_fields)
from ucc.core.target_action_format import MAX_FILE_BYTES, RETAINED_FILES
from .animation_reference_storage import load_source_binding
from .authored_idle_sources import _registered_character_sources
from .export_destination import plan_destination, rename_new
from .export_guards import bounded_paths
from .godot_candidate_inputs import identity
from .master_preview import MAX_BLEND_BYTES
from .target_action_context import Budget, operation_budget, protected
from .target_action_storage import read_target_action_binding


_OMITTED = frozenset({'.ucc-jobs', '.ucc-candidates'})
_ROOT_FOLDERS = frozenset({'master', 'expressions', 'parts', 'history', 'animations', 'materials'})
_DIRS = _ROOT_FOLDERS | {
    'master/versions', 'expressions/manifests', 'expressions/reports', 'expressions/inspections',
    'expressions/revisions', 'parts/objects', 'parts/manifests', 'parts/revisions',
    'animations/references', 'animations/actions', 'materials/manifests', 'materials/proofs',
}
_CONTENT_FOLDERS = {
    'master/versions': '.blend', 'expressions/manifests': '.json', 'expressions/reports': '.json',
    'expressions/inspections': '.json', 'expressions/revisions': '.json', 'parts/objects': '.blend',
    'parts/manifests': '.json', 'parts/revisions': '.json', 'animations/references': '.json',
}
_UNHASHED_FILENAMES = {'expressions/revisions', 'parts/revisions', 'animations/references'}
_HISTORY_NAME = re.compile(r'project-r([0-9]{8,})-([0-9a-f]{16})\.ucc\.json')
_ACTION_PREFIX = re.compile(r'animations/actions/([0-9a-f]{64})(?:/(.*))?')
_ACTION_FILES = RETAINED_FILES | {'binding.json'}
_ACTION_DIRS = {path.rsplit('/', 1)[0] for path in RETAINED_FILES if '/' in path} | {''}
_MAX_COPY_BYTES = 8*1024**3
_REPARSE_POINT = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


@dataclass(frozen=True, slots=True)
class _Entry:
    stamp: tuple[int, int, int, int]
    digest: str | None = None


def _local(path: Path) -> Path:
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ValidationError('Choose an absolute local private target copy path')
    if path.drive and any(':' in part for part in path.parts[1:]):
        raise ValidationError('Choose a path without alternate data streams')
    try:
        info = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
            raise ProjectStorageError('Private target copy cannot open a redirected or reparse-point entry')
    return protected(path)


def _baseline(project: CharacterProject) -> None:
    if type(project) is not CharacterProject or (project.family, project.base_provider) != ('humanoid.v1', 'mpfb'):
        raise ValidationError('Open a saved MPFB humanoid before creating a target copy')
    saved_authoring_sources(project)


def _file_stamp(path: Path) -> tuple[int, int, int, int]:
    info = _local(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProjectStorageError('Private target copy requires independent local regular files')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_exact(path: Path, stamp, budget: Budget, write=None) -> str:
    digest = sha256()
    amount = 0
    _local(path)
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != stamp or info.st_nlink != 1:
            raise ProjectStorageError('Private target copy source file was replaced')
        while True:
            budget.check()
            block = stream.read(min(1024*1024, stamp[2] - amount + 1))
            if not block:
                break
            amount += len(block)
            if amount > stamp[2]:
                raise ProjectStorageError('Private target copy source file grew during transfer')
            digest.update(block)
            if write is not None:
                write(block)
    if amount != stamp[2] or _file_stamp(path) != stamp:
        raise ProjectStorageError('Private target copy source file changed during transfer')
    return digest.hexdigest()


def _file_entry(root: Path, relative: str, budget: Budget) -> _Entry:
    path = root/relative
    parent, _, name = relative.rpartition('/')
    history = _HISTORY_NAME.fullmatch(name) if parent == 'history' else None
    content_suffix = _CONTENT_FOLDERS.get(parent)
    action = _ACTION_PREFIX.fullmatch(relative)
    action_file = action is not None and action[2] in _ACTION_FILES
    if (relative != PROJECT_FILE and history is None and not action_file
            and (content_suffix is None or re.fullmatch(r'[0-9a-f]{64}'+re.escape(content_suffix), name) is None)):
        raise ValidationError('The saved project contains an unsupported private target copy file')
    stamp = _file_stamp(path)
    limit = MAX_FILE_BYTES if action_file else MAX_BLEND_BYTES if content_suffix == '.blend' else MAX_JSON_BYTES
    if not 0 < stamp[2] <= limit:
        raise ProjectStorageError('A private target copy file is empty or exceeds its bounded size')
    digest = _read_exact(path, stamp, budget)
    if ((history is not None and not digest.startswith(history[2]))
            or (content_suffix is not None and parent not in _UNHASHED_FILENAMES and path.stem != digest)):
        raise ProjectStorageError('A saved private target copy file differs from its content address')
    return _Entry(stamp, digest)


def _inventory(root: Path, budget: Budget, *, omit_private=False) -> dict[str, _Entry]:
    rows = {'': _Entry(identity(_local(root)))}
    used = [0]
    size = 0
    with os.scandir(root) as children:
        for child in children:
            budget.check()
            path = _local(root/child.name)
            if child.name in _OMITTED and omit_private and path.is_dir():
                continue
            if child.name not in _ROOT_FOLDERS and child.name != PROJECT_FILE:
                raise ValidationError('The saved project contains an unsupported private target copy entry')
            for entry in bounded_paths(path, budget.cancel, counter=used):
                relative = entry.relative_to(root).as_posix()
                if entry.is_dir():
                    action = _ACTION_PREFIX.fullmatch(relative)
                    if relative not in _DIRS and (action is None or (action[2] or '') not in _ACTION_DIRS):
                        raise ValidationError('The saved project contains an unsupported private target copy folder')
                    rows[relative] = _Entry(identity(_local(entry)))
                else:
                    row = _file_entry(root, relative, budget)
                    rows[relative] = row
                    size += row.stamp[2]
                    if size > _MAX_COPY_BYTES:
                        raise ProjectStorageError('The private target copy exceeds its total byte limit')
    if PROJECT_FILE not in rows:
        raise ProjectStorageError('The private target copy has no saved project metadata')
    return rows


def _read_metadata(path: Path, entry: _Entry) -> dict:
    with _local(path).open('rb') as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) != entry.stamp[2] or sha256(raw).hexdigest() != entry.digest or _file_stamp(path) != entry.stamp:
        raise ProjectStorageError('Saved metadata changed during private target copy review')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_project_fields, parse_constant=_nonfinite_project_number)
        if type(value) is dict:
            return value
    except (ValueError, RecursionError) as error:
        raise ValidationError('The saved project contains malformed target copy metadata') from error
    raise ValidationError('The saved project contains unsupported target copy metadata')


def _admit_animations(store: ProjectStore, project: CharacterProject, rows: dict[str, _Entry], budget: Budget) -> None:
    references = set()
    for relative, entry in rows.items():
        budget.check()
        if relative.startswith('animations/references/'):
            raw = _read_metadata(store.root/relative, entry)
            clip = raw.get('clip_id')
            if (type(clip) is not str or sha256(clip.encode('utf-8')).hexdigest()+'.json' != Path(relative).name
                    or load_source_binding(store, project.project_id, clip, budget.cancel) != raw):
                raise ValidationError('A saved animation reference differs from its registered identity')
            references.add(clip)
        action = _ACTION_PREFIX.fullmatch(relative)
        if action is not None and action[2] is None:
            binding = read_target_action_binding(store, action[1], cancel=budget.cancel)
            if binding.target.project_id != project.project_id:
                raise ValidationError('A retained target Action belongs to a different saved project')
            for item in binding.files:
                row = rows.get(f'{relative}/{item.name}')
                if row is None or row.digest != item.sha256 or row.stamp[2] != item.bytes:
                    raise ProjectStorageError('A retained target Action differs from its saved file inventory')
    if not set(project.animations) <= references:
        raise ValidationError('A current attached clip has no saved animation reference')


def _admit_history(store: ProjectStore, project: CharacterProject, rows: dict[str, _Entry], budget: Budget) -> None:
    for relative, row in rows.items():
        if not relative.startswith('history/'):
            continue
        budget.check()
        path = store.root/relative
        raw = _read_metadata(path, row)
        try:
            snapshot = CharacterProject.from_dict(raw)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise ValidationError('The saved project contains unsupported target copy history') from error
        recorded = _HISTORY_NAME.fullmatch(path.name)
        if (recorded is None or int(recorded[1]) != snapshot.revision or snapshot.revision >= project.revision
                or snapshot.project_id != project.project_id or snapshot.appearance):
            raise ValidationError('The saved project contains incompatible target copy history')
        for clip in snapshot.animations:
            load_source_binding(store, project.project_id, clip, budget.cancel)
        if snapshot.master_blend is not None:
            _baseline(snapshot)
            _registered_character_sources(store, snapshot, budget.cancel)
        elif snapshot.parts or snapshot.expression is not None:
            raise ValidationError('The saved project history references an unavailable saved character')


def _populate(source: Path, stage: Path, rows: dict[str, _Entry], owned: dict[str, _Entry], budget: Budget) -> None:
    for name in sorted(rows):
        if not name:
            continue
        budget.check()
        row = rows[name]
        path = _local(stage/name)
        parent = path.parent.relative_to(stage).as_posix()
        if identity(path.parent) != owned['' if parent == '.' else parent].stamp:
            raise ProjectStorageError('Private target copy staging parent changed')
        if row.digest is None:
            path.mkdir()
            owned[name] = _Entry(identity(_local(path)))
        else:
            _write_stage_file(source/name, path, row, owned, name, budget)
            copied = _file_entry(stage, name, budget)
            if copied != owned.get(name) or copied.digest != row.digest:
                raise ProjectStorageError('Private target copy did not preserve the saved file digest')


def _write_stage_file(source: Path, target: Path, row: _Entry, owned: dict[str, _Entry], name: str, budget: Budget) -> None:
    inode = None
    digest = sha256()
    amount = 0
    try:
        with target.open('xb', buffering=0) as output:
            info = os.fstat(output.fileno())
            inode = info.st_dev, info.st_ino

            def write(block):
                nonlocal amount
                size = output.write(block)
                if size is not None:
                    amount += size
                    digest.update(block[:size])
                if size != len(block):
                    raise ProjectStorageError('Private target copy encountered an incomplete write')

            _read_exact(source, row.stamp, budget, write)
            os.fsync(output.fileno())
    finally:
        # A partial file is ours only when the exact successful writes can be proved.
        if inode is not None:
            try:
                stamp = _file_stamp(target)
            except (OSError, ValidationError, ProjectStorageError):
                pass
            else:
                if stamp[:2] == inode and stamp[2] == amount:
                    owned[name] = _Entry(stamp, digest.hexdigest())


def _owned_file(path: Path, row: _Entry, budget: Budget) -> bool:
    return _file_stamp(path) == row.stamp and _read_exact(path, row.stamp, budget) == row.digest


def _discard(root: Path, parent_stamp, owned: dict[str, _Entry], error: BaseException) -> None:
    try:
        budget = Budget(None, 60)
        if identity(_local(root.parent)) != parent_stamp or identity(_local(root)) != owned[''].stamp:
            raise ProjectStorageError('Private target copy output ownership changed')
        actual = {path.relative_to(root).as_posix() for path in bounded_paths(root, budget.cancel) if path != root}
        if actual != owned.keys() - {''}:
            raise ProjectStorageError('Private target copy contents changed')
        for name in actual:
            row = owned[name]
            path = _local(root/name)
            matches = identity(path) == row.stamp if row.digest is None else _owned_file(path, row, budget)
            if not matches:
                raise ProjectStorageError('Private target copy contents changed')
        for name in sorted(actual, key=lambda name: (name.count('/'), name), reverse=True):
            path = _local(root/name)
            if owned[name].digest is None:
                if identity(path) != owned[name].stamp:
                    raise ProjectStorageError('Private target copy folder changed during cleanup')
                path.rmdir()
            else:
                if not _owned_file(path, owned[name], budget):
                    raise ProjectStorageError('Private target copy file changed during cleanup')
                path.unlink()
        if identity(_local(root.parent)) != parent_stamp or identity(_local(root)) != owned[''].stamp:
            raise ProjectStorageError('Private target copy output ownership changed during cleanup')
        root.rmdir()
    except (OSError, ValidationError, ProjectStorageError) as rollback:
        error.add_note(f'Private target copy retained at {root}. Ownership-safe cleanup did not complete: {rollback}')


def create_private_target_copy(store: ProjectStore, *, expected_project: CharacterProject,
                               destination: Path, cancel=None) -> Path:
    """Publish the same saved baseline at a new path without changing the original."""
    _baseline(expected_project)
    source, output = _local(store.root), _local(Path(destination))
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValidationError('Choose a new target copy folder separate from the original saved project')
    planned = plan_destination(output, source)
    try:
        with operation_budget(cancel, 300) as budget:
            if store.load() != expected_project:
                raise ProjectConflict('The saved character changed before private target copy review')
            original = _inventory(source, budget, omit_private=True)
            _registered_character_sources(store, expected_project, budget.cancel)
            _admit_animations(store, expected_project, original, budget)
            _admit_history(store, expected_project, original, budget)

            def source_current():
                if store.load() != expected_project or _inventory(source, budget, omit_private=True) != original:
                    raise ProjectConflict('The saved character or private target copy inputs changed')

            source_current()
            stage = planned.stage(str(uuid4()))
            owned = {'': _Entry(identity(_local(stage)))}
            published = False
            try:
                _populate(source, stage, original, owned, budget)
                staged_store = ProjectStore(stage)
                if staged_store.load() != expected_project or _inventory(stage, budget) != owned:
                    raise ProjectStorageError('Private target copy differs from its verified staging closure')
                source_current()
                planned.unchanged()
                budget.check()
                rename_new(stage, output)
                published = True
                if identity(_local(output.parent)) != planned.parent_identity or _inventory(output, budget) != owned:
                    raise ProjectStorageError('Published private target copy changed before closing verification')
                source_current()
                budget.check()
                return output
            except BaseException as error:
                _discard(output if published else stage, planned.parent_identity, owned, error)
                raise
    except OSError as error:
        failure = ProjectStorageError('Could not create a private target copy in the selected new folder')
        for note in getattr(error, '__notes__', ()):
            failure.add_note(note)
        raise failure from error
