"""Unity's guarded, cancellable new-folder export transaction and final admission."""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Callable
import math
import os
import sys
import time

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.storage import ProjectStore, _lock
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_contract import UnityExportRequest
from .export_destination import ExportDestination, rename_new
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity, regular_file
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel
from .static_export_sources import static_export_sources
from .unity_preparation import prepare_unity_source
from .unity_runtime_preparation import prepare_unity_runtime_source
from .unity_engine import prepare_unity_engine, tree_hashes
from .unity_runtime_verification import verify_unity_runtime
from .unity_export_payload import (POLICY, RECEIPT, stage_payload, check_snapshot,
    snapshot, verify_unity_export_result, bounded_paths)
from .worker_resources import bundled_unity_adapter_paths, worker_dependency_files
from .receipt_ownership import invalidate_owned_receipt


def _protected_file(path: Path) -> None:
    # Empty Python package markers are valid protected inputs too.
    if (path.is_symlink() or not path.is_file() or path.resolve() != path
            or path.stat().st_size > 512*1024*1024
            or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)() for p in path.parents)):
        raise ProjectStorageError('Unity export protected input is missing, redirected or oversized')


def _source_snapshot(store: ProjectStore, cancel) -> dict:
    """Freeze all saved provenance/ancestry, including identical-byte replacements."""
    result = {}
    counter = [0]
    for name in ('master', 'expressions', 'parts', 'materials', 'history'):
        root = store.root/name
        for path in bounded_paths(root, cancel, counter=counter):
            key = path.relative_to(store.root).as_posix()
            if not path.exists():
                result[key] = None
            elif path.is_file():
                _protected_file(path)
                result[key] = (identity(path), _digest(path, cancel))
            elif path.is_dir():
                result[key] = identity(path)
            else:
                raise ProjectStorageError('Unity source closure contains an unsupported filesystem entry')
    return result


@dataclass(frozen=True, slots=True)
class UnityExport:
    destination: Path
    request_sha256: str
    receipt_sha256: str
    master_sha256: str
    workdir: Path
    maximum_source_position_error_m: float
    maximum_normal_angle_deg: float


