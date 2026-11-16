"""Bounded private engine verification transaction; never changes a master.

Input production by the Blender adapter is a separate required integration.
Success publishes a private candidate, not a shipping/certified engine export.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import tempfile
from threading import Event
import time
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore, _lock
from ucc.export.godot_candidate_contract import GodotCandidateRequest, canonical_bytes
from .expression_storage import safe_directory
from .godot_candidate_inputs import admit_inputs, regular_file, check_cancel, validate_candidate_files
from .godot_candidate_evidence import configuration, verification
from .master_preview import _digest
from .runner import run_process, WorkerFailure

SCRIPTS = ('ucc_skin_adapter.gd', 'ucc_configure_import.gd', 'ucc_verify_candidate.gd')


@dataclass(frozen=True, slots=True)
class PrivateGodotCandidate:
    project_id: str
    revision: int
    job_id: str
    directory: Path
    request_sha256: str
    verification_sha256: str
    observed: dict

    @property
    def engine_import_verified(self) -> bool:
        return False


def verify_staged_godot_candidate(store: ProjectStore, request: GodotCandidateRequest, *,
                                  candidate_folder: Path, motion_sources: dict[str, Path],
                                  godot_exe: Path, adapter_directory: Path,
                                  cancel: Event | None = None, timeout_s: float = 300,
                                  source_guard: Callable[[], None] | None = None) -> PrivateGodotCandidate:
    """Verify, recheck original sources, then atomically retain a new candidate.

    All processes share one total deadline. Cancellation, stale inputs and any
    malformed/missing evidence leave the saved project and prior candidates
    authoritative. Failed staging and logs remain private for diagnosis.
    """
    if (not isinstance(request, GodotCandidateRequest) or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Godot candidate needs a supported request and bounded total timeout')
    request = GodotCandidateRequest.from_bytes(canonical_bytes(request.to_dict()))
    start = time.monotonic()
    admitted = admit_inputs(store, request, Path(candidate_folder), motion_sources=motion_sources, cancel=cancel)
    if source_guard is not None:
        source_guard()
    exe = Path(godot_exe)
    if exe.is_symlink() or not exe.is_file() or exe.resolve() != exe:
        raise ValidationError('Select a canonical existing Godot executable; no installation is performed')
    scripts = Path(adapter_directory)
    if scripts.is_symlink() or not scripts.is_dir() or scripts.resolve() != scripts:
        raise ValidationError('Godot adapter resources are missing or redirected')
    script_hashes = {}
    for name in SCRIPTS:
        regular_file(scripts/name, scripts, 256*1024)
        script_hashes[name] = _digest(scripts/name, cancel)
    executable_sha = _digest(exe, cancel)
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    work = jobs/('godot-'+request.job_id)
    if work.exists() or work.is_symlink():
        raise ProjectStorageError('Godot job identity already exists; refusing to overwrite earlier evidence')
    work.mkdir(exist_ok=False)
    engine = work/'engine'; engine.mkdir()
    commands = []
    destination: Path | None = None

    def journal(state: str, **details) -> None:
        path = work/'job_status.json'
        if path.is_symlink():
            raise ProjectStorageError('Godot job status path was redirected')
        descriptor, name = tempfile.mkstemp(prefix='job_status-', suffix='.tmp', dir=work)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(canonical_bytes({'schema_version': 1, 'job_id': request.job_id,
                    'request_sha256': request.sha256, 'state': state, 'commands': commands,
                    'executable_sha256': executable_sha, 'script_hashes': script_hashes, **details}))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def run(label: str, arguments: list[str]) -> None:
        check_cancel(cancel)
        remaining = timeout_s-(time.monotonic()-start)
        if remaining < .05:
            raise WorkerFailure('Godot candidate exceeded its total time limit')
        command = [str(exe), '--path', str(engine), *arguments]
        result = run_process(command, work/label, timeout_s=remaining, cancel=cancel)
        commands.append({'phase': label, 'command': command, 'return_code': result.return_code,
                         'cancelled': result.cancelled, 'timed_out': result.timed_out,
                         'elapsed_seconds': result.elapsed_seconds})
        journal('RUNNING')
        if result.cancelled or result.timed_out or result.return_code != 0:
            raise WorkerFailure('Godot '+label+' failed/cancelled/timed out; private logs: '+str(work/label))
        admitted.unchanged(cancel)
        if source_guard is not None:
            source_guard()
        validate_candidate_files(engine, request, cancel)
        if _digest(engine/'request.json', cancel) != request.sha256:
            raise ProjectStorageError('Godot candidate request changed during verification')
        for name in SCRIPTS:
            if _digest(engine/name, cancel) != script_hashes[name] or _digest(scripts/name, cancel) != script_hashes[name]:
                raise ProjectStorageError('Godot adapter changed during the candidate job')

    try:
        journal('STAGING')
        for name, expected in request.files:
            check_cancel(cancel)
            shutil.copy2(admitted.candidate_folder/name, engine/name)
            if _digest(engine/name, cancel) != expected:
                raise ProjectStorageError('Candidate changed while copying into the engine job')
        if admitted.supplemental_files:
            evidence = engine/'.ucc-source-evidence'; evidence.mkdir()
            (evidence/'.gdignore').write_text('', encoding='utf-8')
        for name, expected in admitted.supplemental_files.items():
            check_cancel(cancel)
            from .godot_producer_evidence import evidence_folder
            shutil.copy2(evidence_folder(admitted.candidate_folder)/name, evidence/name)
            if _digest(evidence/name, cancel) != expected:
                raise ProjectStorageError('Producer evidence changed while copying into the engine job')
        for name in SCRIPTS:
            shutil.copy2(scripts/name, engine/name)
        (engine/'request.json').write_bytes(canonical_bytes(request.to_dict()))
        (engine/'project.godot').write_text('config_version=5\n[application]\nconfig/name="UCC private candidate verification"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding='utf-8')
        run('initial-import', ['--headless', '--editor', '--import'])
        run('configure-import', ['--headless', '--script', 'res://ucc_configure_import.gd',
                                '--', '--request-sha256', request.sha256])
        configuration(engine, request, cancel)
        run('configured-import', ['--headless', '--editor', '--import'])
        configuration(engine, request, cancel, after_reimport=True)
        run('actual-verification', ['--rendering-method', 'gl_compatibility', '--position', '-32000,-32000',
                                   '--script', 'res://ucc_verify_candidate.gd',
                                   '--', '--request-sha256', request.sha256])
        configuration(engine, request, cancel, after_reimport=True)
        observed = verification(engine, request, cancel)
        verified_sha = _digest(engine/'verification.json', cancel)
        if _digest(exe, cancel) != executable_sha:
            raise ProjectStorageError('Selected Godot executable changed during verification')
        if time.monotonic()-start > timeout_s:
            raise WorkerFailure('Godot candidate exceeded its total time limit before publication')
        # Allocate the new private destination without replacing any predecessor.
        destination_root = safe_directory(store, '.ucc-candidates', 'godot', create=True)
        destination = destination_root/request.job_id
        remaining = timeout_s-(time.monotonic()-start)
        if remaining <= 0:
            raise WorkerFailure('Godot candidate exceeded its total time limit before commit')
        with _lock(store.root/'.project.ucc.lock', timeout_s=min(3.0, remaining)):
            admitted.unchanged(cancel)
            if source_guard is not None:
                source_guard()
            if destination.exists() or destination.is_symlink():
                raise ProjectStorageError('Earlier Godot candidate already occupies this identity')
            check_cancel(cancel)
            if time.monotonic()-start > timeout_s:
                raise WorkerFailure('Godot candidate exceeded its total time limit during final source checks')
            os.rename(engine, destination)
        journal('PRIVATE_CANDIDATE_VERIFIED', candidate=str(destination), verification_sha256=verified_sha,
                engine_import_verified=False, visual_quality_approved=False)
        return PrivateGodotCandidate(request.project_id, request.revision, request.job_id,
                                     destination, request.sha256, verified_sha, observed)
    except BaseException as error:
        if destination is not None and not engine.exists() and destination.is_dir() and not destination.is_symlink():
            try:
                os.rename(destination, engine)
            except OSError as rollback_error:
                error.add_note('Private candidate rollback failed at '+str(destination)+': '+str(rollback_error))
        try:
            journal('FAILED', error_type=type(error).__name__, error=str(error)[:1500], engine_import_verified=False)
        except (OSError, ProjectStorageError) as journal_error:
            error.add_note('Private failure journal could not be recorded: '+str(journal_error))
        raise
