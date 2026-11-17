"""Read-only, current-source-bound registered clip position diagnostics.

All expensive work belongs on a background worker. No engine, subprocess,
persisted report, or permission beyond private local preview is requested.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

from ucc.animations.target_action_diagnostic import (
    TargetActionDiagnosticSelection, TargetActionDiagnostics, DiagnosticSamples,
    measure_target_action_diagnostic, JointPositionEndpoints,
)
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import MAX_BYTES, MAX_FILE_BYTES, RETAINED_FILES
from .target_action import load_target_action
from .target_action_context import operation_budget, protected, check_target_action_catalog
from .godot_candidate_inputs import identity
from .godot_saved_preview_files import ProofReads
from .godot_saved_preview_catalog import final_catalog_guard, coordination_paths


@dataclass(frozen=True, slots=True)
class LoadedTargetActionDiagnostics:
    report: TargetActionDiagnostics
    watch_paths: tuple[Path, ...]
    watched_identities: tuple[tuple[Path, tuple[int, int, int, int]], ...]
    guard: Callable
    database_path: Path


def _boundary(operation):
    try:
        return operation()
    except OSError as error:
        raise ProjectStorageError('Target diagnostic input IO failed: '+str(error)) from error
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError) as error:
        raise ValidationError('Malformed selected target diagnostic evidence') from error


def _original_identities(reads, budget):
    # Cheap fence after the final logical check: never hash or rebaseline here.
    for path, stamp in reads.authority.items():
        budget.check()
        if identity(protected(path)) != stamp:
            raise ProjectStorageError('Target diagnostic original authority changed')
    for path in reads.records:
        if path.stat().st_nlink != 1:
            raise ProjectStorageError('Target diagnostic original input is no longer single-link')


def _samples(prepared, binding, reads, budget):
    name = 'body_first/target_timeline.json'
    row = binding.file_map[name]
    data = reads.metadata(prepared.directory/name, MAX_FILE_BYTES, row.sha256)
    if reads.records[prepared.directory/name][2] != row.bytes:
        raise ValidationError('Target diagnostic timeline length differs from selected binding')
    frames = data['full_timeline_frames']
    if (binding.root_motion_policy != 'SOURCE_HIP_MIDPOINT_V1'
            or data['root_motion_policy'] != binding.root_motion_policy
            or (data['source_first_frame'], data['source_frame_count'], data['fps']) != (2, 300, 30)
            or type(frames) is not list or len(frames) != 300
            or prepared.cache.frame_count != 300 or prepared.cache.fps != 30
            or prepared.cache.source_first_frame != 2):
        raise ValidationError('Target diagnostics require the complete registered hip-midpoint clock')
    roots = []
    for index, frame in enumerate(frames):
        budget.check()
        if (type(frame) is not dict or type(frame['frame']) is not int
                or type(frame['source_frame']) is not int
                or (frame['frame'], frame['source_frame']) != (index+1, index+2)
                or tuple(frame['hip_midpoint_world']) != prepared.cache.hips[index]):
            raise ValidationError('Target diagnostic timeline/cache frame or hip mapping differs')
        roots.append(tuple(frame['root_world_head']))
    pairs = data['mapped_pairs']
    first, last = frames[0]['target_global_poses'], frames[-1]['target_global_poses']
    if (type(pairs) is not list or not 1 <= len(pairs) <= 64
            or len(first) != len(pairs) or len(last) != len(pairs)):
        raise ValidationError('Target diagnostic mapped position endpoints differ')
    joints = []
    for pair, start, end in zip(pairs, first, last):
        budget.check()
        if len(start) != 16 or len(end) != 16:
            raise ValidationError('Target diagnostic mapped matrix is malformed')
        joints.append(JointPositionEndpoints(pair['target'],
            tuple(start[i*4+3] for i in range(3)), tuple(end[i*4+3] for i in range(3))))
    cache_name = 'playback/motion_skin.bin'
    cache_row = binding.file_map[cache_name]
    captured_cache = reads.records[prepared.directory/cache_name]
    budget.check()
    if (captured_cache[1:] != (cache_row.sha256, cache_row.bytes)
            or len(prepared.cache.packed) != cache_row.bytes
            or sha256(prepared.cache.packed).hexdigest() != cache_row.sha256):
        raise ValidationError('Target diagnostic cache bytes differ from selected binding')
    return DiagnosticSamples(
        first_vertices=prepared.cache.frame(0)[0],
        last_vertices=prepared.cache.frame(299)[0],
        world_matrix=prepared.cache.world_matrix,
        root_world_heads=tuple(roots), hip_midpoints_world=prepared.cache.hips,
        fps=prepared.cache.fps, source_first_frame=2, target_first_frame=1,
        mapped_joint_endpoints=tuple(joints), root_motion_policy=binding.root_motion_policy,
        cache_sha256=cache_row.sha256, timeline_sha256=row.sha256,
    )


def inspect_saved_target_action(store, *, selection: TargetActionDiagnosticSelection,
        database_path: Path, local_preview_confirmed: bool, cancel=None,
        timeout_s: float = 300, progress: Callable[[str], None] | None = None
        ) -> LoadedTargetActionDiagnostics:
    """Measure a selected typed proof and retain its ORIGINAL byte authority.

    The returned guard has a fresh bounded budget, revalidates the existing
    typed cache and current catalog, and compares against this operation's
    captured identities/hashes. It is never a GUI-thread stat-only waiver.
    """
    def operation():
        if type(selection) is not TargetActionDiagnosticSelection or local_preview_confirmed is not True:
            raise ValidationError('Choose an exact target binding and confirm private local diagnostics')
        database = protected(Path(database_path))
        with operation_budget(cancel, timeout_s) as budget:
            def phase(name):
                budget.check()
                if progress:
                    progress('TARGET_DIAGNOSTIC_'+name)
                budget.check()
            phase('SOURCE_REVIEW')
            prepared = load_target_action(store, **selection.loader_args(), database_path=database,
                cancel=budget.cancel, timeout_s=budget.remaining())
            reads = ProofReads(budget)
            phase('CAPTURE')
            # These hashes and identities come from the existing typed loader,
            # not from a subsequent namespace scan or reconstructed producer.
            stamps = dict(prepared.watched_identities)
            for path, digest in prepared.watched_inputs:
                budget.check()
                if identity(protected(path)) != stamps[path]:
                    raise ProjectStorageError('Target diagnostic input changed after typed loading')
                reads.record(path, MAX_FILE_BYTES, digest)
                if reads.records[path][0] != stamps[path]:
                    raise ProjectStorageError('Target diagnostic input replaced during capture')
            for path, stamp in stamps.items():
                if path != database and path in reads.authority and reads.authority[path] != stamp:
                    raise ProjectStorageError('Target diagnostic original ancestry changed after loading')
                if path not in {database, database.parent} and path not in reads.authority:
                    if identity(protected(path)) != stamp:
                        raise ProjectStorageError('Target diagnostic original catalog ancestry changed')
                    reads.authority[path] = stamp
            raw = reads.capture(prepared.binding_path, MAX_BYTES)
            binding = TargetActionBinding.from_bytes(raw)
            if (binding.sha256 != selection.binding_sha256
                    or set(binding.file_map) != set(RETAINED_FILES)
                    or prepared.directory != store.root/'animations/actions'/selection.binding_sha256
                    or prepared.binding_path != prepared.directory/'binding.json'):
                raise ProjectConflict('Target diagnostic selected binding or retained namespace differs')
            samples = _samples(prepared, binding, reads, budget)
            phase('MEASURE')
            report = measure_target_action_diagnostic(selection, samples, cancel_check=budget.check)
            database_identity = stamps[database][:2]
            parent_identity = stamps[database.parent][:2]

            def logical(fresh):
                fresh.check()
                check_target_action_catalog(database, binding.source,
                    expected_database_identity=database_identity,
                    expected_parent_identity=parent_identity)
                fresh.check()

            def guard(*, cancel=None, timeout_s=300):
                def recheck():
                    with operation_budget(cancel, timeout_s) as fresh:
                        reads.check(fresh)
                        load_target_action(store, **selection.loader_args(), database_path=database,
                            cancel=fresh.cancel, timeout_s=fresh.remaining())
                        reads.check(fresh)
                        final_catalog_guard(database, fresh, lambda: logical(fresh))
                        _original_identities(reads, fresh)
                return _boundary(recheck)

            phase('FINAL_GUARD')
            reads.check()
            watched = dict(reads.authority)
            catalog_parent_stamp = identity(protected(database.parent))
            coordinated = final_catalog_guard(database, budget, lambda: logical(budget))
            _original_identities(reads, budget)
            watched.update(coordinated)
            watched[database.parent] = catalog_parent_stamp
            paths = {path for path, stamp in watched.items() if stamp != (0, 0, 0, 0)}
            paths.difference_update(coordination_paths(database))
            paths.update(path for path, stamp in coordinated.items() if stamp != (0, 0, 0, 0))
            # No progress callback or fresh authority sampling follows the fence.
            budget.check()
            return LoadedTargetActionDiagnostics(report, tuple(sorted(paths, key=str)),
                tuple(sorted(watched.items(), key=lambda row: str(row[0]))), guard, database)
    return _boundary(operation)
