"""Require corrected Unity rendering from a fresh, unchanged saved project."""
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import checked_sha
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_animation_recipe import OUTPUT_LIMITS, SOURCE_FRAMES, VERIFY_REPORT
from ucc.export.unity_corrected_animation_evidence import compare_unity_corrected_animation
from ucc.export.unity_topology import UnityQuadSource
from .godot_registered_runtime_files import hash_file, read_bytes, read_metadata
from .runner import WorkerFailure, run_process
from .target_action_context import operation_budget, protected
from .unity_animation_correction import ATTACH_RECEIPT, SCENE, TOPOLOGY, StagedUnityCorrectedAnimation
from .unity_animation_engine import MAX_OUTPUT, UNITY_VERSION, _write, copy_unity_project_inputs
from .unity_animation_payload import split_animated_unity_inputs
from .unity_animation_source import PreparedUnityAnimationSource
from .unity_engine import tree_hashes


EXPECT = 'unity-correction-expect.json'
OBSERVATION = 'unity-correction-observation.json'
RENDERED = 'unity-correction-rendered.f32'
SOURCE_POSITIONS = 'unity_animated_corrected_positions.f32'
SOURCE_NORMALS = 'unity_animated_corrected_normals.f32'
_ROW_FIELDS = {'sample', 'engine_frame', 'camera_id', 'completed_frame', 'completed_camera', 'offset'}


@dataclass(frozen=True, slots=True)
class VerifiedUnityCorrectedAnimation:
    directory: Path
    receipt_sha256: str


