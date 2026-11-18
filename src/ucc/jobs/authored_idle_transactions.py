"""Exclusive private idle candidate publication; never adopts a project master."""
import os
import re
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ucc.core.errors import ProjectStorageError
from ucc.core.storage import _lock
from .authored_idle_evidence import record
from .authored_idle_io import private_bytes
from .export_destination import rename_new
from .godot_candidate_inputs import identity
from .target_action_context import protected


def inventory(folder, names, budget=None):
    protected(folder); result = {}
    with os.scandir(folder) as entries:
        for index, entry in enumerate(entries):
            if index >= 64 or entry.name not in names:
                raise ProjectStorageError('Private idle output contains an unrequested entry')
            path = folder/entry.name
            if budget is None:
                # Rollback must still authenticate ownership after cancellation.
                from .target_action_context import Budget
                budget = Budget(None, 60)
            row = record(path, budget)
            result[entry.name] = {'sha256': row['sha256'], 'bytes': row['bytes']}
    if set(result) != set(names):
        raise ProjectStorageError('Private idle output is incomplete')
    return result


def ownership(folder, names):
    return {name: (*identity(protected(folder/name)), (folder/name).stat().st_nlink) for name in names}


def write_journal(work, request_sha, state, **extra):
    protected(work)
    if type(state) is not str or re.fullmatch(r'[A-Z_]{1,64}', state) is None:
        raise ProjectStorageError('Idle journal phase is invalid')
    # Immutable phase records never overwrite an edited regular status file.
    target, temporary = work/('job_status-'+state+'.json'), work/'job_status.tmp'
    protected(target); protected(temporary)
    if target.exists() or target.is_symlink() or temporary.exists() or temporary.is_symlink():
        raise ProjectStorageError('Idle journal is redirected or already in progress')
    payload = private_bytes({'schema_version': 1, 'policy': 'UCC_PRIVATE_IDLE_JOB_V1',
        'inspection_request_sha256': request_sha, 'state': state, **extra})
    owned = None
    try:
        with temporary.open('xb') as stream:
            info = os.fstat(stream.fileno()); owned = info.st_dev, info.st_ino
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        rename_new(temporary, target)
    except BaseException as error:
        try:
            if owned is not None and temporary.is_file() and not temporary.is_symlink():
                info = temporary.stat()
                if ((info.st_dev, info.st_ino) == owned and info.st_nlink == 1 and info.st_size <= len(payload)):
                    with temporary.open('rb') as stream: current = stream.read(len(payload)+1)
                    if payload.startswith(current): temporary.unlink()
        except OSError as cleanup:
            error.add_note('Idle owned journal temporary cleanup failed: '+str(cleanup))
        raise


class IdlePublication:
    def __init__(self, store, destination, stage, names, budget):
        self.store, self.destination, self.stage = store, destination, stage
        self.names = set(names); self.stamp = identity(protected(stage))
        self.files = inventory(stage, self.names, budget)
        self.owners = ownership(stage, self.names); self.published = False

    def commit(self, guard, budget):
        with _lock(self.store.root/'.project.ucc.lock', timeout_s=min(3, budget.remaining())):
            guard(); self.destination.unchanged()
            if (identity(protected(self.stage)) != self.stamp or inventory(self.stage, self.names, budget) != self.files
                    or ownership(self.stage, self.names) != self.owners):
                raise ProjectStorageError('Private idle staging changed before exclusive publication')
            budget.check(); rename_new(self.stage, self.destination.path); self.published = True

    def withdraw(self, error):
        if not self.published: return
        path = self.destination.path
        try:
            if (self.stage.exists() or not path.is_dir() or path.is_symlink()
                    or identity(protected(path.parent)) != self.destination.parent_identity
                    or identity(protected(path)) != self.stamp or inventory(path, self.names) != self.files
                    or ownership(path, self.names) != self.owners):
                raise ProjectStorageError('Private idle output ownership changed; foreign edits cannot be moved')
            rename_new(path, self.stage); self.published = False
        except (OSError, ProjectStorageError) as rollback:
            error.add_note('Private idle output retained at '+str(path)+'; rollback was not safe: '+str(rollback))


def publish_idle_document(store, destination, filename, payload, guard, budget):
    """Stage exactly one canonical document and publish a new directory atomically."""
    digest = sha256(payload).hexdigest()
    budget.check()
    stage = destination.stage(str(uuid4()))
    stamp = file_stamp = None
    try:
        stamp = identity(protected(stage))
        path = protected(stage/filename)
        with path.open('xb') as stream:
            info = os.fstat(stream.fileno())
            file_stamp = info.st_dev, info.st_ino
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        publication = IdlePublication(store, destination, stage, {filename}, budget)
        if (publication.stamp != stamp or publication.owners[filename][:2] != file_stamp
                or publication.files[filename] != {'sha256': digest, 'bytes': len(payload)}):
            raise ProjectStorageError('The staged idle document differs from its canonical pointer')
        publication.commit(guard, budget)
        return digest
    except BaseException as error:
        try:
            _discard_document_stage(destination, stage, stamp, filename, file_stamp, payload)
        except (OSError, ProjectStorageError) as cleanup:
            error.add_note('Private idle document staging retained: '+str(cleanup))
        raise


def _discard_document_stage(destination, stage, stage_stamp, filename, file_stamp, payload):
    if (identity(protected(stage.parent)) != destination.parent_identity
            or identity(protected(stage)) != stage_stamp):
        raise ProjectStorageError('The idle document staging directory changed')
    path = protected(stage/filename)
    if path.exists():
        info = path.stat()
        if (not path.is_file() or info.st_nlink != 1 or (info.st_dev, info.st_ino) != file_stamp
                or info.st_size > len(payload) or set(stage.iterdir()) != {path}):
            raise ProjectStorageError('The idle document staging contents changed')
        with path.open('rb') as stream:
            if not payload.startswith(stream.read(len(payload) + 1)):
                raise ProjectStorageError('The idle document staging bytes changed')
        path.unlink()
    stage.rmdir()
