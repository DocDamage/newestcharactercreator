"""Actual saved-source and private code admission for the body300 consumer."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import sqlite3
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.core.worker_payload import REGISTERED_BODY_FILES
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection,REFERENCE_BYTES
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection,RegisteredRuntimeManifest,MAX_MANIFEST_BYTES
from ucc.export.godot_runtime_contract import FILES
from .godot_registered_native_producer import PreparedRegisteredNativeSource
from .godot_registered_runtime_admission import current_inputs,preparation_paths,validate_graph,watch_preparation
from .godot_registered_runtime_storage import load_registered_native_inputs
from .godot_registered_runtime_files import read_bytes,hash_file,seal,check_seal_identities
from .godot_candidate_inputs import identity
from .target_action_context import Budget,protected
from .target_action_storage import ancestry
from .worker_resources import bundled_registered_body_paths

SCRIPTS = REGISTERED_BODY_FILES


def _current_guard(check:Callable[[],None],budget:Budget)->None:
    """Retry one interrupted metadata transaction, never a rejected policy."""
    for attempt in range(2):
        budget.check()
        try:
            check()
        except ProjectStorageError as error:
            cause=error.__cause__
            if (attempt or not isinstance(cause,sqlite3.OperationalError)
                    or getattr(cause,'sqlite_errorcode',None)!=sqlite3.SQLITE_INTERRUPT):
                raise
        else:
            budget.check()
            return


@dataclass(frozen=True,slots=True)
class RegisteredBodyInputs:
    files:dict[str,Path]
    records:dict[str,dict]
    references:dict[str,tuple[Path,str]]
    guard:Callable[[],None]


def body_adapter_paths()->dict[str,Path]:
    return {name: protected(path) for name, path in bundled_registered_body_paths().items()}


def admit_body_inputs(store:ProjectStore,*,selection:RegisteredInputSelection,retention_id:str,
        expected_manifest_sha256:str,database_path:Path,permissions:tuple[EngineInputPermission,...],
        preparation:PreparedRegisteredNativeSource,expected_production_receipt_sha256:str,
        execution:RegisteredRuntimeExecutionSelection,godot_exe:Path,godot_main_exe:Path,
        budget:Budget,progress:Callable[[str],None]|None=None)->RegisteredBodyInputs:
    if type(preparation) is not PreparedRegisteredNativeSource:
        raise ValidationError("Body300 requires the typed actual prepared source locator")
    if type(execution) is not RegisteredRuntimeExecutionSelection or execution.retention_manifest_sha256!=expected_manifest_sha256:
        raise ValidationError("Require explicit execution selection bound to this retained candidate")
    retained=load_registered_native_inputs(store,selection=selection,retention_id=retention_id,
        expected_manifest_sha256=expected_manifest_sha256,database_path=database_path,permissions=permissions,
        cancel=budget.cancel,timeout_s=min(300,budget.remaining()),progress=progress)
    raw,_=read_bytes(retained.directory/'manifest.json',MAX_MANIFEST_BYTES,budget,expected_sha256=expected_manifest_sha256)
    manifest=RegisteredRuntimeManifest.from_bytes(raw)
    if manifest.source_receipt_sha256!=expected_production_receipt_sha256:
        raise ValidationError("Body300 preparation belongs to a different source receipt")
    candidate_seal=seal(retained.directory,manifest,budget)
    context=current_inputs(store,selection,database_path,permissions,budget,progress)
    if execution.execution_id in {*context.binding.producer.worker_job_ids,preparation.stage_job_id,preparation.reopen_job_id}:
        raise ValidationError("Execution identity must differ from historical source/proof workers")
    paths=preparation_paths(store,preparation)
    recipe,receipt,request,hashes=validate_graph(paths,context,expected_production_receipt_sha256,
        permissions,budget,anchors=preparation,check_source_outputs=True)
    original_guard=watch_preparation(preparation,recipe,receipt,hashes,budget)
    selected={row.name:dict(sha256=row.sha256,bytes=row.bytes) for row in execution.code}
    if (selected!={name:dict(sha256=recipe['implementation'][name],bytes=recipe['runtime_code_lengths'][name]) for name in recipe['implementation']}
            or execution.provenance_sha256!=recipe['runtime_code_provenance_sha256']
            or manifest.stage_job_id!=preparation.stage_job_id or manifest.reopen_job_id!=preparation.reopen_job_id):
        raise ValidationError("Execution code/provenance/source workers differ from actual prepared inputs")
    from .godot_registered_runtime_files import read_metadata
    stage,_,_=read_metadata(paths['native_stage.json'],4*1024*1024,budget,expected_sha256=receipt['native_stage_sha256'])
    references={name:(preparation.directory/name,stage['files'][name]['sha256'])
        for name in ('native_positions.bin','native_normals.bin')}
    for name,(path,digest) in references.items():
        if stage['files'][name]['bytes']!=REFERENCE_BYTES or hash_file(path,REFERENCE_BYTES,budget)!=(digest,REFERENCE_BYTES):
            raise ValidationError("Actual body300 source reference bytes differ")
    files={name:retained.directory/name for name in FILES}
    files.update(body_adapter_paths())
    files.update({'runtime_request.json':retained.directory/'runtime_request.json',
                  'source_receipt.json':retained.directory/'source_receipt.json'})
    exe=protected(Path(godot_exe));main=protected(Path(godot_main_exe))
    if exe.parent!=main.parent or exe==main:
        raise ValidationError("Select the installed Godot4.7.1 console and matching main executable pair")
    external={exe:execution.godot_executable_sha256,main:execution.godot_main_sha256}
    records={}
    for name,path in files.items():
        maximum=256*1024 if name in SCRIPTS else 512*1024*1024
        digest,size=hash_file(path,maximum,budget)
        if size<1:raise ValidationError("Empty body300 input")
        records[name]=dict(sha256=digest,bytes=size)
    expected={path:(records[name]['sha256'],records[name]['bytes']) for name,path in files.items()}
    for path,digest in external.items():
        record=hash_file(path,512*1024*1024,budget)
        if record[0]!=digest:raise ValidationError("Selected Godot executable identity differs")
        expected[path]=record
    watched={path:(identity(path),record) for path,record in expected.items()}
    authority=ancestry(watched)
    def guard()->None:
        budget.check();_current_guard(context.guard,budget);original_guard()
        if seal(retained.directory,manifest,budget)!=candidate_seal:raise ProjectStorageError("Selected retained candidate changed during execution")
        for path,stamp in authority.items():
            if identity(protected(path))!=stamp:raise ProjectStorageError("Body300 selected input ancestry changed")
        for path,(stamp,record) in watched.items():
            if identity(protected(path))!=stamp or hash_file(path,record[1],budget)!=record:
                raise ProjectStorageError("Body300 code/engine/input changed")
        _current_guard(context.guard,budget);check_seal_identities(retained.directory,candidate_seal,budget)
    guard()
    return RegisteredBodyInputs(files,records,references,guard)
