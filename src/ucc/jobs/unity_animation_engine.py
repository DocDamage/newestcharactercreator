"""Private native Unity animation admission prior to corrected rendering and delivery."""
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import checked_sha
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_animation_evidence import UnityAnimationComparison, compare_unity_animation
from ucc.export.unity_animation_recipe import (
    BIND, BONES, FBX, OUTPUT_LIMITS, POLICY, SOURCE_FRAMES, VERIFY_REPORT, VERTICES, WEIGHTS,
)
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import copy_file, hash_file, read_bytes, read_metadata
from .runner import WorkerFailure, run_process
from .target_action_context import operation_budget, protected
from .unity_animation_source import PreparedUnityAnimationSource
from .unity_engine import tree_hashes
from .worker_resources import bundled_unity_registered_animation_paths


UNITY_VERSION = '6000.4.5f1'
INPUTS = 'unity-animation-inputs.json'
EXPECT = 'unity-animation-expect.json'
BIND_OBSERVATION = 'unity-animation-bind.json'
OBSERVATION = 'unity-animation-observation.json'
NATIVE_BONES = 'unity-animation-bones.f32'
NATIVE_RAW = 'unity-animation-raw-skin.f32'
RAW_REFERENCE = 'unity_animated_raw_positions.f32'
BONE_REFERENCE = 'unity_animated_world_bones.f32'
MAX_OUTPUT = 512 * 1024**2
MAX_NATIVE_VERTICES = 6 * VERTICES
BIND_FIELDS = {'schema_version', 'policy', 'binding_sha256', 'master_sha256', 'fbx_sha256',
               'native_mesh_sha256', 'clip_name', 'fps', 'duration_seconds', 'native_vertices',
               'native_to_source', 'bones'}


@dataclass(frozen=True, slots=True)
class VerifiedUnityNativeAnimation:
    directory: Path
    receipt_sha256: str
    comparison: UnityAnimationComparison


@dataclass(frozen=True, slots=True)
class _File:
    sha256: str
    bytes: int


def _write(path: Path, document: dict) -> None:
    with path.open('xb') as stream:
        stream.write(canonical_bytes(document))


def _record(path: Path, maximum: int, budget) -> _File:
    digest, size = hash_file(path, maximum, budget)
    if size < 1:
        raise ValidationError('Unity animation input or result is empty')
    return _File(digest, size)


