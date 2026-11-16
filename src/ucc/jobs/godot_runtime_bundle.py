"""Atomically retain private native runtime inputs without executing their code.

Source-production and target-application verification are separate required
gates. A retained bundle is neither a shipping export nor an approved runtime.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import tempfile
from threading import Event
from typing import Callable
import time

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore, _lock
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import NativeRuntimeRequest, EVIDENCE
from ucc.export.godot_runtime_data import LIMITS, validate_runtime_files
from .expression_storage import safe_directory
from .godot_candidate_inputs import project_sources, regular_file, read_json, identity, check_cancel
from .master_preview import _digest
from .runner import WorkerFailure


@dataclass(frozen=True, slots=True)
class PrivateNativeRuntimeInputs:
    directory: Path
    request_sha256: str
    validation_sha256: str

    @property
    def runtime_execution_verified(self) -> bool:
        return False


def retain_private_native_runtime_inputs(store: ProjectStore, request: NativeRuntimeRequest, *,
        candidate_folder: Path, motion_sources: dict[str, Path], native_evidence: dict[str, Path],
        cancel: Event | None = None, timeout_s: float = 120,
        source_guard: Callable[[],None] | None = None) -> PrivateNativeRuntimeInputs:
    """Check exact permissions/sources/bytes, then atomically add a private bundle.

    Never runs caller-supplied scripts, saves a master, changes project metadata,
    rewrites rights, overwrites an earlier candidate or grants readiness.
    """
    if (not isinstance(request, NativeRuntimeRequest) or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Runtime retention needs a supported request and bounded total deadline')
    request = NativeRuntimeRequest.from_bytes(canonical_bytes(request.to_dict()))
    start = time.monotonic()

    def check() -> None:
        check_cancel(cancel)
        if time.monotonic()-start >= timeout_s:
            raise WorkerFailure('Runtime input retention exceeded its total deadline')

    check(); store._check_safety(); folder = Path(candidate_folder)
    if folder.is_symlink() or not folder.is_dir() or folder.resolve() != folder:
        raise ProjectStorageError('Select a canonical private runtime input directory')
    project = store.load()
    if (project.project_id != request.project_id or project.revision != request.revision
            or project.master_blend != 'master/versions/'+request.master_sha256+'.blend'
            or _digest(store.file, cancel) != request.project_file_sha256):
        raise ProjectConflict('Runtime request differs from the saved character revision/master')
    sources = dict(project_sources(store, project, cancel))
    if (type(motion_sources) is not dict or len(motion_sources) != 1
            or any(type(name) is not str or not name.startswith('motion:') or name in sources or not isinstance(path, Path)
                   for name, path in motion_sources.items())):
        raise ValidationError('Runtime inputs require one explicit original motion source')
    sources.update(motion_sources)
    if set(sources) != set(dict(request.source_bindings)):
        raise ValidationError('Runtime permissions must cover every registered original source')
    if type(native_evidence) is not dict or set(native_evidence) != EVIDENCE or any(not isinstance(p, Path) for p in native_evidence.values()):
        raise ValidationError('Runtime inputs require explicit native review/timeline evidence')
    roots = (store.root, folder)
    expected = {**{path: dict(request.source_bindings)[name] for name, path in sources.items()},
                **{path: dict(request.evidence_bindings)[name] for name, path in native_evidence.items()},
                **{folder/name: sha for name, sha in request.files}}
    # A single path cannot claim incompatible source/evidence/file hashes.
    rows = [(path, dict(request.source_bindings)[name]) for name, path in sources.items()]
    rows += [(path, dict(request.evidence_bindings)[name]) for name, path in native_evidence.items()]
    rows += [(folder/name, sha) for name, sha in request.files]
    if any(expected[path] != sha for path, sha in rows):
        raise ValidationError('Runtime input path has contradictory content bindings')
    watched = {store.file, *roots, *expected}
    for path in tuple(watched):
        root = next((root for root in roots if path.is_relative_to(root)), None)
        if root is None:
            raise ProjectStorageError('Runtime source/evidence is outside the selected project/input directories')
        regular_file(path, root, 512*1024*1024) if path not in roots else None
        for parent in path.parents:
            if parent == root:
                break
            if not parent.is_relative_to(root):
                break
            watched.add(parent)
    identities = {path: identity(path) for path in watched}

    def unchanged() -> None:
        check(); current = store.load()
        if source_guard is not None:source_guard()
        if (current.project_id != request.project_id or current.revision != request.revision
                or _digest(store.file, cancel) != request.project_file_sha256):
            raise ProjectConflict('Saved character changed during runtime retention')
        if dict(project_sources(store, current, cancel)) != {name: path for name, path in sources.items() if not name.startswith('motion:')}:
            raise ProjectStorageError('Registered runtime source selection changed')
        for path, previous in identities.items():
            if path.is_symlink() or not path.exists() or identity(path) != previous:
                raise ProjectStorageError('Runtime input or directory identity changed')
        for path, sha in expected.items():
            check(); root = next(root for root in roots if path.is_relative_to(root))
            regular_file(path, root, 512*1024*1024)
            if _digest(path, cancel) != sha:
                raise ProjectStorageError('Runtime source/evidence content changed: '+path.name)
        for permission in request.permissions:
            permission.require_godot()
            if permission.asset_id != 'master' and not permission.asset_id.startswith('motion:'):
                rights = read_json(sources[permission.asset_id], 4*1024*1024).get('rights', {})
                if rights.get('no_ai') and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                    raise ValidationError('Runtime permission must retain the registered NoAI restriction')

    unchanged(); validate_runtime_files(folder, request, check)
    jobs = safe_directory(store, '.ucc-jobs', create=True); work = jobs/('native-runtime-'+request.job_id)
    if work.exists() or work.is_symlink():
        raise ProjectStorageError('Runtime job identity already exists')
    work.mkdir(exist_ok=False); staged = work/'inputs'; staged.mkdir()
    destination: Path | None = None

    def journal(state: str, **details) -> None:
        path = work/'job_status.json'
        if path.is_symlink():
            raise ProjectStorageError('Runtime journal was redirected')
        descriptor, name = tempfile.mkstemp(prefix='status-', suffix='.tmp', dir=work)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(canonical_bytes({'schema_version': 1, 'job_id': request.job_id,
                    'request_sha256': request.sha256, 'state': state,
                    'runtime_execution_verified': False, **details}))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    try:
        journal('STAGING_PRIVATE_INPUTS')
        for name, sha in request.files:
            check(); shutil.copy2(folder/name, staged/name)
            if _digest(staged/name, cancel) != sha:
                raise ProjectStorageError('Runtime input changed while copying: '+name)
        (staged/'.gdignore').write_text('', encoding='utf-8')
        (staged/'request.json').write_bytes(canonical_bytes(request.to_dict()))
        observed = validate_runtime_files(staged, request, check)
        (staged/'byte_validation.json').write_bytes(canonical_bytes(observed))
        validation_sha = _digest(staged/'byte_validation.json', cancel)
        unchanged(); check()
        root = safe_directory(store, '.ucc-candidates', 'godot-runtime-inputs', create=True)
        destination = root/request.job_id
        with _lock(store.root/'.project.ucc.lock', timeout_s=min(3., max(.001, timeout_s-(time.monotonic()-start)))):
            unchanged(); check()
            validate_runtime_files(staged, request, check)
            if _digest(staged/'request.json', cancel) != request.sha256 or _digest(staged/'byte_validation.json', cancel) != validation_sha:
                raise ProjectStorageError('Runtime request/validation changed before retention')
            if destination.exists() or destination.is_symlink():
                raise ProjectStorageError('Earlier runtime inputs occupy this identity')
            check(); os.rename(staged, destination)
        check()
        journal('PRIVATE_INPUTS_RETAINED_NOT_EXECUTED', candidate=str(destination), validation_sha256=validation_sha)
        return PrivateNativeRuntimeInputs(destination, request.sha256, validation_sha)
    except BaseException as error:
        if destination is not None and not staged.exists() and destination.is_dir() and not destination.is_symlink():
            try:
                os.rename(destination, staged)
            except OSError as rollback_error:
                error.add_note('Runtime input rollback failed: '+str(rollback_error))
        try:
            journal('FAILED', error_type=type(error).__name__, error=str(error)[:1500])
        except (OSError, ProjectStorageError) as journal_error:
            error.add_note('Runtime failure journal unavailable: '+str(journal_error))
        raise
