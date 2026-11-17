"""Guarded actual Godot body300 diagnostic; no publication, adoption or shipping."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Callable
import os
import stat
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission,canonical_bytes
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection,POLICY,PROFILE,FALSE_FLAGS
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_native_producer import PreparedRegisteredNativeSource
from .godot_registered_body_inputs import admit_body_inputs
from .godot_registered_body_references import convert_reference,verify_body_outputs,verify_import_configuration
from .godot_registered_runtime_files import copy_file,hash_file,read_bytes,FileIdentity
from .target_action_context import operation_budget,protected
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .runner import run_process,WorkerFailure
from .export_destination import rename_new


@dataclass(frozen=True,slots=True)
class VerifiedRegisteredNativeBodyDiagnostic:
    directory:Path
    execution_id:str
    receipt_sha256:str

    @property
    def engine_import_verified(self)->bool:return False


@dataclass(frozen=True,slots=True)
class _CopyRecord:
    sha256:str
    bytes:int


def _generated_project(path:Path,record:dict,budget,expected:FileIdentity|None=None)->FileIdentity:
    """Exact generated settings; only an owned successful editor may replace it."""
    before=identity(protected(path));info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or expected is not None and before!=expected:
        raise ProjectStorageError("Generated project configuration ownership changed")
    raw,_=read_bytes(path,record['bytes'],budget,expected_sha256=record['sha256'])
    after=identity(protected(path));info=path.stat()
    if (after!=before or len(raw)!=record['bytes'] or b'\r' in raw
            or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or identity(protected(path))!=after):
        raise ProjectStorageError("Generated project configuration changed while admitting bytes")
    return after


def verify_registered_native_body_runtime(store:ProjectStore,*,selection:RegisteredInputSelection,
        retention_id:str,expected_manifest_sha256:str,database_path:Path,
        permissions:tuple[EngineInputPermission,...],preparation:PreparedRegisteredNativeSource,
        expected_production_receipt_sha256:str,execution:RegisteredRuntimeExecutionSelection,
        godot_exe:Path,godot_main_exe:Path,cancel:Event|None=None,timeout_s:float=1800,
        progress:Callable[[str],None]|None=None)->VerifiedRegisteredNativeBodyDiagnostic:
    """Caller explicitly selects local private code. No code sandbox is implied."""
    try:
        with operation_budget(cancel,timeout_s) as budget:
            godot_exe=protected(Path(godot_exe))
            godot_main_exe=protected(Path(godot_main_exe))
            inputs=admit_body_inputs(store,selection=selection,retention_id=retention_id,
                expected_manifest_sha256=expected_manifest_sha256,database_path=database_path,permissions=permissions,
                preparation=preparation,expected_production_receipt_sha256=expected_production_receipt_sha256,
                execution=execution,godot_exe=godot_exe,godot_main_exe=godot_main_exe,budget=budget,progress=progress)
            jobs=safe_directory(store,'.ucc-jobs')
            work=jobs/('registered-body300-'+execution.execution_id)
            work.mkdir(exist_ok=False);engine=work/'engine';engine.mkdir()
            ownership={path:identity(path) for path in (jobs,work,engine)}
            def guard()->None:
                budget.check()
                for path,stamp in ownership.items():
                    if identity(protected(path))!=stamp:raise ProjectStorageError("Owned body300 work directory replaced")
                inputs.guard()
            guard()
            if progress:progress('STAGE_REGISTERED_BODY300')
            staged={}
            for name,path in inputs.files.items():
                guard();record=inputs.records[name]
                # Metadata names are not runtime payload names; copy them through
                # the same bounded primitive without broadening V1 contracts.
                copy_file(path,engine/name,_CopyRecord(**record),budget)
                staged[name]=dict(record)
            execution_bytes=canonical_bytes(execution.to_dict())
            with (engine/'execution.json').open('xb') as stream:stream.write(execution_bytes)
            staged['execution.json']=dict(sha256=sha256(execution_bytes).hexdigest(),bytes=len(execution_bytes))
            if progress:progress('VALIDATE_REGISTERED_BODY300_REFERENCES')
            for name,(source,digest) in inputs.references.items():
                guard();normal=name=='native_normals.bin'
                destination='expected_normals_vec4.f32' if normal else 'expected_vec4.f32'
                staged[destination]=convert_reference(source,engine/destination,digest,normal=normal,budget=budget)
            guard()
            spec=dict(schema_version=1,policy=POLICY,profile=PROFILE,vertices=13380,corners=53512,
                frames=300,fps=30,execution_sha256=execution.sha256,retention_manifest_sha256=expected_manifest_sha256,
                target_action_binding_sha256=selection.binding_sha256,source_receipt_sha256=expected_production_receipt_sha256,
                plan_sha256=inputs.records['skin_plan.json']['sha256'],files={name:row['sha256'] for name,row in staged.items()})
            spec_raw=canonical_bytes(spec);spec_sha=sha256(spec_raw).hexdigest()
            with (engine/'spec.json').open('xb') as stream:stream.write(spec_raw)
            staged['spec.json']=dict(sha256=spec_sha,bytes=len(spec_raw))
            stamps={name:identity(engine/name) for name in staged}
            def immutable_staged_guard()->None:
                guard()
                for name,row in staged.items():
                    if name=='project.godot':continue
                    path=protected(engine/name)
                    if identity(path)!=stamps[name] or hash_file(path,row['bytes'],budget)!=(row['sha256'],row['bytes']):
                        raise ProjectStorageError("Body300 staged code/data/spec changed")
                guard()
            def staged_guard()->None:
                immutable_staged_guard()
                _generated_project(engine/'project.godot',staged['project.godot'],budget,stamps['project.godot'])
                guard()
                if identity(protected(engine/'project.godot'))!=stamps['project.godot']:
                    raise ProjectStorageError("Generated project configuration replaced after guard")
            def refresh_project(phase:str)->dict:
                if phase not in {'initial-import','configured-import'}:
                    raise ProjectStorageError("Configuration identity transition outside owned editor phase")
                immutable_staged_guard();previous=stamps['project.godot']
                current=_generated_project(engine/'project.godot',staged['project.godot'],budget)
                immutable_staged_guard()
                _generated_project(engine/'project.godot',staged['project.godot'],budget,current)
                stamps['project.godot']=current
                return dict(phase=phase,policy='OWNED_EDITOR_IDENTICAL_PROJECT_CONFIGURATION_V1',
                    previous_identity=list(previous),new_identity=list(current),**staged['project.godot'])
            commands=[]
            vulkan=['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000']
            phases=[('initial-import',vulkan+['--editor','--import']),
                ('configure-import',['--headless','--script','res://configure.gd']),
                ('configured-import',vulkan+['--editor','--import']),
                ('actual-body300',vulkan+['--script','res://validate.gd'])]
            for label,args in phases:
                staged_guard()
                if progress:progress('GODOT_'+label.upper().replace('-','_'))
                staged_guard()
                logdir=work/label
                if logdir.exists() or logdir.is_symlink():raise ProjectStorageError("Earlier body300 child directory exists")
                logdir.mkdir();ownership[logdir]=identity(logdir)
                command=[str(godot_exe),'--path',str(engine),*args]
                # Keep the originally owned descriptor across the child so a
                # postphase admission failure cannot erase its raw return code.
                raw_outcome=logdir/'process_outcome.json'
                with raw_outcome.open('xb') as stream:
                    opened=os.fstat(stream.fileno())
                    outcome=run_process(command,logdir,timeout_s=budget.remaining(),cancel=budget.cancel)
                    row=dict(phase=label,command=command,return_code=outcome.return_code,cancelled=outcome.cancelled,
                        timed_out=outcome.timed_out,elapsed_seconds=outcome.elapsed_seconds)
                    stream.write(canonical_bytes(row));stream.flush();os.fsync(stream.fileno())
                    if identity(protected(raw_outcome))[:2]!=(opened.st_dev,opened.st_ino):
                        raise ProjectStorageError("Owned raw child outcome replaced")
                commands.append(row)
                successful=outcome.return_code==0 and not outcome.cancelled and not outcome.timed_out
                if not successful:
                    raise WorkerFailure('Godot body300 '+label+' failed with exit code '+str(outcome.return_code)+'; logs: '+str(logdir))
                if successful and label in {'initial-import','configured-import'}:
                    row['generated_project_transition']=refresh_project(label)
                staged_guard()
                with (logdir/'outcome.json').open('xb') as stream:stream.write(canonical_bytes(row))
                if label=='configure-import':verify_import_configuration(engine,'PRE_REIMPORT',budget)
            configuration=verify_import_configuration(engine,'POST_REIMPORT',budget)
            if progress:progress('VERIFY_REGISTERED_BODY300_READBACK')
            observed=verify_body_outputs(engine,execution.sha256,spec_sha,budget,
                input_hashes={name:row['sha256'] for name,row in staged.items()})
            staged_guard()
            outputs={name:hash_file(engine/name,64*1024*1024,budget) for name in
                ('measurement.json','actual_corrected_world.f32','actual_normals_vec4.f32',
                 'imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32','import_configuration.json','character.glb.import')}
            if outputs['import_configuration.json'][0]!=configuration['report_sha256'] or outputs['character.glb.import'][0]!=configuration['import_settings_sha256']:
                raise ProjectStorageError("Parsed import configuration changed")
            if outputs['measurement.json'][0]!=observed['measurement_sha256']:
                raise ProjectStorageError("Body300 measurement changed after parsing")
            for name,row in observed['output_files'].items():
                if outputs[name]!=(row['sha256'],row['bytes']):
                    raise ProjectStorageError("Body300 output changed after independent comparison")
            output_ids={name:identity(engine/name) for name in outputs}
            def output_guard()->None:
                for name,row in outputs.items():
                    if identity(protected(engine/name))!=output_ids[name] or hash_file(engine/name,row[1],budget)!=row:
                        raise ProjectStorageError("Body300 outputs changed after validation")
            def final_identities()->None:
                for name,stamp in output_ids.items():
                    budget.check()
                    if identity(protected(engine/name))!=stamp:raise ProjectStorageError("Body300 output identity changed")
            receipt=dict(schema_version=1,policy=POLICY,profile=PROFILE,execution_sha256=execution.sha256,
                retention_manifest_sha256=expected_manifest_sha256,source_receipt_sha256=expected_production_receipt_sha256,
                target_action_binding_sha256=selection.binding_sha256,spec_sha256=spec_sha,commands=commands,
                files={name:dict(sha256=row[0],bytes=row[1]) for name,row in outputs.items()},observed=observed,
                **{name:False for name in FALSE_FLAGS})
            raw=canonical_bytes(receipt);receipt_sha=sha256(raw).hexdigest();pending=work/'receipt.pending.json'
            with pending.open('xb') as stream:
                stamp=identity(pending);stream.write(raw);stream.flush();os.fsync(stream.fileno())
                if os.fstat(stream.fileno()).st_ino!=stamp[1] or identity(protected(pending))[:2]!=stamp[:2]:
                    raise ProjectStorageError("Owned body300 receipt replaced")
            staged_guard()
            output_guard()
            staged_guard()
            final_identities()
            final=work/'diagnostic_receipt.json';rename_new(pending,final)
            try:
                staged_guard()
                output_guard()
                staged_guard()
                if hash_file(final,len(raw),budget)!=(receipt_sha,len(raw)):
                    raise ProjectStorageError("Body300 receipt changed after commit")
                staged_guard()
                final_identities()
                if identity(protected(final))[:2]!=stamp[:2]:raise ProjectStorageError("Committed diagnostic receipt replaced")
                return VerifiedRegisteredNativeBodyDiagnostic(work,execution.execution_id,receipt_sha)
            except BaseException as error:
                error.add_note('Private diagnostic receipt commit completed at '+str(final)+'; current loading not revalidated')
                raise
    except OSError as error:
        wrapped=ProjectStorageError('Registered body300 IO failed: '+str(error))
        for note in getattr(error,'__notes__',()):wrapped.add_note(note)
        raise wrapped from error