def verify_unity_corrected_animation(staged: StagedUnityCorrectedAnimation, source: PreparedUnityAnimationSource, *,
        unity_exe: Path, work: Path, guard: Callable[[], None], cancel: Event | None = None,
        timeout_s: float = 600) -> VerifiedUnityCorrectedAnimation:
    if type(staged) is not StagedUnityCorrectedAnimation or type(source) is not PreparedUnityAnimationSource:
        raise ValidationError('Unity corrected playback requires the exact staged scene and Blender source')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        exe = protected(unity_exe)
        exe_sha, _ = hash_file(exe, MAX_OUTPUT, budget)
        attach_path = staged.directory.parent/ATTACH_RECEIPT
        attach, _, attach_sha = read_metadata(attach_path, 512 * 1024, budget, expected_sha256=staged.receipt_sha256)
        saved = attach.get('saved_files')
        if (attach.get('policy') != 'UCC_UNITY_ANIMATED_CORRECTION_STAGE_V1'
                or attach.get('corrected_draw_binding_persisted') is not True
                or attach.get('unity_executable_sha256') != exe_sha
                or attach.get('blender_source_verification_sha256') != source.verification_sha256
                or saved != tree_hashes(staged.directory, budget.cancel) or SCENE not in saved):
            raise ValidationError('Corrected Unity verification found a different saved source, scene or engine')
        proof_path = source.directory/VERIFY_REPORT
        proof, _, _ = read_metadata(proof_path, 256 * 1024, budget, expected_sha256=source.verification_sha256)
        topology_sha = checked_sha(attach.get('topology_sha256'))
        topology = UnityQuadSource.from_bytes(read_bytes(staged.directory/TOPOLOGY, 8 * 1024**2, budget,
                                                       expected_sha256=topology_sha)[0])
        if (proof.get('target_binding_sha256') != source.binding_sha256
                or proof.get('master_sha256') != topology.master_sha256
                or proof.get('recomputed_source_references') is not True):
            raise ValidationError('Corrected Unity scene does not share the independently reopened Blender source')
        work = Path(work)
        protected(work.parent)
        work.mkdir(exist_ok=False)
        fresh = work/'fresh'
        portable, verifier = split_animated_unity_inputs(saved)
        verification_inputs = portable | verifier
        copy_unity_project_inputs(staged.directory, fresh, saved, budget, selected=verification_inputs)
        expected = dict(schema_version=1, policy='UCC_UNITY_REGISTERED_CORRECTION_VERIFY_V1',
            binding_sha256=source.binding_sha256, native_mesh_sha256=topology.native_mesh_sha256,
            topology_sha256=topology_sha, scene_sha256=saved[SCENE])
        _write(fresh/EXPECT, expected)
        command = [str(exe), '-batchmode', '-force-d3d11', '-noUpm', '-disableManagedDebugger',
                   '-projectPath', str(fresh), '-executeMethod', 'Ucc.UnityAdapter.Editor.UccRegisteredCorrectionVerify.Run',
                   '-logFile', str(work/'Verify-Editor.log')]
        guard()
        outcome = run_process(command, work/'verify', timeout_s=budget.remaining(), cancel=budget.cancel)
        run = dict(command=command, return_code=outcome.return_code, cancelled=outcome.cancelled,
                   timed_out=outcome.timed_out, elapsed_seconds=outcome.elapsed_seconds)
        _write(work/'command.json', run)
        if outcome.return_code != 0 or outcome.cancelled or outcome.timed_out:
            raise WorkerFailure('Unity corrected playback process failed; local logs: '+str(work))
        guard()
        observation, _, proof_sha = read_metadata(fresh/OBSERVATION, 256 * 1024, budget)
        raw_sha = checked_sha(observation.get('corrected_sha256'))
        rows = observation.get('rows')
        native_count = len(topology.native_source)
        observed = dict(expected, policy='UCC_UNITY_REGISTERED_CORRECTION_OBSERVATION_V1', unity=UNITY_VERSION,
            graphics='Direct3D11', normal_animator_wrap=True, lit_raster_changed=True, motion_raster_changed=True,
            native_vertices=native_count, corrected_sha256=raw_sha, rows=rows)
        if canonical_bytes(observation) != canonical_bytes(observed):
            raise ValidationError('Unity did not observe corrected lit playback on the pinned native scene')
        frame_bytes = native_count*6*4
        _check_rows(rows, frame_bytes)
        native = read_bytes(fresh/RENDERED, SOURCE_FRAMES*frame_bytes, budget, expected_sha256=raw_sha)[0]
        positions = read_bytes(source.directory/SOURCE_POSITIONS, OUTPUT_LIMITS[SOURCE_POSITIONS], budget,
                               expected_sha256=proof['files'][SOURCE_POSITIONS])[0]
        normals = read_bytes(source.directory/SOURCE_NORMALS, OUTPUT_LIMITS[SOURCE_NORMALS], budget,
                             expected_sha256=proof['files'][SOURCE_NORMALS])[0]
        comparison = compare_unity_corrected_animation(source_positions=positions, source_normals=normals,
            native_samples=native, native_to_source=topology.native_source, check=budget.check)
        if (tree_hashes(fresh, budget.cancel) != verification_inputs
                or tree_hashes(staged.directory, budget.cancel) != saved
                or hash_file(exe, MAX_OUTPUT, budget)[0] != exe_sha
                or hash_file(attach_path, 512 * 1024, budget)[0] != attach_sha
                or hash_file(proof_path, 256 * 1024, budget)[0] != source.verification_sha256
                or read_bytes(fresh/EXPECT, 64 * 1024, budget)[0] != canonical_bytes(expected)):
            raise ProjectStorageError('Unity corrected playback changed a guarded source or saved project')
        guard()
        receipt = work/'unity-animation-correction-verified.json'
        _write(receipt, dict(schema_version=1, policy='UCC_UNITY_ANIMATED_CORRECTION_ADMISSION_V1',
            source_verification_sha256=source.verification_sha256, stage_receipt_sha256=attach_sha,
            corrected_observation_sha256=proof_sha, unity_executable_sha256=exe_sha,
            saved_files=verification_inputs, portable_files=portable, comparison=asdict(comparison), corrective_runtime_verified=True,
            normal_loop_wrap_verified=True, lit_motion_verified=True, export_published=False))
        return VerifiedUnityCorrectedAnimation(fresh, hash_file(receipt, 512 * 1024, budget)[0])


def _check_rows(rows: object, frame_bytes: int) -> None:
    if type(rows) is not list or len(rows) != SOURCE_FRAMES:
        raise ValidationError('Unity did not render all 300 fixed-clock samples')
    previous_frame = -1
    camera = None
    for i, row in enumerate(rows):
        if (type(row) is not dict or set(row) != _ROW_FIELDS or any(type(n) is not int for n in row.values())
                or row['sample'] != i or row['offset'] != i*frame_bytes or row['engine_frame'] <= previous_frame
                or row['completed_frame'] != row['engine_frame'] or row['completed_camera'] != row['camera_id']
                or row['camera_id'] == 0 or (camera is not None and row['camera_id'] != camera)):
            raise ValidationError(f'Unity corrected draw is stale or incomplete at sample {i + 1}')
        previous_frame = row['engine_frame']
        camera = row['camera_id']