def export_unity(store: ProjectStore, *, request: UnityExportRequest, destination: ExportDestination,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path, unity_exe: Path,
        cancel: Event | None=None, timeout_s: float=3600,
        progress: Callable[[str], None] | None=None) -> UnityExport:
    """Use one deadline and truthful failure reasons across every boundary stage."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not .05 <= timeout_s <= 3600):
        raise ValidationError('Unity export needs a reviewed request, new destination and bounded total deadline')
    deadline, _ = _cancel_context(cancel, time.monotonic()+timeout_s)
    try:
        return _export_unity(store, request=request, destination=destination, blender_exe=blender_exe,
            worker_script=worker_script, mpfb_data_dir=mpfb_data_dir, unity_exe=unity_exe,
            cancel=cancel, timeout_s=timeout_s, progress=progress, deadline=deadline)
    except BaseException as error:
        reason, message = getattr(error, '_ucc_unity_failure_reason', None) or _failure_reason(cancel, deadline)
        if reason is None:
            raise
        normalized = ProjectStorageError(message)
        for note in getattr(error, '__notes__', ()):
            normalized.add_note(note)
        normalized.add_note('Underlying failure: '+type(error).__name__+': '+str(error)[:1500])
        raise normalized from error


def _cancel_context(cancel, deadline: float) -> tuple[float, bool]:
    """Separate actual user flags from deadlines in known nested cancel budgets."""
    current = cancel
    seen = set()
    user_cancelled = False
    while isinstance(current, _BudgetCancel):
        if id(current) in seen or len(seen) >= 64:
            raise ValidationError('Unity export cancellation budget chain is cyclic or too deep')
        seen.add(id(current))
        if Event.is_set(current):
            user_cancelled = True
        if type(current.deadline) not in (int, float) or not math.isfinite(current.deadline):
            raise ValidationError('Unity export cancellation budget has an invalid deadline')
        deadline = min(deadline, current.deadline)
        current = current.user
    if current is not None and current.is_set():
        user_cancelled = True
    return deadline, user_cancelled


def _failure_reason(cancel, deadline: float) -> tuple[str | None, str | None]:
    deadline, user_cancelled = _cancel_context(cancel, deadline)
    if user_cancelled:
        return 'user_cancel', 'Unity export cancelled by caller; saved character preserved'
    if time.monotonic() >= deadline:
        return 'total_deadline', 'Unity export total deadline exceeded; saved character preserved'
    return None, None


def _export_unity(store: ProjectStore, *, request: UnityExportRequest, destination: ExportDestination,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path, unity_exe: Path,
        cancel: Event | None, timeout_s: float, progress: Callable[[str], None] | None,
        deadline: float) -> UnityExport:
    """Preserve the saved character; publish only an independently admitted payload.

    Publication is provisional until the final destination's sealed bytes have
    passed actual graphical Unity verification through an identical private copy.
    Any failure moves our owned destination back to retained staging; a raced-in
    destination is never replaced, removed or adopted as our own.
    """
    if (type(request) is not UnityExportRequest or type(destination) is not ExportDestination
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not .05 <= timeout_s <= 3600 or (progress is not None and not callable(progress))):
        raise ValidationError('Unity export needs a reviewed request, new destination and bounded total deadline')
    budget = _BudgetCancel(cancel, deadline)

    def remaining() -> float:
        reason, message = _failure_reason(cancel, deadline)
        if reason is not None:
            raise ProjectStorageError(message)
        return max(.05, deadline-time.monotonic())

    remaining()
    initial = store.load()
    destination.unchanged()
    review, sources, binding = static_export_sources(store, project_id=request.project_id,
        revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unity export')
    if (review.project_sha256 != request.project_sha256
            or dict(request.source_bindings) != {s.asset_id:s.sha256 for s in review.sources}):
        raise ProjectConflict('Unity export source/rights review is stale; review the exact saved inputs again')
    unity = regular_file(Path(unity_exe), Path(unity_exe).parent, 512*1024*1024)
    blender = regular_file(Path(blender_exe), Path(blender_exe).parent, 512*1024*1024)
    worker = regular_file(Path(worker_script), Path(worker_script).parent, 256*1024)
    if _digest(unity, budget) != request.unity_executable_sha256:
        raise ValidationError('Selected Unity executable differs from the reviewed executable')
    protected = {store.file, *sources.values(), unity, blender, *worker_dependency_files(worker),
                 *bundled_unity_adapter_paths().values()}
    protected.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    if getattr(sys, 'frozen', False):
        protected.add(Path(sys.executable).resolve())
    protected.update(safe_directory(store, 'materials', 'proofs')/(binding[key]+'.json')
        for key in ('recipe_sha256', 'stage_sha256', 'verification_sha256'))
    protected.update(safe_directory(store, 'master', 'versions')/(binding[key]+'.blend')
        for key in ('source_master_sha256', 'material_master_sha256', 'final_master_sha256'))
    for path in protected:
        _protected_file(path)
    hashes = {path:_digest(path, budget) for path in protected}
    identities = {path:identity(path) for path in protected}
    source_snapshot = _source_snapshot(store, budget)
    stage = None
    stage_identity = None
    sealed = None
    published = False

    def guard() -> None:
        remaining()
        if store.load() != initial:
            raise ProjectConflict('Saved character changed during Unity export; review it again')
        for path, expected in hashes.items():
            _protected_file(path)
            if identity(path) != identities[path] or _digest(path, budget) != expected:
                raise ProjectStorageError('Unity export source, rights proof, executable or first-party resource changed')
        current, _, current_binding = static_export_sources(store, project_id=request.project_id,
            revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unity export')
        if current != review or current_binding != binding:
            raise ProjectConflict('Unity export source, permission or material proof closure changed')
        if _source_snapshot(store, budget) != source_snapshot:
            raise ProjectStorageError('Unity saved source/proof ancestry or history changed')
        parent = destination.path.parent
        if (parent.resolve() != parent or identity(parent) != destination.parent_identity
                or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)()
                       for p in (parent, *parent.parents))):
            raise ProjectStorageError('Unity export destination parent changed or was redirected')
        if published:
            if identity(destination.path) != stage_identity:
                raise ProjectStorageError('Published Unity destination was replaced')
            check_snapshot(destination.path, sealed, budget)

    guard()
    work = safe_directory(store, '.ucc-jobs', create=True)/('unity-export-'+request.job_id)
    work.mkdir(exist_ok=False)
    work_identity = identity(work)

    def journal(state: str, **extra) -> None:
        if work.resolve() != work or identity(work) != work_identity:
            raise ProjectStorageError('Unity export journal folder changed')
        path = work/'job_status.json'
        temporary = work/'job_status.tmp'
        if path.is_symlink() or temporary.exists() or temporary.is_symlink():
            raise ProjectStorageError('Unity export journal path was redirected')
        data = {'schema_version':1, 'policy':POLICY, 'request_sha256':request.sha256,
            'state':state, 'destination':str(destination.path), 'export_published':False, **extra}
        temporary_owner = None
        try:
            with temporary.open('xb') as stream:
                opened = os.fstat(stream.fileno())
                temporary_owner = (opened.st_dev, opened.st_ino)
                stream.write(canonical_bytes(data)); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException as error:
            # A failed replacement must not strand a COMPLETE temporary record
            # that prevents the subsequent FAILED journal update.
            try:
                if (temporary_owner is not None and temporary.is_file() and not temporary.is_symlink()
                        and temporary.resolve() == temporary
                        and (temporary.stat().st_dev, temporary.stat().st_ino) == temporary_owner):
                    temporary.unlink()
            except OSError as cleanup:
                error.add_note('Owned Unity journal temporary cleanup failed: '+str(cleanup))
            raise

    def phase(state: str) -> None:
        guard(); journal(state)
        if progress is not None:
            progress(state)
        guard()

    try:
        phase('SOURCE_PREPARATION')
        prepared = prepare_unity_source(store, request=request, blender_exe=blender, worker_script=worker,
            mpfb_data_dir=mpfb_data_dir, cancel=budget, timeout_s=remaining())
        phase('RUNTIME_SOURCE_PREPARATION')
        runtime_source = prepare_unity_runtime_source(store, prepared, request=request,
            blender_exe=blender, worker_script=worker, mpfb_data_dir=mpfb_data_dir, cancel=budget, timeout_s=remaining())
        phase('UNITY_IMPORT')
        engine = prepare_unity_engine(prepared, request=request, spec=SkinMaterialSpec.from_dict(binding['spec']),
            unity_exe=unity, work=work/'native-import', guard=guard, cancel=budget, timeout_s=remaining())
        phase('DESTINATION_STAGING')
        destination.unchanged()
        stage = destination.stage(request.job_id)
        stage_identity = identity(stage)
        sealed = stage_payload(engine, stage, request, budget)
        with _lock(store.root/'.project.ucc.lock', timeout_s=min(3., remaining())):
            guard(); destination.unchanged()
            if identity(stage) != stage_identity:
                raise ProjectStorageError('Unity export staging directory was replaced')
            check_snapshot(stage, sealed, budget)
            rename_new(stage, destination.path)
            published = True
        phase('PUBLISHED_RUNTIME_VERIFICATION')
        final_engine = replace(engine, directory=destination.path)
        admitted = verify_unity_runtime(final_engine, runtime_source, request=request, unity_exe=unity,
            work=work/'published-runtime', guard=guard, cancel=budget, timeout_s=remaining(),
            native_import_receipt=engine.directory.parent/'native-import-receipt.json',
            published_files=tree_hashes(destination.path, budget))
        guard()
        receipt = {'schema_version':1, 'policy':POLICY, 'request_sha256':request.sha256,
            'master_sha256':dict(request.source_bindings)['master'], 'files':sealed,
            'unity_executable_sha256':hashes[unity], 'source_verification_sha256':prepared.verification_sha256,
            'runtime_source_verification_sha256':runtime_source.verification_sha256,
            'native_import_receipt_sha256':engine.receipt_sha256, 'runtime_admission_sha256':admitted.receipt_sha256,
            'maximum_source_position_error_m':admitted.maximum_source_position_error_m,
            'maximum_normal_angle_deg':admitted.maximum_normal_angle_deg,
            'private_runtime_diagnostics_verified':True, 'diagnostic_states':178, 'cameras':2,
            'final_payload_verified':True, 'export_published':True, 'project_metadata_changed':False,
            'animation_clips_verified':False, 'visual_quality_approved':False,
            'distribution_license_review_complete':False}
        receipt_file = destination.path/RECEIPT
        receipt_bytes = canonical_bytes(receipt)
        receipt_owner = None
        with receipt_file.open('xb') as stream:
            opened = os.fstat(stream.fileno())
            receipt_owner = (opened.st_dev, opened.st_ino)
            stream.write(receipt_bytes); stream.flush(); os.fsync(stream.fileno())
        receipt_sha = _digest(receipt_file, budget)
        sealed = sealed | {RECEIPT:receipt_sha}
        result = UnityExport(destination.path, request.sha256, receipt_sha, dict(request.source_bindings)['master'],
            work, admitted.maximum_source_position_error_m, admitted.maximum_normal_angle_deg)
        guard(); verify_unity_export_result(result, budget)
        journal('COMPLETE', export_published=True, receipt_sha256=receipt_sha, final_payload_verified=True)
        if progress is not None:
            progress('COMPLETE')
        guard()
        return result
    except BaseException as error:
        reason, normalized_message = _failure_reason(cancel, deadline)
        error._ucc_unity_failure_reason = (reason, normalized_message)
        error.add_note('Unity export diagnostics retained in '+str(work))
        rolled_back = False
        if published and stage is not None:
            try:
                parent = destination.path.parent
                if (not stage.exists() and not stage.is_symlink() and parent.resolve() == parent
                        and identity(parent) == destination.parent_identity
                        and destination.path.is_dir() and not destination.path.is_symlink()
                        and destination.path.resolve() == destination.path
                        and identity(destination.path) == stage_identity):
                    rename_new(destination.path, stage)
                    rolled_back = True
                    # Never leave a withdrawn export carrying a current success receipt.
                    withdrawn = stage/RECEIPT
                    if withdrawn.is_file() and not withdrawn.is_symlink():
                        if ('receipt_owner' not in locals() or receipt_owner is None
                                or not invalidate_owned_receipt(withdrawn, receipt_bytes, receipt_owner)):
                            error.add_note('Retained receipt was changed externally; do not treat the rolled-back stage as a published export')
                else:
                    error.add_note('Unity rollback could not establish exclusive ownership; retained destination: '+str(destination.path))
            except (OSError, ProjectStorageError) as rollback:
                error.add_note('Unity rollback failed; inspect retained destination '+str(destination.path)+': '+str(rollback))
        try:
            journal('FAILED', error_type='ProjectStorageError' if reason else type(error).__name__,
                error=normalized_message or str(error)[:1500], raw_error_type=type(error).__name__,
                raw_error=str(error)[:1500], failure_reason=reason or 'error',
                cancelled=reason=='user_cancel', total_deadline_exceeded=reason=='total_deadline',
                rolled_back=rolled_back, retained_stage=None if stage is None else str(stage),
                publication_may_remain=published and not rolled_back)
        except (OSError, ProjectStorageError) as journal_error:
            error.add_note('Unity export journal failure: '+str(journal_error))
        raise
