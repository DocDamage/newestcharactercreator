"""Private static Unreal publication with one budget and ownership-safe rollback."""
from dataclasses import dataclass
from hashlib import sha256
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
from ucc.export.unreal_contract import UnrealExportRequest, ENGINE_VERSION, READINESS_FLAGS
from .export_destination import ExportDestination, rename_new
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity, regular_file
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel
from .static_export_sources import static_export_sources
from .unreal_preparation import prepare_unreal_source
from .unreal_engine import prepare_unreal_engine
from .unreal_runtime_verification import verify_unreal_published_project
from .unreal_toolchain import UnrealToolchain, preflight_unreal_toolchain
from .export_guards import (protected_file as _protected_file, source_snapshot as _source_snapshot,
    cancel_context as _cancel_context, failure_reason as _failure_reason, invalidate_owned_receipt)
from .unreal_export_payload import (POLICY, RECEIPT, stage_payload, check_snapshot,
    snapshot, verify_unreal_export_result, bounded_paths, SUCCESS_FLAGS, FALSE_FLAGS)
from .worker_resources import bundled_unreal_adapter_paths, worker_dependency_files






@dataclass(frozen=True, slots=True)
class UnrealExport:
    destination: Path
    request_sha256: str
    receipt_sha256: str
    master_sha256: str
    workdir: Path
    maximum_source_position_error_m: float
    maximum_normal_angle_deg: float


