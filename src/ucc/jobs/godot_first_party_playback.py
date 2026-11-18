"""Publish a fresh, privately verified project for the first-party Godot runtime."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, UCCError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_registered_body_runtime import PROFILE
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.export.godot_runtime_contract import CODE_FILES, DATA_FILES
from .export_destination import ExportDestination, plan_destination, rename_new
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .godot_first_party_animation import PreparedFirstPartyGodotAnimation, admit_first_party_godot_animation
from .godot_registered_runtime_files import copy_file, hash_file, read_metadata
from .runner import WorkerFailure, run_process
from .target_action_context import operation_budget, protected
from .worker_resources import bundled_registered_playback_paths


POLICY = 'UCC_PRIVATE_FIRST_PARTY_GODOT_PLAYBACK_RECEIPT_V1'
MANIFEST_POLICY = 'UCC_FIRST_PARTY_GODOT_PLAYBACK_V1'
RECEIPT = 'playback-receipt.json'
MAX_FILE = 128 * 1024 * 1024
RUNTIME_FILES = (CODE_FILES - {'ucc_skin_adapter.gd'}) | DATA_FILES | {'project.godot', 'playback.gd'}
VERIFIED = {
    'status': 'PRIVATE_GODOT_PLAYBACK_REOPENED', 'schema_version': 1,
    'native_animation_advanced': True, 'native_loop_wrapped': True,
    'corrected_normal_stream_drawn': True, 'rendered_motion_observed': True,
    'private_pixels_retained': False,
}


@dataclass(frozen=True, slots=True)
class PublishedFirstPartyGodotPlayback:
    directory: Path
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class _File:
    sha256: str
    bytes: int


def _record(path: Path, budget) -> _File:
    digest, size = hash_file(path, MAX_FILE, budget)
    if size == 0:
        raise ValidationError('An animated project resource is empty')
    return _File(digest, size)


def _write(path: Path, record: dict) -> _File:
    content = canonical_bytes(record)
    with path.open('xb') as stream:
        stream.write(content)
    return _File(sha256(content).hexdigest(), len(content))


def publish_first_party_godot_playback(store: ProjectStore, *, result: PreparedFirstPartyGodotAnimation,
        selection: RegisteredInputSelection, database_path: Path, permissions: tuple[EngineInputPermission, ...],
        godot_exe: Path, godot_main_exe: Path, destination: ExportDestination, cancel: Event | None = None,
        timeout_s: float = 300, progress: Callable[[str], None] | None = None,
        authorization_guard: Callable[[], None] | None = None) -> PublishedFirstPartyGodotPlayback:
    """Pack, reopen and draw the exact corrected loop before publishing a new local folder."""
    if (type(destination) is not ExportDestination or destination.path.is_relative_to(store.root)
            or destination.path.is_relative_to(Path(database_path).parent)
            or plan_destination(destination.path, store.root) != destination):
        raise ValidationError('Select a new local export folder outside the saved project and catalog')
    with operation_budget(cancel, timeout_s) as budget:
        inputs = admit_first_party_godot_animation(store, result=result, selection=selection,
            database_path=database_path, permissions=permissions, godot_exe=godot_exe,
            godot_main_exe=godot_main_exe, budget=budget, progress=progress)
        scripts = bundled_registered_playback_paths()
        script_records = {name: _record(path, budget) for name, path in scripts.items()}
        execution_id = str(uuid4())
        jobs = safe_directory(store, '.ucc-jobs')
        work = jobs/('first-party-godot-playback-'+execution_id)
        work.mkdir(exist_ok=False)
        build = work/'build'
        verify = work/'reopen'
        build.mkdir()
        verify.mkdir()
        owners = {path: identity(path) for path in (jobs, work, build, verify)}

        def guard(*, before_publication: bool = True) -> None:
            budget.check()
            if authorization_guard is not None:
                authorization_guard()
            inputs.guard()
            if any(identity(protected(path)) != stamp for path, stamp in owners.items()):
                raise ProjectStorageError('Animated Godot export workspace changed')
            if (bundled_registered_playback_paths() != scripts
                    or any(_record(path, budget) != script_records[name] for name, path in scripts.items())):
                raise ProjectStorageError('Bundled Godot playback programs changed')
            if before_publication:
                destination.unchanged()

        def check_files(folder: Path, records: dict[str, _File]) -> None:
            if any(_record(folder/name, budget) != row for name, row in records.items()):
                raise ProjectStorageError('An animated Godot project input or output changed')

        runtime_sources = {name: (inputs.files[name], _File(**inputs.records[name]))
                           for name in RUNTIME_FILES - {'project.godot', 'playback.gd'}}
        runtime_sources.update({name: (scripts[name], script_records[name])
                                for name in ('project.godot', 'playback.gd')})
        manifest = dict(schema_version=1, policy=MANIFEST_POLICY, profile=PROFILE,
            vertices=13380, corners=53512, frames=300, fps=30,
            files={name: row.sha256 for name, (_, row) in runtime_sources.items()})
        guard()
        for name, (source, row) in runtime_sources.items():
            if name != 'project.godot':
                copy_file(source, build/name, row, budget)
        build_rows = {name: row for name, (_, row) in runtime_sources.items() if name != 'project.godot'}
        importer = {'project.godot', 'configure.gd', 'ucc_skin_adapter.gd',
                    'character.glb', 'skin_plan.json', 'bind_source_indices.json'}
        for name in importer:
            row = _File(**inputs.records[name])
            copy_file(inputs.files[name], build/name, row, budget)
            build_rows[name] = row
        copy_file(scripts['pack.gd'], build/'pack.gd', script_records['pack.gd'], budget)
        build_rows['pack.gd'] = script_records['pack.gd']
        manifest_row = _write(build/'playback.json', manifest)
        build_rows['playback.json'] = manifest_row
        settings = ['--rendering-method', 'mobile', '--rendering-driver', 'vulkan', '--position', '-32000,-32000']

        def run(label: str, folder: Path, arguments: list[str], records: dict[str, _File]) -> None:
            guard()
            check_files(folder, records)
            if progress is not None:
                progress('GODOT_PLAYBACK_' + label.upper().replace('-', '_'))
            log = work/label
            log.mkdir(exist_ok=False)
            command = [str(godot_exe), '--path', str(folder), *arguments]
            outcome = run_process(command, log, timeout_s=budget.remaining(), cancel=budget.cancel)
            _write(log/'process.json', {'command': command, 'return_code': outcome.return_code,
                'cancelled': outcome.cancelled, 'timed_out': outcome.timed_out,
                'elapsed_seconds': outcome.elapsed_seconds})
            if outcome.return_code != 0 or outcome.cancelled or outcome.timed_out:
                raise WorkerFailure(f'Godot playback {label} failed. Local logs: {log}')
            guard()
            check_files(folder, records)

        run('initial-import', build, settings+['--editor', '--import'], build_rows)
        run('configure-import', build, ['--headless', '--script', 'res://configure.gd'], build_rows)
        run('configured-import', build, settings+['--editor', '--import'], build_rows)
        # Packing rechecks the imported skin buffer through Godot. The dummy
        # headless renderer cannot preserve the observable packed skin codes.
        run('pack', build, settings+['--script', 'res://pack.gd', '--',
            build_rows['character.glb'].sha256, build_rows['skin_plan.json'].sha256,
            manifest_row.sha256, build_rows['bind_source_indices.json'].sha256], build_rows)
        runtime_sources.update({
            'character.tscn': (build/'character.tscn', _record(build/'character.tscn', budget)),
            'playback.json': (build/'playback.json', manifest_row),
        })
        portable_rows = {name: row for name, (_, row) in runtime_sources.items()}
        for name, (source, row) in runtime_sources.items():
            copy_file(source, verify/name, row, budget)
        copy_file(scripts['verify.gd'], verify/'verify.gd', script_records['verify.gd'], budget)
        observed_path = work/'playback-observation.json'
        run('fresh-reopen', verify, settings+['--script', 'res://verify.gd', '--', str(observed_path)],
            portable_rows | {'verify.gd': script_records['verify.gd']})
        observed, _, observed_sha = read_metadata(observed_path, 64 * 1024, budget)
        if canonical_bytes(observed) != canonical_bytes(VERIFIED):
            raise ValidationError('The reopened project did not verify native lit loop playback')

        guard()
        stage = destination.stage(execution_id)
        stamp = identity(stage)
        for name, row in portable_rows.items():
            copy_file(verify/name, stage/name, row, budget)
        receipt = _write(stage/RECEIPT, {
            'schema_version': 1, 'policy': POLICY, 'private_local_only': True,
            'binding_sha256': selection.binding_sha256, 'diagnostic_receipt_sha256': result.diagnostic.receipt_sha256,
            'runtime_provenance_sha256': result.provenance.sha256, 'observation_sha256': observed_sha,
            'observed': observed, 'files': {name: row.sha256 for name, row in portable_rows.items()},
            'distribution_review_complete': False, 'material_appearance_approved': False,
        })
        guard()
        if identity(protected(stage)) != stamp or {path.name for path in stage.iterdir()} != set(portable_rows) | {RECEIPT}:
            raise ProjectStorageError('Animated project publication staging changed')
        check_files(stage, portable_rows | {RECEIPT: receipt})
        budget.check()
        destination.unchanged()
        rename_new(stage, destination.path)
        try:
            guard(before_publication=False)
            if (identity(protected(destination.path)) != stamp
                    or {path.name for path in destination.path.iterdir()} != set(portable_rows) | {RECEIPT}):
                raise ProjectStorageError('Published animated Godot project changed during verification')
            check_files(destination.path, portable_rows | {RECEIPT: receipt})
            budget.check()
        except BaseException as error:
            try:
                with operation_budget(None, 5) as rollback_budget:
                    own_rows = portable_rows | {RECEIPT: receipt}
                    if (identity(protected(destination.path.parent)) == destination.parent_identity
                            and identity(protected(destination.path)) == stamp
                            and {path.name for path in destination.path.iterdir()} == set(own_rows)
                            and all(_record(destination.path/name, rollback_budget) == row
                                    for name, row in own_rows.items())):
                        rename_new(destination.path, stage)
                    else:
                        error.add_note('Published destination changed; external files are retained')
            except (UCCError, OSError) as rollback_error:
                error.add_note('Animated Godot export rollback could not complete: ' + str(rollback_error))
            raise
        return PublishedFirstPartyGodotPlayback(destination.path, receipt.sha256)
