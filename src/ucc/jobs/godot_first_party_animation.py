"""Run exact authorized registered animation through the first-party Godot runtime."""

from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
import os
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import checked_text
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection, RuntimeCodeSelection
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection, RetainedInputFile
from ucc.export.godot_runtime_contract import CAPABILITY, CODE_FILES
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .godot_registered_body_inputs import RegisteredBodyInputs, admit_body_inputs
from .godot_registered_body_target import VerifiedRegisteredNativeBodyDiagnostic, verify_registered_native_body_runtime
from .godot_registered_native_producer import PreparedRegisteredNativeSource, prepare_registered_native_source
from .godot_registered_runtime_admission import permission_bytes
from .godot_registered_runtime_files import copy_file, hash_file, read_bytes
from .godot_registered_runtime_storage import RetainedRegisteredNativeInputs, retain_registered_native_inputs
from .target_action_context import Budget, operation_budget, protected
from .worker_resources import bundled_registered_correction_paths


PROVENANCE_POLICY = 'UCC_FIRST_PARTY_GODOT_RUNTIME_PROVENANCE_V1'
IMPLEMENTATION = 'UCC_REGISTERED_BOUND_CORRECTIVE_MOBILE_VULKAN_V1'
MAX_CODE_BYTES = 256 * 1024
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
Progress = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class FirstPartyGodotRuntimeProvenance:
    """Identify the trusted UCC implementation selected for a private local run."""

    code: tuple[RuntimeCodeSelection, ...]

    def __post_init__(self) -> None:
        if (type(self.code) is not tuple or len(self.code) != len(CODE_FILES)
                or any(type(row) is not RuntimeCodeSelection for row in self.code)
                or tuple(row.name for row in self.code) != tuple(sorted(CODE_FILES))):
            raise ValidationError('First-party Godot provenance requires the exact bundled runtime closure')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': PROVENANCE_POLICY, 'implementation': IMPLEMENTATION,
                'origin': 'UCC_FIRST_PARTY_REPOSITORY_RESOURCES', 'use': 'PRIVATE_LOCAL_VERIFICATION_ONLY',
                'files': {row.name: {'sha256': row.sha256, 'bytes': row.bytes} for row in self.code},
                'distribution_license_review_complete': False, 'shipping_authorized': False}

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedFirstPartyGodotAnimation:
    preparation: PreparedRegisteredNativeSource
    production_receipt_sha256: str
    retained: RetainedRegisteredNativeInputs
    diagnostic: VerifiedRegisteredNativeBodyDiagnostic
    execution: RegisteredRuntimeExecutionSelection
    provenance: FirstPartyGodotRuntimeProvenance
    provenance_path: Path
    runtime_directory: Path


def _runtime_rows(budget: Budget) -> tuple[dict[str, Path], FirstPartyGodotRuntimeProvenance]:
    paths = bundled_registered_correction_paths()
    if (type(paths) is not dict or set(paths) != CODE_FILES
            or any(not isinstance(path, Path) for path in paths.values())
            or len(set(paths.values())) != len(CODE_FILES)):
        raise ValidationError('First-party Godot runtime resources differ from the fixed closure')
    rows = []
    for name, path in sorted(paths.items()):
        digest, size = hash_file(path, MAX_CODE_BYTES, budget)
        rows.append(RuntimeCodeSelection(name, digest, size))
    return paths, FirstPartyGodotRuntimeProvenance(tuple(rows))


def _check_runtime(paths: dict[str, Path], provenance: FirstPartyGodotRuntimeProvenance,
                    provenance_path: Path, runtime: Path, budget: Budget) -> None:
    current_paths, current = _runtime_rows(budget)
    if (current_paths != paths or current != provenance or not protected(runtime).is_dir()
            or {path.name for path in islice(runtime.iterdir(), len(CODE_FILES) + 1)} != CODE_FILES):
        raise ProjectStorageError('First-party Godot runtime resource closure changed')
    expected = canonical_bytes(provenance.to_dict())
    raw, _ = read_bytes(provenance_path, len(expected), budget, expected_sha256=provenance.sha256)
    if raw != expected:
        raise ProjectStorageError('First-party Godot runtime provenance changed')
    for row in provenance.code:
        if hash_file(runtime/row.name, row.bytes, budget) != (row.sha256, row.bytes):
            raise ProjectStorageError('First-party Godot staged runtime bytes changed')