def export_unreal(store: ProjectStore, *, request: UnrealExportRequest, destination: ExportDestination,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path, unreal_exe: Path, toolchain: UnrealToolchain | None=None,
        cancel: Event | None=None, timeout_s: float=3600,
        progress: Callable[[str], None] | None=None) -> UnrealExport:
    """Use one deadline and truthful failure reasons across every boundary stage."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not .05 <= timeout_s <= 3600):
        raise ValidationError('Unreal export needs a reviewed request, new destination and bounded total deadline')
    deadline, _ = _cancel_context(cancel, time.monotonic()+timeout_s)
    try:
        return _export_unreal(store, request=request, destination=destination, blender_exe=blender_exe,
            worker_script=worker_script, mpfb_data_dir=mpfb_data_dir, unreal_exe=unreal_exe, toolchain=toolchain,
            cancel=cancel, timeout_s=timeout_s, progress=progress, deadline=deadline)
    except BaseException as error:
        reason, message = getattr(error, '_ucc_unreal_failure_reason', None) or _failure_reason(cancel, deadline)
        if reason is None:
            raise
        normalized = ProjectStorageError(message)
        for note in getattr(error, '__notes__', ()):
            normalized.add_note(note)
        normalized.add_note('Underlying failure: '+type(error).__name__+': '+str(error)[:1500])
        raise normalized from error






def _export_unreal(store: ProjectStore, *, request: UnrealExportRequest, destination: ExportDestination,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path, unreal_exe: Path, toolchain: UnrealToolchain | None,
        cancel: Event | None, timeout_s: float, progress: Callable[[str], None] | None,
        deadline: float) -> UnrealExport:
    """Preserve the saved character; publish only an independently admitted payload.

    Publication is provisional until the final destination's sealed bytes have
    passed actual static native Unreal verification through an identical private copy.
    Any failure moves our owned destination back to retained staging; a raced-in
    destination is never replaced, removed or adopted as our own.
    """
    if (type(request) is not UnrealExportRequest or type(destination) is not ExportDestination
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not .05 <= timeout_s <= 3600 or (progress is not None and not callable(progress))):
        raise ValidationError('Unreal export needs a reviewed request, new destination and bounded total deadline')
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
        revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unreal export')
    if (review.project_sha256 != request.project_sha256
            or dict(request.source_bindings) != {s.asset_id:s.sha256 for s in review.sources}):
        raise ProjectConflict('Unreal export source/rights review is stale; review the exact saved inputs again')
    unreal = regular_file(Path(unreal_exe), Path(unreal_exe).parent, 512*1024*1024)
    blender = regular_file(Path(blender_exe), Path(blender_exe).parent, 512*1024*1024)
    worker = regular_file(Path(worker_script), Path(worker_script).parent, 256*1024)
    if _digest(unreal, budget) != request.unreal_executable_sha256:
        raise ValidationError('Selected Unreal executable differs from the reviewed executable')
    if toolchain is None:
        toolchain = preflight_unreal_toolchain(unreal, cancel=budget, timeout_s=remaining())
    if type(toolchain) is not UnrealToolchain or toolchain.editor_exe != unreal:
        raise ValidationError('Unreal export needs the reviewed installed toolchain')
    toolchain.require_unchanged(budget)
    if (toolchain.identity_sha256 != request.toolchain_sha256
            or _digest(toolchain.build_version, budget) != request.unreal_build_version_sha256):
        raise ValidationError('Selected Unreal build or compiler differs from the reviewed toolchain')
    protected = {store.file, *sources.values(), unreal, blender, *worker_dependency_files(worker),
                 *bundled_unreal_adapter_paths().values()}
    protected.update(p for p in bounded_paths(Path(__file__).resolve().parents[1], budget)
                     if p.is_file() and p.suffix == '.py')
    protected.update(Path(name) for name, _ in toolchain.files)
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
        toolchain.require_unchanged(budget)
        remaining()
        if store.load() != initial:
            raise ProjectConflict('Saved character changed during Unreal export; review it again')
        for path, expected in hashes.items():
            _protected_file(path)
            if identity(path) != identities[path] or _digest(path, budget) != expected:
                raise ProjectStorageError('Unreal export source, rights proof, executable or first-party resource changed')
        current, _, current_binding = static_export_sources(store, project_id=request.project_id,
            revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unreal export')
        if current != review or current_binding != binding:
            raise ProjectConflict('Unreal export source, permission or material proof closure changed')
        if _source_snapshot(store, budget) != source_snapshot:
            raise ProjectStorageError('Unreal saved source/proof ancestry or history changed')
        parent = destination.path.parent
        if (parent.resolve() != parent or identity(parent) != destination.parent_identity
                or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)()
                       for p in (parent, *parent.parents))):
            raise ProjectStorageError('Unreal export destination parent changed or was redirected')
        if published:
            if identity(destination.path) != stage_identity:
                raise ProjectStorageError('Published Unreal destination was replaced')
            check_snapshot(destination.path, sealed, budget)

    guard()
    work = safe_directory(store, '.ucc-jobs', create=True)/('unreal-export-'+request.job_id)
    work.mkdir(exist_ok=False)
    work_identity = identity(work)

    def journal(state: str, **extra) -> None:
        if work.resolve() != work or identity(work) != work_identity:
            raise ProjectStorageError('Unreal export journal folder changed')
        path = work/'job_status.json'
        temporary = work/'job_status.tmp'
        if path.is_symlink() or temporary.exists() or temporary.is_symlink():
            raise ProjectStorageError('Unreal export journal path was redirected')
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
                error.add_note('Owned Unreal journal temporary cleanup failed: '+str(cleanup))
            raise

    def phase(state: str) -> None:
        guard(); journal(state)
        if progress is not None:
            progress(state)
        guard()

    try:
        phase('SOURCE_PREPARATION')
        prepared = prepare_unreal_source(store, request=request, blender_exe=blender, worker_script=worker,
            mpfb_data_dir=mpfb_data_dir, cancel=budget, timeout_s=remaining())
        phase('UNREAL_IMPORT')
        engine = prepare_unreal_engine(prepared, request=request, toolchain=toolchain,
            cancel=budget, timeout_s=remaining(), progress=phase)
        phase('DESTINATION_STAGING')
        destination.unchanged()
        stage = destination.stage(request.job_id)
        stage_identity = identity(stage)
        sealed = stage_payload(engine, stage, request, budget)
        with _lock(store.root/'.project.ucc.lock', timeout_s=min(3., remaining())):
            guard(); destination.unchanged()
            if identity(stage) != stage_identity:
                raise ProjectStorageError('Unreal export staging directory was replaced')
            check_snapshot(stage, sealed, budget)
            rename_new(stage, destination.path)
            published = True
        phase('PUBLISHED_UNREAL_VERIFICATION')
        admitted = verify_unreal_published_project(destination.path, source=prepared,
            request=request, toolchain=toolchain,
            engine_receipt_path=engine.workdir/'engine-receipt.json',
            engine_receipt_sha256=engine.receipt_sha256, expected_files=sealed,
            cancel=budget, timeout_s=remaining(), progress=phase)
        guard()
        if (admitted.get('request_sha256') != request.sha256
                or admitted.get('toolchain_identity_sha256') != request.toolchain_sha256
                or admitted.get('payload_files') != sealed
                or admitted.get('admission', {}).get('saved_reopened_bind_verified') is not True
                or any(admitted.get(name) is not (name in {'engine_import_verified','source_parity_verified'})
                       for name in READINESS_FLAGS)):
            raise ValidationError('Published Unreal verification lacks the exact static admission bindings')
        receipt = {'schema_version':1, 'policy':POLICY, 'request_sha256':request.sha256,
            'master_sha256':dict(request.source_bindings)['master'], 'files':sealed,
            'engine_version':ENGINE_VERSION, 'toolchain_sha256':request.toolchain_sha256,
            'source_verification_sha256':prepared.verification_sha256,
            'engine_receipt_sha256':engine.receipt_sha256,
            'published_verification_sha256':sha256(canonical_bytes(admitted)).hexdigest(),
            'maximum_source_position_error_m':engine.maximum_source_position_error_m,
            'maximum_normal_angle_deg':engine.maximum_normal_angle_deg,
            **{name:True for name in SUCCESS_FLAGS}, **{name:False for name in FALSE_FLAGS}}
        receipt_file = destination.path/RECEIPT
        receipt_bytes = canonical_bytes(receipt)
        receipt_owner = None
        with receipt_file.open('xb') as stream:
            opened = os.fstat(stream.fileno())
            receipt_owner = (opened.st_dev, opened.st_ino)
            stream.write(receipt_bytes); stream.flush(); os.fsync(stream.fileno())
        receipt_sha = _digest(receipt_file, budget)
        sealed = sealed | {RECEIPT:receipt_sha}
        result = UnrealExport(destination.path, request.sha256, receipt_sha, dict(request.source_bindings)['master'],
            work, engine.maximum_source_position_error_m, engine.maximum_normal_angle_deg)
        guard(); verify_unreal_export_result(result, budget)
        journal('COMPLETE', export_published=True, receipt_sha256=receipt_sha, final_payload_verified=True)
        if progress is not None:
            progress('COMPLETE')
        guard()
        return result
    except BaseException as error:
        reason, normalized_message = _failure_reason(cancel, deadline)
        error._ucc_unreal_failure_reason = (reason, normalized_message)
        error.add_note('Unreal export diagnostics retained in '+str(work))
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
                    error.add_note('Unreal rollback could not establish exclusive ownership; retained destination: '+str(destination.path))
            except (OSError, ProjectStorageError) as rollback:
                error.add_note('Unreal rollback failed; inspect retained destination '+str(destination.path)+': '+str(rollback))
        try:
            journal('FAILED', error_type='ProjectStorageError' if reason else type(error).__name__,
                error=normalized_message or str(error)[:1500], raw_error_type=type(error).__name__,
                raw_error=str(error)[:1500], failure_reason=reason or 'error',
                cancelled=reason=='user_cancel', total_deadline_exceeded=reason=='total_deadline',
                rolled_back=rolled_back, retained_stage=None if stage is None else str(stage),
                publication_may_remain=published and not rolled_back)
        except (OSError, ProjectStorageError) as journal_error:
            error.add_note('Unreal export journal failure: '+str(journal_error))
        raise