def verify_unity_native_animation(prepared: PreparedUnityAnimationSource, *, unity_exe: Path,
        unity_executable_sha256: str, work: Path, guard: Callable[[], None],
        cancel: Event | None = None, timeout_s: float = 900,
        progress: Callable[[str], None] | None = None) -> VerifiedUnityNativeAnimation:
    """Stage an isolated Unity project and verify its reimported native Animator and raw skin."""
    if type(prepared) is not PreparedUnityAnimationSource or prepared.fbx_path != prepared.directory/FBX:
        raise ValidationError('Unity animation import requires the exact independently reopened Blender source')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        exe = protected(unity_exe)
        executable = _record(exe, MAX_OUTPUT, budget)
        report_path = prepared.directory/VERIFY_REPORT
        report, _, proof_sha = read_metadata(report_path, 256 * 1024, budget,
                                              expected_sha256=checked_sha(prepared.verification_sha256))
        files = report.get('files')
        if (executable.sha256 != checked_sha(unity_executable_sha256)
                or report.get('policy') != POLICY or report.get('target_binding_sha256') != prepared.binding_sha256
                or report.get('recomputed_source_references') is not True
                or report.get('blender_fbx_reimport_verified') is not True
                or report.get('engine_import_verified') is not False
                or type(files) is not dict or set(files) != set(OUTPUT_LIMITS)):
            raise ValidationError('Unity animation source report or exact editor identity differs from selection')
        inputs = {name: prepared.directory/name for name in OUTPUT_LIMITS}
        records = {name: _record(path, OUTPUT_LIMITS[name], budget) for name, path in inputs.items()}
        if any(records[name].sha256 != checked_sha(digest) for name, digest in files.items()):
            raise ProjectStorageError('Unity animation source changed since the fresh Blender run')
        scripts = bundled_unity_registered_animation_paths()
        script_records = {name: _record(path, 256 * 1024, budget) for name, path in scripts.items()}
        protected_records = {exe: executable, report_path: _record(report_path, 256 * 1024, budget),
                             **{path: records[name] for name, path in inputs.items()},
                             **{path: script_records[name] for name, path in scripts.items()}}
        seals = {path: identity(path) for path in protected_records}

        def unchanged():
            budget.check()
            guard()
            if (identity(protected(work))[:2] != owner
                    or any(identity(protected(path)) != seals[path]
                           or _record(path, row.bytes, budget) != row for path, row in protected_records.items())):
                raise ProjectStorageError('Unity animation source, worker script or workspace changed')

        work = Path(work)
        protected(work.parent)
        work.mkdir(exist_ok=False)
        owner = identity(work)[:2]
        stage, reopened = work/'stage', work/'fresh'
        assets = stage/'Assets/UCC'
        assets.mkdir(parents=True)
        (stage/'Packages').mkdir()
        (stage/'ProjectSettings').mkdir()
        _write(stage/'Packages/manifest.json', {'dependencies': {}})
        (stage/'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {UNITY_VERSION}\n', encoding='utf-8')
        for name in (FBX, WEIGHTS):
            copy_file(inputs[name], assets/name, records[name], budget)
        for name, path in scripts.items():
            target = assets/name
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_file(path, target, script_records[name], budget)
        recipe = dict(schema_version=1, policy='UCC_UNITY_REGISTERED_ANIMATION_IMPORT_V1',
                      binding_sha256=prepared.binding_sha256, master_sha256=checked_sha(report.get('master_sha256')),
                      fbx_sha256=files[FBX], weights_sha256=files[WEIGHTS])
        _write(stage/INPUTS, recipe)
        commands = []

        def run(folder: Path, method: str):
            unchanged()
            if progress is not None:
                progress('UNITY_REGISTERED_ANIMATION_'+method.upper())
            command = [str(exe), '-batchmode', '-nographics', '-noUpm', '-disableManagedDebugger']
            if method == 'Stage':
                command.append('-quit')
            command.extend(('-projectPath', str(folder), '-executeMethod',
                            'Ucc.UnityAdapter.Editor.UccRegisteredAnimationJob.'+method,
                            '-logFile', str(work/(method+'-Editor.log'))))
            outcome = run_process(command, work/method, timeout_s=budget.remaining(), cancel=budget.cancel)
            commands.append({'command': command, 'return_code': outcome.return_code,
                             'cancelled': outcome.cancelled, 'timed_out': outcome.timed_out,
                             'elapsed_seconds': outcome.elapsed_seconds})
            (work/'commands.json').write_bytes(canonical_bytes({'commands': commands}))
            if outcome.return_code != 0 or outcome.cancelled or outcome.timed_out:
                raise WorkerFailure('Unity animation '+method+' failed; local logs: '+str(work))
            unchanged()

        run(stage, 'Stage')
        bind, _, bind_sha = read_metadata(stage/BIND_OBSERVATION, 8 * 1024**2, budget)
        native_count = bind.get('native_vertices')
        if (set(bind) != BIND_FIELDS or type(bind['schema_version']) is not int or bind['schema_version'] != 1
                or bind.get('policy') != 'UCC_UNITY_REGISTERED_ANIMATION_BIND_V1'
                or any(bind.get(key) != recipe[key] for key in ('binding_sha256', 'master_sha256', 'fbx_sha256'))
                or type(native_count) is not int or not VERTICES <= native_count <= MAX_NATIVE_VERTICES
                or type(bind.get('bones')) is not list or len(bind['bones']) != BONES
                or type(bind.get('native_to_source')) is not list or len(bind['native_to_source']) != native_count
                or type(bind.get('clip_name')) is not str or not 1 <= len(bind['clip_name']) <= 160
                or not checked_sha(bind.get('native_mesh_sha256'))
                or bind.get('fps') != 30 or bind.get('duration_seconds') != 10
                or not (assets/'AnimatedCharacter.unity').is_file()):
            raise ValidationError('Unity staged animation binding has an unexpected profile or inventory')
        sealed = tree_hashes(stage, budget)
        immutable_assets = {f'Assets/UCC/{name}': records[name].sha256 for name in (FBX, WEIGHTS)}
        immutable_assets.update({f'Assets/UCC/{name}': row.sha256 for name, row in script_records.items()})
        if any(sealed.get(name) != digest for name, digest in immutable_assets.items()):
            raise ProjectStorageError('Unity import modified first-party code or selected source bytes')
        for relative, digest in sealed.items():
            target = reopened/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            row = _record(stage/relative, MAX_OUTPUT, budget)
            if row.sha256 != digest:
                raise ProjectStorageError('Unity stage changed during fresh project copy')
            copy_file(stage/relative, target, row, budget)
        _write(reopened/INPUTS, recipe)
        expectation = dict(schema_version=1, policy='UCC_UNITY_REGISTERED_ANIMATION_VERIFY_V1', bind_sha256=bind_sha)
        _write(reopened/EXPECT, expectation)
        bind_record = _record(stage/BIND_OBSERVATION, 8 * 1024**2, budget)
        if bind_record.sha256 != bind_sha:
            raise ProjectStorageError('Unity bind observation changed during fresh project copy')
        copy_file(stage/BIND_OBSERVATION, reopened/BIND_OBSERVATION, bind_record, budget)
        if tree_hashes(reopened, budget) != sealed or any((reopened/name).exists() for name in ('Library', 'Temp')):
            raise ProjectStorageError('Unity fresh project copy is incomplete or contains a cache')
        run(reopened, 'Verify')
        if tree_hashes(reopened, budget) != sealed or tree_hashes(stage, budget) != sealed:
            raise ProjectStorageError('Unity fresh animation playback modified saved inputs')
        for path, document in ((stage/INPUTS, recipe), (reopened/INPUTS, recipe), (reopened/EXPECT, expectation)):
            if read_bytes(path, 64 * 1024, budget)[0] != canonical_bytes(document):
                raise ProjectStorageError('Unity animation verification modified its input recipe')
        read_metadata(reopened/BIND_OBSERVATION, 8 * 1024**2, budget, expected_sha256=bind_sha)
        observation, _, observation_sha = read_metadata(reopened/OBSERVATION, 128 * 1024, budget)
        comparison = _compare(prepared.directory, reopened, files, bind, bind_sha, observation, budget)
        unchanged()
        receipt_path = work/'unity-animation-native-receipt.json'
        _write(receipt_path, dict(schema_version=1, policy='UCC_UNITY_REGISTERED_ANIMATION_RAW_ADMISSION_V1',
            blender_source_verification_sha256=proof_sha, unity_executable_sha256=executable.sha256,
            unity_version=UNITY_VERSION, bind_sha256=bind_sha, observation_sha256=observation_sha,
            observed=asdict(comparison), saved_files=sealed, native_raw_skin_verified=True,
            corrective_runtime_verified=False, export_published=False))
        return VerifiedUnityNativeAnimation(reopened, hash_file(receipt_path, 512 * 1024, budget)[0], comparison)