def _motion_role(permissions: tuple[EngineInputPermission, ...]) -> str:
    permission_bytes(permissions)
    motions = [row.asset_id for row in permissions if row.asset_id.startswith('motion:')]
    if len(motions) != 1 or motions[0] == 'motion:':
        raise ValidationError('Select a separate Godot permission for the exact original motion')
    return motions[0]


def prepare_first_party_godot_animation(store: ProjectStore, *, selection: RegisteredInputSelection,
        database_path: Path, permissions: tuple[EngineInputPermission, ...], blender_exe: Path,
        worker_script: Path, godot_exe: Path, godot_main_exe: Path, purpose: str,
        private_local_execution_confirmed: bool, cancel: Event | None = None,
        timeout_s: float = 1800, progress: Progress | None = None) -> PreparedFirstPartyGodotAnimation:
    """Prepare retained first-party inputs and verify corrected body geometry locally."""
    if (type(store) is not ProjectStore or type(selection) is not RegisteredInputSelection
            or private_local_execution_confirmed is not True):
        raise ValidationError('Explicit private local Godot execution and exact registered source selection are required')
    checked_text(purpose, 500)
    motion_role = _motion_role(permissions)

    with operation_budget(cancel, timeout_s) as budget:
        paths, provenance = _runtime_rows(budget)
        godot_exe, godot_main_exe = protected(Path(godot_exe)), protected(Path(godot_main_exe))
        if godot_exe == godot_main_exe or godot_exe.parent != godot_main_exe.parent:
            raise ValidationError('Select the installed Godot console and matching main executable pair')
        executables = {path: (identity(path), hash_file(path, MAX_EXECUTABLE_BYTES, budget))
                       for path in (godot_exe, godot_main_exe)}
        if any(stamp[1][1] == 0 for stamp in executables.values()):
            raise ValidationError('Selected Godot executable pair cannot be empty')
        jobs = safe_directory(store, '.ucc-jobs', create=True)
        execution_id = str(uuid4())
        work = jobs/('first-party-godot-'+execution_id)
        work.mkdir(exist_ok=False)
        runtime = work/'runtime'
        runtime.mkdir(exist_ok=False)
        directory_ids = {directory: identity(directory)[:2] for directory in (jobs, work, runtime)}
        provenance_path = work/'runtime_provenance.json'
        for row in provenance.code:
            copy_file(paths[row.name], runtime/row.name, RetainedInputFile(row.name, row.sha256, row.bytes), budget)
        with provenance_path.open('xb') as stream:
            stream.write(canonical_bytes(provenance.to_dict()))
            stream.flush()
            os.fsync(stream.fileno())
        provenance_stamp = identity(protected(provenance_path))
        code_stamps = {row.name: identity(protected(runtime/row.name)) for row in provenance.code}

        def guard() -> None:
            budget.check()
            if (any(identity(protected(path))[:2] != stamp for path,stamp in directory_ids.items())
                    or identity(protected(provenance_path)) != provenance_stamp
                    or any(identity(protected(runtime/name)) != stamp for name,stamp in code_stamps.items())):
                raise ProjectStorageError('Owned first-party Godot stage identity changed')
            _check_runtime(paths, provenance, provenance_path, runtime, budget)
            for path, (stamp, record) in executables.items():
                if identity(protected(path)) != stamp or hash_file(path, record[1], budget) != record:
                    raise ProjectStorageError('Selected Godot executable changed during preparation')
            budget.check()

        guard()
        preparation = prepare_registered_native_source(store, **selection.loader_args(),
            database_path=database_path, permissions=permissions, motion_asset_id=motion_role,
            runtime_directory=runtime, runtime_code_provenance=provenance_path, requested_capability=CAPABILITY,
            blender_exe=blender_exe, worker_script=worker_script, cancel=budget.cancel,
            timeout_s=budget.remaining(), progress=progress)
        guard()
        receipt_sha, _ = hash_file(preparation.production_receipt, 2 * 1024 * 1024, budget)
        retained = retain_registered_native_inputs(store, selection=selection, preparation=preparation,
            expected_production_receipt_sha256=receipt_sha, database_path=database_path, permissions=permissions,
            cancel=budget.cancel, timeout_s=budget.remaining(), progress=progress)
        guard()
        execution = RegisteredRuntimeExecutionSelection(execution_id, retained.manifest_sha256,
            provenance.code, provenance.sha256, executables[godot_exe][1][0], executables[godot_main_exe][1][0],
            purpose, True)
        diagnostic = verify_registered_native_body_runtime(store, selection=selection, retention_id=retained.retention_id,
            expected_manifest_sha256=retained.manifest_sha256, database_path=database_path,
            permissions=permissions, preparation=preparation, expected_production_receipt_sha256=receipt_sha,
            execution=execution, godot_exe=godot_exe, godot_main_exe=godot_main_exe,
            cancel=budget.cancel, timeout_s=budget.remaining(), progress=progress)
        guard()
        return PreparedFirstPartyGodotAnimation(preparation, receipt_sha, retained, diagnostic, execution,
                                                 provenance, provenance_path, runtime)


