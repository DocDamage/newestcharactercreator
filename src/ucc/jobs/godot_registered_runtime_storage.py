"""Atomic private registered-input retention and explicit current-context reload.

Rename commits private data only. Postcommit failure retains a historical record
and reports its identity. Nothing is adopted, run, delivered or published.
"""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from ucc.core.errors import ProjectStorageError
from ucc.core.storage import _lock, ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_native_producer import PreparedRegisteredNativeSource
from ucc.core.target_action_format import checked_sha, checked_uuid
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_runtime_contract import (NAMESPACE,
    PAYLOAD_FILES, MAX_MANIFEST_BYTES, RetainedInputFile, RegisteredRuntimeManifest)
from .target_action_context import operation_budget, protected
from .target_action_storage import ancestry
from .expression_storage import safe_directory
from .export_destination import rename_new
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import hash_file, copy_file, seal, read_bytes, check_seal_identities
from .godot_registered_runtime_admission import (current_inputs, preparation_paths,
    validate_graph, proof_references, permission_bytes, watch_preparation)


@dataclass(frozen=True, slots=True)
class RetainedRegisteredNativeInputs:
    directory: Path
    retention_id: str
    manifest_sha256: str
    project_id: str
    revision: int
    target_action_binding_sha256: str

    @property
    def runtime_execution_verified(self) -> bool:
        return False

    @property
    def engine_import_verified(self) -> bool:
        return False


def _result(directory,manifest):
    return RetainedRegisteredNativeInputs(directory,manifest.retention_id,manifest.sha256,
        manifest.selection.project_id,manifest.selection.revision,manifest.selection.binding_sha256)


def _metadata_records(paths,request,budget):
    records=[]
    for name in sorted(PAYLOAD_FILES):
        if name==".gdignore":
            from hashlib import sha256
            records.append(RetainedInputFile(name,sha256(b"").hexdigest(),0));continue
        from ucc.export.godot_registered_runtime_contract import file_limit
        digest,size=hash_file(paths[name],file_limit(name),budget)
        if name in dict(request.files) and digest!=dict(request.files)[name]:
            raise ProjectStorageError("Registered runtime bytes changed after source admission")
        records.append(RetainedInputFile(name,digest,size))
    return tuple(records)


def _check_manifest_context(manifest,context,receipt_sha,permissions):
    if (manifest.selection!=context.selection or manifest.source_receipt_sha256!=receipt_sha
            or manifest.proofs!=proof_references(context.binding)
            or permission_bytes(manifest.permissions)!=permission_bytes(permissions)):
        raise ProjectStorageError("Retained manifest differs from current explicit context/permissions")


def _load_directory(directory,manifest,context,permissions,budget,*,expected_seal=None):
    _check_manifest_context(manifest,context,manifest.source_receipt_sha256,permissions)
    before=seal(directory,manifest,budget)
    if expected_seal is not None and before!=expected_seal:
        raise ProjectStorageError("Private committed candidate differs from its owned staging identity")
    paths={name:directory/name for name in PAYLOAD_FILES if name!=".gdignore"}
    recipe,receipt,request,hashes=validate_graph(paths,context,manifest.source_receipt_sha256,
        permissions,budget,anchors=None,check_source_outputs=False)
    if (manifest.recipe_sha256!=hashes["native_recipe.json"]
            or manifest.runtime_request_sha256!=request.sha256
            or manifest.stage_job_id!=receipt["stage_job_id"] or manifest.reopen_job_id!=receipt["reopen_job_id"]):
        raise ProjectStorageError("Retained source anchors changed")
    context.guard()
    if seal(directory,manifest,budget)!=before:
        raise ProjectStorageError("Retained candidate identities changed during loading")
    context.guard()
    check_seal_identities(directory,before,budget)
    return _result(directory,manifest)


def _raise_io(error):
    wrapped=ProjectStorageError("Registered private-input IO failed: "+str(error))
    for note in getattr(error,"__notes__",()):wrapped.add_note(note)
    raise wrapped from error


def retain_registered_native_inputs(store: ProjectStore, *, selection: RegisteredInputSelection,
        preparation: PreparedRegisteredNativeSource, expected_production_receipt_sha256: str,
        database_path: Path, permissions: tuple[EngineInputPermission,...], cancel: Event | None=None,
        timeout_s: float=300, progress: Callable[[str],None] | None=None) -> RetainedRegisteredNativeInputs:
    """Consume an actual V2 preparation; no Blender/native/runtime jobs are run."""
    try:
        with operation_budget(cancel,timeout_s) as budget:
            return _retain(store,selection,preparation,expected_production_receipt_sha256,
                database_path,permissions,budget,progress)
    except OSError as error:_raise_io(error)