def _compare(source: Path, reopened: Path, files: dict, bind: dict, bind_sha: str, observation: dict,
             budget) -> UnityAnimationComparison:
    bone_sha = checked_sha(observation.get('bones_sha256'))
    raw_sha = checked_sha(observation.get('raw_skin_sha256'))
    expected = dict(schema_version=1, policy='UCC_UNITY_REGISTERED_ANIMATION_OBSERVATION_V1',
        bind_sha256=bind_sha, binding_sha256=bind['binding_sha256'], clip_name=bind['clip_name'], unity=UNITY_VERSION,
        normal_animation_advanced=True, normal_loop_wrapped=True, fixed_clock_samples=SOURCE_FRAMES, bone_count=BONES,
        native_vertices=bind['native_vertices'], bones_sha256=bone_sha, raw_skin_sha256=raw_sha,
        corrective_runtime_verified=False, visual_quality_approved=False)
    if canonical_bytes(observation) != canonical_bytes(expected):
        raise ValidationError('Unity failed to witness a complete advancing and looping native Animator')
    bind_source, _, _ = read_metadata(source/BIND, OUTPUT_LIMITS[BIND], budget, expected_sha256=files[BIND])
    source_bones = bind_source.get('bones')
    if type(source_bones) is not list or len(source_bones) != BONES:
        raise ValidationError('Unity animation requires the original Blender bind skeleton')
    original_bones = read_bytes(source/BONE_REFERENCE, OUTPUT_LIMITS[BONE_REFERENCE], budget,
                                expected_sha256=files[BONE_REFERENCE])[0]
    original_raw = read_bytes(source/RAW_REFERENCE, OUTPUT_LIMITS[RAW_REFERENCE], budget,
                              expected_sha256=files[RAW_REFERENCE])[0]
    native_bones = read_bytes(reopened/NATIVE_BONES, SOURCE_FRAMES * BONES * 16 * 4, budget,
                              expected_sha256=bone_sha)[0]
    native_raw = read_bytes(reopened/NATIVE_RAW, SOURCE_FRAMES * bind['native_vertices'] * 3 * 4, budget,
                            expected_sha256=raw_sha)[0]
    return compare_unity_animation(source_bones=source_bones, native_bones=bind['bones'], source_vertex_count=VERTICES,
        native_to_source=bind['native_to_source'], source_pose_samples=original_bones, native_pose_samples=native_bones,
        source_raw_samples=original_raw, native_raw_samples=native_raw, check=budget.check)
