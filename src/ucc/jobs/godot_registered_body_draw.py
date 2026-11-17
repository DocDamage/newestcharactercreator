"""Owned private debug draw of an admitted numerical diagnostic; no publication."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Callable
import os
import sys

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_registered_body_draw import RegisteredBodyDrawSelection, POLICY, PROFILE, FRAMES
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection, FALSE_FLAGS, VERTICES
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_body_target import VerifiedRegisteredNativeBodyDiagnostic
from .godot_registered_native_producer import PreparedRegisteredNativeSource
from .godot_registered_body_draw_inputs import admit_draw_inputs
from .godot_registered_body_draw_evidence import map_frame, verify_draw_outputs, read_frame_stream
from .godot_registered_runtime_files import read_bytes, hash_file
from .godot_candidate_inputs import identity
from .target_action_context import protected, operation_budget
from .expression_storage import safe_directory
from .runner import run_process, WorkerFailure
from .export_destination import rename_new


@dataclass(frozen=True, slots=True)
class VerifiedRegisteredBodyDraw:
    directory: Path
    draw_id: str
    receipt_sha256: str


def _adapter_paths() -> dict[str, Path]:
    if getattr(sys, 'frozen', False):
        raise ValidationError('Registered private body draw is not yet packaged')
    root = Path(__file__).resolve().parents[3]/'engine_adapters/godot/registered_body_draw'
    return {name: protected(root/name) for name in ('project.godot','validate.gd')}


def draw_registered_native_body(store: ProjectStore, *, selection: RegisteredInputSelection,
        retention_id: str, expected_manifest_sha256: str, database_path: Path,
        permissions: tuple[EngineInputPermission, ...], preparation: PreparedRegisteredNativeSource,
        expected_production_receipt_sha256: str, execution: RegisteredRuntimeExecutionSelection,
        diagnostic: VerifiedRegisteredNativeBodyDiagnostic, draw: RegisteredBodyDrawSelection,
        godot_exe: Path, godot_main_exe: Path, cancel: Event | None = None,
        timeout_s: float = 1800, progress: Callable[[str],None] | None = None) -> VerifiedRegisteredBodyDraw:
    """Draw three admitted frames locally; do not execute the private kernel again."""
    with operation_budget(cancel, timeout_s) as budget:
        godot_exe = protected(Path(godot_exe)); godot_main_exe = protected(Path(godot_main_exe))
        inputs = admit_draw_inputs(store, selection=selection, retention_id=retention_id,
            expected_manifest_sha256=expected_manifest_sha256, database_path=database_path,
            permissions=permissions, preparation=preparation,
            expected_production_receipt_sha256=expected_production_receipt_sha256,
            execution=execution, diagnostic=diagnostic, draw=draw,
            godot_exe=godot_exe, godot_main_exe=godot_main_exe, budget=budget, progress=progress)
        adapters = _adapter_paths()
        adapter_bytes = {name: read_bytes(path,256*1024,budget)[0] for name,path in adapters.items()}
        adapter_ids = {name: identity(path) for name,path in adapters.items()}
        jobs = safe_directory(store,'.ucc-jobs')
        work = jobs/('registered-body-draw-'+draw.draw_id)
        work.mkdir(exist_ok=False); engine = work/'engine'; engine.mkdir()
        ownership = {path:identity(path) for path in (jobs,work,engine)}
        staged = {}
        stamps = {}
        def guard() -> None:
            budget.check(); inputs.guard()
            for path,stamp in ownership.items():
                if identity(protected(path)) != stamp:
                    raise ProjectStorageError('Private body draw work directory replaced')
            for name,path in adapters.items():
                raw,_ = read_bytes(path,256*1024,budget)
                if identity(path) != adapter_ids[name] or raw != adapter_bytes[name]:
                    raise ProjectStorageError('Private body draw adapter changed')
            for name,stamp in stamps.items():
                if identity(protected(engine/name)) != stamp or (engine/name).stat().st_nlink != 1:
                    raise ProjectStorageError('Private draw staged input identity changed')
        def write(name: str, raw: bytes) -> None:
            guard()
            path = engine/name
            with path.open('xb') as stream:
                opened = os.fstat(stream.fileno())
                if identity(protected(path))[:2] != (opened.st_dev,opened.st_ino) or opened.st_nlink != 1:
                    raise ProjectStorageError('Private draw staged writer ownership changed')
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                closed = os.fstat(stream.fileno())
                stamp = (closed.st_dev,closed.st_ino,closed.st_size,closed.st_mtime_ns)
                if ((opened.st_dev,opened.st_ino) != stamp[:2] or closed.st_nlink != 1
                        or closed.st_size != len(raw) or identity(protected(path)) != stamp
                        or path.stat().st_nlink != 1):
                    raise ProjectStorageError('Private draw staged writer replaced or linked')
            row = dict(sha256=sha256(raw).hexdigest(),bytes=len(raw))
            if hash_file(path,len(raw),budget) != (row['sha256'],len(raw)) or identity(protected(path)) != stamp:
                raise ProjectStorageError('Private draw written bytes changed')
            staged[name] = row; stamps[name] = stamp
            guard()
        if progress: progress('STAGE_REGISTERED_BODY_DRAW')
        arrays = {}
        for name in ('imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32'):
            row = inputs.records[name]
            arrays[name],_ = read_bytes(inputs.directory/name,row['bytes'],budget,expected_sha256=row['sha256'])
        streams = {}
        for name in ('actual_corrected_world.f32','actual_normals_vec4.f32'):
            guard()
            streams[name] = read_frame_stream(inputs.directory/name,
                inputs.records[name]['sha256'],budget)
            guard()
        for frame in FRAMES:
            guard()
            mapped = map_frame(streams['actual_corrected_world.f32'][frame],
                streams['actual_normals_vec4.f32'][frame], arrays['imported_uv_source_ids.u32'],
                arrays['imported_uv.f32'], arrays['imported_uv_triangles.u32'],check=budget.check)
            write(f'frame{frame:03d}_positions.f32',mapped['positions'])
            write(f'frame{frame:03d}_normals.f32',mapped['normals'])
        write('imported_uv.f32',arrays['imported_uv.f32'])
        write('imported_uv_triangles.u32',arrays['imported_uv_triangles.u32'])
        data_hashes = {name:row['sha256'] for name,row in staged.items()}
        write('selection.json',canonical_bytes(draw.to_dict()))
        for name,raw in adapter_bytes.items(): write(name,raw)
        spec = dict(schema_version=1,profile=PROFILE,selection_sha256=draw.sha256,
                    diagnostic_receipt_sha256=draw.diagnostic_receipt_sha256,
                    files={name:row['sha256'] for name,row in staged.items()})
        raw = canonical_bytes(spec); spec_sha = sha256(raw).hexdigest(); write('spec.json',raw)
        def staged_guard() -> None:
            guard()
            for name,row in staged.items():
                if identity(protected(engine/name)) != stamps[name] or hash_file(engine/name,row['bytes'],budget) != (row['sha256'],row['bytes']):
                    raise ProjectStorageError('Private draw staged input changed')
            guard()
        staged_guard()
        if progress: progress('GODOT_REGISTERED_BODY_DRAW')
        logs = work/'draw'; logs.mkdir(); ownership[logs] = identity(logs)
        command = [str(godot_exe),'--path',str(engine),'--rendering-method','mobile',
                   '--rendering-driver','vulkan','--position','-32000,-32000','--script','res://validate.gd']
        with (logs/'process_outcome.json').open('xb') as stream:
            descriptor = os.fstat(stream.fileno())
            outcome = run_process(command,logs,timeout_s=budget.remaining(),cancel=budget.cancel)
            row = dict(command=command,return_code=outcome.return_code,cancelled=outcome.cancelled,
                       timed_out=outcome.timed_out,elapsed_seconds=outcome.elapsed_seconds)
            stream.write(canonical_bytes(row)); stream.flush(); os.fsync(stream.fileno())
            if identity(protected(logs/'process_outcome.json'))[:2] != (descriptor.st_dev,descriptor.st_ino):
                raise ProjectStorageError('Private draw raw outcome replaced')
        if outcome.return_code != 0 or outcome.cancelled or outcome.timed_out:
            raise WorkerFailure('Godot private body draw failed with exit code '+str(outcome.return_code)+'; logs: '+str(logs))
        staged_guard()
        if progress: progress('VERIFY_REGISTERED_BODY_DRAW')
        observed = verify_draw_outputs(engine,spec_sha,data_hashes,budget)
        staged_guard()
        outputs = {'measurement.json':dict(sha256=observed['measurement_sha256'],bytes=(engine/'measurement.json').stat().st_size),
                   **observed['files']}
        output_ids = {name:identity(protected(engine/name)) for name in outputs}
        def final_identities() -> None:
            budget.check()
            for path,stamp in ownership.items():
                if identity(protected(path)) != stamp:
                    raise ProjectStorageError('Private draw work namespace changed')
            for name,stamp in {**stamps,**output_ids}.items():
                if identity(protected(engine/name)) != stamp or (engine/name).stat().st_nlink != 1:
                    raise ProjectStorageError('Private draw final file ownership changed')
        def output_guard() -> None:
            for name,value in outputs.items():
                if identity(protected(engine/name)) != output_ids[name] or hash_file(engine/name,value['bytes'],budget) != (value['sha256'],value['bytes']):
                    raise ProjectStorageError('Private draw evidence changed after validation')
        receipt = dict(schema_version=1,policy=POLICY,profile=PROFILE,selection_sha256=draw.sha256,
            diagnostic_receipt_sha256=draw.diagnostic_receipt_sha256,spec_sha256=spec_sha,
            command=row,observed=observed,**{name:False for name in FALSE_FLAGS})
        raw = canonical_bytes(receipt); digest = sha256(raw).hexdigest()
        pending = work/'receipt.pending.json'
        with pending.open('xb') as stream:
            opened = os.fstat(stream.fileno())
            if identity(protected(pending))[:2] != (opened.st_dev,opened.st_ino) or opened.st_nlink != 1:
                raise ProjectStorageError('Private draw pending receipt writer replaced')
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            finished = os.fstat(stream.fileno())
            stamp = (finished.st_dev,finished.st_ino,finished.st_size,finished.st_mtime_ns)
            if ((opened.st_dev,opened.st_ino) != stamp[:2] or finished.st_nlink != 1
                    or finished.st_size != len(raw) or identity(protected(pending)) != stamp
                    or pending.stat().st_nlink != 1):
                raise ProjectStorageError('Private draw pending receipt replaced or linked')
        staged_guard(); output_guard(); staged_guard(); final_identities()
        if identity(protected(pending)) != stamp or pending.stat().st_nlink != 1:
            raise ProjectStorageError('Private draw pending receipt ownership changed before commit')
        final = work/'diagnostic_draw_receipt.json'; rename_new(pending,final)
        try:
            staged_guard(); output_guard(); staged_guard()
            if identity(protected(final)) != stamp or final.stat().st_nlink != 1 or hash_file(final,len(raw),budget) != (digest,len(raw)):
                raise ProjectStorageError('Private draw receipt changed after commit')
            final_identities()
            if identity(protected(final)) != stamp or final.stat().st_nlink != 1:
                raise ProjectStorageError('Private draw final receipt ownership changed')
            return VerifiedRegisteredBodyDraw(work,draw.draw_id,digest)
        except BaseException as error:
            error.add_note('Private draw receipt committed at '+str(final)+'; current loading not revalidated')
            raise
