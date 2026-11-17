"""Re-admit a completed private body diagnostic without executing its code."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import struct

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_registered_body_draw import RegisteredBodyDrawSelection
from ucc.export.godot_registered_body_runtime import (
    RegisteredRuntimeExecutionSelection, FALSE_FLAGS, POLICY, PROFILE, VERTICES, FRAMES)
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from .godot_registered_body_inputs import admit_body_inputs
from .godot_registered_body_references import verify_body_outputs, verify_import_configuration
from .godot_registered_body_target import VerifiedRegisteredNativeBodyDiagnostic
from .godot_registered_native_producer import PreparedRegisteredNativeSource
from .godot_registered_runtime_files import read_bytes, read_metadata, hash_file
from .godot_candidate_inputs import identity
from .target_action_context import Budget, protected
from .target_action_storage import ancestry
from .expression_storage import safe_directory


@dataclass(frozen=True, slots=True)
class BodyDrawInputs:
    directory: Path
    records: dict[str, dict]
    guard: Callable[[], None]


def _source_reference(source: Path, converted: Path, normal: bool, budget: Budget, *,
        source_sha256: str, converted_sha256: str, frames: int = FRAMES,
        vertices: int = VERTICES) -> None:
    """Compare AND hash the same complete captured source/expanded streams."""
    from hashlib import sha256
    import os
    import stat
    from ucc.core.target_action_format import checked_sha
    checked_sha(source_sha256); checked_sha(converted_sha256)
    if (type(frames) is not int or not 1 <= frames <= FRAMES
            or type(vertices) is not int or not 1 <= vertices <= VERTICES
            or type(normal) is not bool):
        raise ValidationError('Unsupported bounded source reference profile')
    source=protected(Path(source)); converted=protected(Path(converted)); budget.check()
    def stamp(value):
        return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,
                value.st_nlink)
    before=[path.stat() for path in (source,converted)]
    for value,width in zip(before,(12,16)):
        if not stat.S_ISREG(value.st_mode) or value.st_nlink!=1 or value.st_size!=frames*vertices*width:
            raise ProjectStorageError('Original body reference length or ownership differs')
    digests=[sha256(),sha256()]
    with source.open('rb') as original, converted.open('rb') as expanded:
        opened=[os.fstat(stream.fileno()) for stream in (original,expanded)]
        if [stamp(value) for value in before]!=[stamp(value) for value in opened]:
            raise ProjectStorageError('Original body references replaced before read')
        for _ in range(frames):
            budget.check(); raw=original.read(vertices*12); actual=expanded.read(vertices*16)
            if len(raw)!=vertices*12 or len(actual)!=vertices*16:
                raise ValidationError('Incomplete original body reference')
            digests[0].update(raw); digests[1].update(actual)
            expected=b''.join(struct.pack('<4f',*point,0. if normal else 1.)
                              for point in struct.iter_unpack('<3f',raw))
            if actual!=expected:
                raise ValidationError('Diagnostic reference differs from actual producer bytes')
        if original.read(1) or expanded.read(1):
            raise ValidationError('Trailing original body reference')
        finished=[os.fstat(stream.fileno()) for stream in (original,expanded)]
    after=[protected(path).stat() for path in (source,converted)]; budget.check()
    if (any(stamp(a)!=stamp(b) or stamp(b)!=stamp(c) or stamp(c)!=stamp(d)
            or a.st_ctime_ns!=d.st_ctime_ns or b.st_ctime_ns!=c.st_ctime_ns
            for a,b,c,d in zip(before,opened,finished,after))
            or [digest.hexdigest() for digest in digests]!=[source_sha256,converted_sha256]):
        raise ProjectStorageError('Captured original body reference differs from selected SHA/identity')


def admit_draw_inputs(store: ProjectStore, *, selection: RegisteredInputSelection,
        retention_id: str, expected_manifest_sha256: str, database_path: Path,
        permissions: tuple[EngineInputPermission, ...], preparation: PreparedRegisteredNativeSource,
        expected_production_receipt_sha256: str, execution: RegisteredRuntimeExecutionSelection,
        diagnostic: VerifiedRegisteredNativeBodyDiagnostic, draw: RegisteredBodyDrawSelection,
        godot_exe: Path, godot_main_exe: Path, budget: Budget, progress=None) -> BodyDrawInputs:
    if (type(draw) is not RegisteredBodyDrawSelection
            or type(diagnostic) is not VerifiedRegisteredNativeBodyDiagnostic
            or type(execution) is not RegisteredRuntimeExecutionSelection):
        raise ValidationError('Select typed private draw and completed body diagnostic')
    if (draw.diagnostic_receipt_sha256 != diagnostic.receipt_sha256
            or diagnostic.execution_id != execution.execution_id
            or draw.draw_id == execution.execution_id
            or draw.godot_executable_sha256 != execution.godot_executable_sha256
            or draw.godot_main_sha256 != execution.godot_main_sha256):
        raise ValidationError('Private draw differs from selected body diagnostic or engine')
    current = admit_body_inputs(store, selection=selection, retention_id=retention_id,
        expected_manifest_sha256=expected_manifest_sha256, database_path=database_path,
        permissions=permissions, preparation=preparation,
        expected_production_receipt_sha256=expected_production_receipt_sha256,
        execution=execution, godot_exe=godot_exe, godot_main_exe=godot_main_exe,
        budget=budget, progress=progress)
    # The accepted C job is read-only and may belong to an earlier project copy.
    # Current graph/retention/source admission above binds its content lineage;
    # a new draw job must never be appended inside that immutable evidence case.
    work = protected(Path(diagnostic.directory))
    if work.name != 'registered-body300-' + execution.execution_id or work.parent.name != '.ucc-jobs':
        raise ValidationError('Body diagnostic locator is outside its selected job namespace')
    folder = protected(work / 'engine')
    original_authority = ancestry((folder, work))
    receipt, raw, _ = read_metadata(work / 'diagnostic_receipt.json', 4*1024*1024,
                                    budget, expected_sha256=draw.diagnostic_receipt_sha256)
    keys = {'schema_version','policy','profile','execution_sha256','retention_manifest_sha256',
            'source_receipt_sha256','target_action_binding_sha256','spec_sha256','commands','files','observed'} | FALSE_FLAGS
    if (set(receipt) != keys or type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
            or receipt['policy'] != POLICY or receipt['profile'] != PROFILE
            or receipt['execution_sha256'] != execution.sha256
            or receipt['retention_manifest_sha256'] != expected_manifest_sha256
            or receipt['source_receipt_sha256'] != expected_production_receipt_sha256
            or receipt['target_action_binding_sha256'] != selection.binding_sha256
            or any(receipt[name] is not False for name in FALSE_FLAGS)
            or canonical_bytes(receipt) != raw):
        raise ValidationError('Body diagnostic receipt lineage or readiness changed')
    spec, _, _ = read_metadata(folder/'spec.json', 256*1024, budget, expected_sha256=receipt['spec_sha256'])
    spec_keys = {'schema_version','policy','profile','vertices','corners','frames','fps',
                 'execution_sha256','retention_manifest_sha256','target_action_binding_sha256',
                 'source_receipt_sha256','plan_sha256','files'}
    if (set(spec) != spec_keys or type(spec.get('schema_version')) is not int or spec['schema_version'] != 1
            or spec.get('policy') != POLICY or spec.get('profile') != PROFILE
            or any(type(spec.get(key)) is not int or spec[key] != value
                   for key,value in (('vertices',13380),('corners',53512),('frames',300),('fps',30)))
            or type(spec.get('files')) is not dict
            or set(spec['files']) != set(current.records) | {'execution.json','expected_vec4.f32','expected_normals_vec4.f32'}
            or spec.get('plan_sha256') != current.records['skin_plan.json']['sha256']
            or spec.get('execution_sha256') != execution.sha256
            or spec.get('retention_manifest_sha256') != expected_manifest_sha256
            or spec.get('source_receipt_sha256') != expected_production_receipt_sha256
            or spec.get('target_action_binding_sha256') != selection.binding_sha256):
        raise ValidationError('Body diagnostic specification lineage changed')
    phases = ('initial-import','configure-import','configured-import','actual-body300')
    commands = receipt['commands']
    if type(commands) is not list or len(commands) != len(phases):
        raise ValidationError('Incomplete body diagnostic child evidence')
    for index,(phase,row) in enumerate(zip(phases,commands)):
        keys = {'phase','command','return_code','cancelled','timed_out','elapsed_seconds'}
        if index in (0,2): keys.add('generated_project_transition')
        if (type(row) is not dict or set(row) != keys or row['phase'] != phase
                or type(row['return_code']) is not int or row['return_code'] != 0
                or row['cancelled'] is not False or row['timed_out'] is not False
                or type(row['command']) is not list or len(row['command']) < 5
                or row['command'][:3] != [str(godot_exe),'--path',str(folder)]):
            raise ValidationError('Body diagnostic lacks successful selected native phases')
    executable, _ = read_bytes(folder/'execution.json', 256*1024, budget, expected_sha256=execution.sha256)
    if executable != canonical_bytes(execution.to_dict()):
        raise ValidationError('Body diagnostic execution selection changed')
    records = {}
    for name, digest in spec['files'].items():
        if type(name) is not str or Path(name).name != name or name in {'.','..'}:
            raise ValidationError('Invalid body diagnostic input name')
        maximum = 512*1024*1024
        measured, size = hash_file(folder/name, maximum, budget)
        if measured != digest:
            raise ValidationError('Body diagnostic input differs from its bound specification')
        records[name] = dict(sha256=measured, bytes=size)
    for name, row in current.records.items():
        if name not in {'project.godot','configure.gd','validate.gd'} and records.get(name) != row:
            raise ValidationError('Body diagnostic inputs differ from currently admitted sources')
    for name, (source, source_sha256) in current.references.items():
        converted_name = 'expected_normals_vec4.f32' if name == 'native_normals.bin' else 'expected_vec4.f32'
        _source_reference(source, folder/converted_name, name == 'native_normals.bin', budget,
                          source_sha256=source_sha256, converted_sha256=spec['files'][converted_name])
    observed = verify_body_outputs(folder, execution.sha256, receipt['spec_sha256'], budget,
                                   input_hashes=spec['files'])
    if observed != receipt['observed']:
        raise ValidationError('Current independent body comparison differs from receipt')
    configuration = verify_import_configuration(folder, 'POST_REIMPORT', budget)
    expected_outputs = observed['output_files'] | {
        'measurement.json': dict(sha256=observed['measurement_sha256'], bytes=(folder/'measurement.json').stat().st_size),
        'import_configuration.json': dict(sha256=configuration['report_sha256'], bytes=(folder/'import_configuration.json').stat().st_size),
        'character.glb.import': dict(sha256=configuration['import_settings_sha256'], bytes=(folder/'character.glb.import').stat().st_size)}
    if receipt['files'] != expected_outputs:
        raise ValidationError('Body diagnostic output closure changed')
    records.update(expected_outputs)
    watched = {folder/name: (identity(protected(folder/name)), row) for name,row in records.items()}
    for path,digest in ((work/'diagnostic_receipt.json',draw.diagnostic_receipt_sha256),
                        (folder/'spec.json',receipt['spec_sha256'])):
        measured, size = hash_file(path, 4*1024*1024, budget)
        if measured != digest:
            raise ProjectStorageError('Body diagnostic metadata changed after admission')
        watched[path] = (identity(path), dict(sha256=digest, bytes=size))
    authority = ancestry(watched)
    def guard() -> None:
        current.guard()
        for path,stamp in original_authority.items():
            if identity(protected(path)) != stamp:
                raise ProjectStorageError('Original body diagnostic work directory replaced')
        for path, stamp in authority.items():
            if identity(protected(path)) != stamp:
                raise ProjectStorageError('Body diagnostic source ancestry changed')
        for path,(stamp,row) in watched.items():
            if identity(protected(path)) != stamp or hash_file(path,row['bytes'],budget) != (row['sha256'],row['bytes']):
                raise ProjectStorageError('Body diagnostic changed during private drawing')
        current.guard()
    guard()
    return BodyDrawInputs(folder, records, guard)