def admit_first_party_godot_animation(store: ProjectStore, *, result: PreparedFirstPartyGodotAnimation,
        selection: RegisteredInputSelection, database_path: Path, permissions: tuple[EngineInputPermission, ...],
        godot_exe: Path, godot_main_exe: Path, budget: Budget, progress: Progress | None = None) -> RegisteredBodyInputs:
    """Re-admit a typed first-party result and return new consumer guards."""
    if type(result) is not PreparedFirstPartyGodotAnimation:
        raise ValidationError('A typed first-party Godot animation result is required')
    _motion_role(permissions)
    paths, provenance = _runtime_rows(budget)
    work = safe_directory(store, '.ucc-jobs')/('first-party-godot-'+result.execution.execution_id)
    if (result.provenance != provenance or result.execution.provenance_sha256 != provenance.sha256
            or result.execution.code != provenance.code or result.runtime_directory != work/'runtime'
            or result.provenance_path != work/'runtime_provenance.json'
            or result.diagnostic.execution_id != result.execution.execution_id):
        raise ValidationError('First-party Godot selection, runtime provenance or owned locators differ')
    diagnostic_receipt = result.diagnostic.directory/'diagnostic_receipt.json'
    if result.diagnostic.directory != work.parent/('registered-body300-'+result.execution.execution_id):
        raise ValidationError('First-party Godot diagnostic locator differs from its owned execution')
    inputs = admit_body_inputs(store, selection=selection, retention_id=result.retained.retention_id,
        expected_manifest_sha256=result.retained.manifest_sha256, database_path=database_path,
        permissions=permissions, preparation=result.preparation,
        expected_production_receipt_sha256=result.production_receipt_sha256, execution=result.execution,
        godot_exe=godot_exe, godot_main_exe=godot_main_exe, budget=budget, progress=progress)

    def guard() -> None:
        _check_runtime(paths, provenance, result.provenance_path, result.runtime_directory, budget)
        if hash_file(diagnostic_receipt, 4 * 1024 * 1024, budget)[0] != result.diagnostic.receipt_sha256:
            raise ProjectStorageError('First-party Godot diagnostic receipt changed')
        inputs.guard()

    guard()
    return RegisteredBodyInputs(inputs.files, inputs.records, inputs.references, guard)
