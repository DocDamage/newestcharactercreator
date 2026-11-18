"""Exclusive private idle candidate publication; never adopts a project master."""
import os
import re
from pathlib import Path

from ucc.core.errors import ProjectStorageError, ValidationError
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
        except (OSError, ProjectStorageError, ValidationError) as rollback:
            error.add_note('Private idle output retained at '+str(path)+'; rollback was not safe: '+str(rollback))