def _retain(store,selection,preparation,receipt_sha,database_path,permissions,budget,progress):
    checked_sha(receipt_sha)
    context=current_inputs(store,selection,database_path,permissions,budget,progress)
    paths=preparation_paths(store,preparation)
    recipe,receipt,request,hashes=validate_graph(paths,context,receipt_sha,permissions,budget,
        anchors=preparation,check_source_outputs=True)
    original_guard=watch_preparation(preparation,recipe,receipt,hashes,budget)
    records=_metadata_records(paths,request,budget)
    manifest=RegisteredRuntimeManifest(str(uuid4()),selection,receipt_sha,
        hashes["native_recipe.json"],request.sha256,receipt["stage_job_id"],receipt["reopen_job_id"],
        records,proof_references(context.binding),permissions)
    _check_manifest_context(manifest,context,receipt_sha,permissions)
    sources_before={name:identity(protected(path)) for name,path in paths.items()}
    source_authority=ancestry(paths.values())
    jobs=safe_directory(store,".ucc-jobs",create=True)
    work=jobs/("registered-runtime-retention-"+manifest.retention_id)
    work.mkdir(exist_ok=False);staging=work/"inputs";staging.mkdir()
    work_stamp=identity(work);jobs_stamp=identity(jobs);staging_stamp=identity(staging)
    committed=None
    def guard_work():
        budget.check()
        if identity(protected(work))!=work_stamp or identity(protected(jobs))!=jobs_stamp:
            raise ProjectStorageError("Private retention job directory changed")
        if committed is None and identity(protected(staging))!=staging_stamp:
            raise ProjectStorageError("Private retention staging directory changed")
    def guard_source():
        guard_work();context.guard();original_guard()
        for path,stamp in source_authority.items():
            if identity(protected(path))!=stamp:
                raise ProjectStorageError("Completed source preparation ancestry changed")
        for name,path in paths.items():
            if identity(protected(path))!=sources_before[name]:
                raise ProjectStorageError("Completed source preparation input was replaced")
        for row in records:
            if row.name!=".gdignore" and hash_file(paths[row.name],row.bytes,budget)!=(row.sha256,row.bytes):
                raise ProjectStorageError("Completed source preparation bytes changed")
    try:
        guard_source()
        if progress:progress("COPY_PRIVATE_REGISTERED_INPUTS")
        for record in records:
            guard_work()
            if record.name==".gdignore":
                with (staging/record.name).open("xb"):pass
            else:copy_file(paths[record.name],staging/record.name,record,budget)
            guard_work()
        with (staging/"manifest.json").open("xb") as stream:
            stream.write(canonical_bytes(manifest.to_dict()));stream.flush()
            import os
            os.fsync(stream.fileno())
        staged_seal=seal(staging,manifest,budget)
        _load_directory(staging,manifest,context,permissions,budget)
        guard_source()
        root=safe_directory(store,".ucc-candidates",NAMESPACE,create=True)
        root_stamp=identity(root);parent_stamp=identity(root.parent)
        destination=root/manifest.retention_id
        if progress:progress("COMMIT_PRIVATE_REGISTERED_INPUTS")
        with _lock(store.root/".project.ucc.lock",timeout_s=min(3,max(.001,budget.remaining()))):
            guard_source()
            if identity(protected(root))!=root_stamp or identity(protected(root.parent))!=parent_stamp:
                raise ProjectStorageError("Private candidate parent was replaced")
            if seal(staging,manifest,budget)!=staged_seal:
                raise ProjectStorageError("Private staging payload changed before commit")
            if destination.exists() or destination.is_symlink():
                raise ProjectStorageError("Earlier private inputs occupy this retention identity")
            budget.check();rename_new(staging,destination)
            committed=destination
        # The immutable private data commit is complete. Later failures preserve
        # the historical record and report its path; never roll back a foreign path.
        if progress:progress("PRIVATE_INPUTS_COMMITTED")
        guard_source()
        result=_load_directory(destination,manifest,context,permissions,budget,expected_seal=staged_seal)
        guard_source()
        if seal(destination,manifest,budget)!=staged_seal:
            raise ProjectStorageError("Private committed input bytes changed before return")
        guard_source()
        check_seal_identities(destination,staged_seal,budget)
        if identity(protected(root))!=root_stamp or identity(protected(root.parent))!=parent_stamp:
            raise ProjectStorageError("Private candidate ancestry changed after commit")
        budget.check()
        return result
    except BaseException as error:
        if committed is not None:
            error.add_note("Private registered-input commit completed at "+str(committed)
                           +"; manifest SHA "+manifest.sha256
                           +"; current loading failed; inspect the historical record because filesystem state may have changed")
        raise


def load_registered_native_inputs(store: ProjectStore, *, selection: RegisteredInputSelection,
        retention_id: str, expected_manifest_sha256: str, database_path: Path,
        permissions: tuple[EngineInputPermission,...], cancel: Event | None=None,
        timeout_s: float=300, progress: Callable[[str],None] | None=None) -> RetainedRegisteredNativeInputs:
    """Explicit current-context read-only restart load; no jobs, adoption or run."""
    checked_uuid(retention_id);checked_sha(expected_manifest_sha256)
    try:
        with operation_budget(cancel,timeout_s) as budget:
            root=safe_directory(store,".ucc-candidates",NAMESPACE)
            directory=protected(root/retention_id)
            root_state=(identity(root),identity(root.parent),identity(directory))
            raw,_=read_bytes(directory/"manifest.json",MAX_MANIFEST_BYTES,budget,
                             expected_sha256=expected_manifest_sha256)
            manifest=RegisteredRuntimeManifest.from_bytes(raw)
            if manifest.retention_id!=retention_id or manifest.selection!=selection:
                raise ProjectStorageError("Selected private candidate belongs to a different context")
            context=current_inputs(store,selection,database_path,permissions,budget,progress)
            result=_load_directory(directory,manifest,context,permissions,budget)
            if root_state!=(identity(protected(root)),identity(protected(root.parent)),identity(protected(directory))):
                raise ProjectStorageError("Private candidate ancestry changed during loading")
            budget.check()
            return result
    except OSError as error:_raise_io(error)
