"""Stage the unassigned-material Unity animation with source-bound GPU correction."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_animation_recipe import BIND, CORRECTION_INPUTS, OUTPUT_LIMITS, VERIFY_REPORT, VERTICES
from ucc.export.unity_topology import UnityQuadSource
from .godot_registered_runtime_files import copy_file, hash_file, read_bytes, read_metadata
from .runner import WorkerFailure, run_process
from .target_action_context import operation_budget, protected
from .unity_animation_engine import (
    BIND_OBSERVATION, MAX_OUTPUT, VerifiedUnityNativeAnimation, _record, _write, copy_unity_project_inputs,
)
from .unity_animation_source import PreparedUnityAnimationSource
from .unity_engine import tree_hashes
from .worker_resources import bundled_unity_registered_correction_paths


RAW_RECEIPT = 'unity-animation-native-receipt.json'
ATTACH_RECEIPT = 'unity-animation-correction-stage.json'
ATTACH_PLAN = 'unity-animation-correction.json'
TOPOLOGY = 'Assets/UCC/source_quads.json'
SCENE = 'Assets/UCC/AnimatedCharacter.unity'
_SETTINGS = 'ProjectSettings/ProjectSettings.asset'
_OUTPUTS = {'Assets/UCC/NeutralPreview.mat', 'Assets/UCC/RegisteredCorrection.asset'}


@dataclass(frozen=True, slots=True)
class StagedUnityCorrectedAnimation:
    directory: Path
    receipt_sha256: str


def stage_unity_animation_correction(native: VerifiedUnityNativeAnimation, source: PreparedUnityAnimationSource, *,
        unity_exe: Path, work: Path, guard: Callable[[], None], cancel: Event | None = None,
        timeout_s: float = 300) -> StagedUnityCorrectedAnimation:
    """Attach the live correction between native skinning and normal reconstruction."""
    if type(native) is not VerifiedUnityNativeAnimation or type(source) is not PreparedUnityAnimationSource:
        raise ValidationError('Corrective attachment requires the verified raw Unity animation and Blender source')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        executable = protected(unity_exe)
        exe_record = _record(executable, MAX_OUTPUT, budget)
        raw_path = native.directory.parent/RAW_RECEIPT
        raw, _, raw_sha = read_metadata(raw_path, 512 * 1024, budget, expected_sha256=native.receipt_sha256)
        if (raw.get('policy') != 'UCC_UNITY_REGISTERED_ANIMATION_RAW_ADMISSION_V1'
                or raw.get('native_raw_skin_verified') is not True or raw.get('corrective_runtime_verified') is not False
                or raw.get('unity_executable_sha256') != exe_record.sha256
                or raw.get('blender_source_verification_sha256') != source.verification_sha256
                or raw.get('saved_files') != tree_hashes(native.directory, budget.cancel)):
            raise ValidationError('Unity corrective attachment requires the exact admitted native project')
        bind_path = native.directory/BIND_OBSERVATION
        native_bind, _, bind_sha = read_metadata(bind_path, 8 * 1024**2, budget, expected_sha256=raw['bind_sha256'])
        proof_path = source.directory/VERIFY_REPORT
        proof, _, _ = read_metadata(proof_path, 256 * 1024, budget, expected_sha256=source.verification_sha256)
        source_bind_path = source.directory/BIND
        bind, _, _ = read_metadata(source_bind_path, OUTPUT_LIMITS[BIND], budget,
                                   expected_sha256=proof['files'][BIND])
        if (native_bind['binding_sha256'] != source.binding_sha256 or native_bind['master_sha256'] != proof['master_sha256']
                or set(native_bind['shape_names']) != set(bind['morphs']) or len(bind['quads']) != 13378):
            raise ValidationError('Corrective operands and Unity mesh refer to different Blender source profiles')
        topology = UnityQuadSource(native_bind['master_sha256'], native_bind['native_mesh_sha256'], VERTICES,
            tuple(native_bind['native_to_source']), tuple(tuple(row) for row in bind['quads']),
            tuple(row['name'] for row in native_bind['bones']), tuple(native_bind['shape_names']))
        operands = {name: _record(source.directory/name, size, budget) for name, size in CORRECTION_INPUTS.items()}
        if any(row.bytes != CORRECTION_INPUTS[name] or row.sha256 != proof['files'][name]
               for name, row in operands.items()):
            raise ProjectStorageError('Unity correction operands changed after independent Blender reopening')
        scripts = bundled_unity_registered_correction_paths()
        scripts_records = {name: _record(path, 256 * 1024, budget) for name, path in scripts.items()}
        watched = {executable: exe_record.sha256, raw_path: raw_sha, bind_path: bind_sha,
                   proof_path: source.verification_sha256, source_bind_path: proof['files'][BIND],
                   **{source.directory/name: row.sha256 for name, row in operands.items()},
                   **{path: scripts_records[name].sha256 for name, path in scripts.items()}}

        def unchanged() -> None:
            guard()
            if (tree_hashes(native.directory, budget.cancel) != raw['saved_files']
                    or any(hash_file(path, MAX_OUTPUT, budget)[0] != sha for path, sha in watched.items())):
                raise ProjectStorageError('Unity source, executable or adapter changed during correction setup')

        work = Path(work)
        protected(work.parent)
        work.mkdir(exist_ok=False)
        stage = work/'stage'
        copy_unity_project_inputs(native.directory, stage, raw['saved_files'], budget)
        _write(stage/TOPOLOGY, topology.to_dict())
        asset_dir = stage/'Assets/UCC'
        correction_dir = asset_dir/'CorrectionData'
        correction_dir.mkdir()
        for name, record in operands.items():
            copy_file(source.directory/name, correction_dir/(name+'.bytes'), record, budget)
        for name, path in scripts.items():
            (asset_dir/name).parent.mkdir(exist_ok=True, parents=True)
            copy_file(path, asset_dir/name, scripts_records[name], budget)
        plan = dict(schema_version=1, policy='UCC_UNITY_ANIMATED_CORRECTION_ATTACH_V1',
                    native_mesh_sha256=topology.native_mesh_sha256, topology_sha256=topology.sha256,
                    operands=[dict(name=name, sha256=row.sha256) for name, row in operands.items()])
        _write(stage/ATTACH_PLAN, plan)
        before = tree_hashes(stage, budget.cancel)
        unchanged()
        command = [str(executable), '-batchmode', '-nographics', '-quit', '-noUpm', '-disableManagedDebugger',
                   '-projectPath', str(stage), '-executeMethod', 'Ucc.UnityAdapter.Editor.UccRegisteredCorrectionJob.Attach',
                   '-logFile', str(work/'Attach-Editor.log')]
        outcome = run_process(command, work/'attach', timeout_s=budget.remaining(), cancel=budget.cancel)
        run = dict(command=command, return_code=outcome.return_code, cancelled=outcome.cancelled,
                   timed_out=outcome.timed_out, elapsed_seconds=outcome.elapsed_seconds)
        _write(work/'command.json', run)
        if outcome.return_code != 0 or outcome.cancelled or outcome.timed_out:
            raise WorkerFailure('Unity could not attach corrected drawing; local logs: '+str(work))
        after = tree_hashes(stage, budget.cancel)
        if (not _OUTPUTS <= set(after) or before.get(SCENE) == after.get(SCENE)
                or any(after.get(name) != sha for name, sha in before.items() if name not in {SCENE, _SETTINGS})
                or read_bytes(stage/ATTACH_PLAN, 64 * 1024, budget)[0] != canonical_bytes(plan)):
            raise ProjectStorageError('Unity correction setup changed a protected input or failed to save the scene')
        unchanged()
        receipt = work/ATTACH_RECEIPT
        _write(receipt, dict(schema_version=1, policy='UCC_UNITY_ANIMATED_CORRECTION_STAGE_V1',
            raw_skin_receipt_sha256=raw_sha, blender_source_verification_sha256=source.verification_sha256,
            unity_executable_sha256=exe_record.sha256, topology_sha256=topology.sha256,
            native_bind_sha256=bind_sha, saved_files=after, corrected_draw_binding_persisted=True,
            corrective_runtime_verified=False, export_published=False, process=run))
        return StagedUnityCorrectedAnimation(stage, hash_file(receipt, 512 * 1024, budget)[0])
