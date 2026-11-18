"""Exclusive private sprite publication with recoverable journal/rename failure."""
from pathlib import Path
import os

from ucc.core.body_sprites import POLICY
from ucc.core.errors import ProjectStorageError
from ucc.core.storage import _lock
from ucc.core.target_action_format import canonical_bytes
from .godot_candidate_inputs import identity
from .master_preview import _digest
from .target_action_context import protected
from .export_destination import rename_new


def write_journal(work: Path, request_sha256: str, state: str, **extra) -> None:
    target = work/'job_status.json'; temporary = work/'job_status.tmp'
    if target.is_symlink() or temporary.exists() or temporary.is_symlink():
        raise ProjectStorageError('Body-sprite journal was redirected or already in progress')
    payload = canonical_bytes({'schema_version':1,'policy':POLICY,
        'request_sha256':request_sha256,'state':state,**extra})
    owned = None
    try:
        with temporary.open('xb') as stream:
            info = os.fstat(stream.fileno()); owned = (info.st_dev, info.st_ino)
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException as error:
        try:
            if owned is not None and temporary.is_file() and not temporary.is_symlink():
                info = temporary.stat()
                if ((info.st_dev,info.st_ino) == owned and info.st_nlink == 1
                        and info.st_size <= len(payload) and payload.startswith(temporary.read_bytes())):
                    temporary.unlink()
        except OSError as cleanup:
            error.add_note('Body-sprite owned journal temporary cleanup failed: '+str(cleanup))
        raise


def file_inventory(folder: Path, expected_names: set[str], cancel=None) -> dict[str, str]:
    result = {}; protected(folder)
    with os.scandir(folder) as entries:
        for count, entry in enumerate(entries):
            if count >= 512 or entry.name not in expected_names:
                raise ProjectStorageError('Body-sprite output contains an unrequested entry')
            if cancel is not None and cancel.is_set(): raise ProjectStorageError('Body-sprite publication cancelled')
            path = protected(folder/entry.name)
            if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 32*1024*1024:
                raise ProjectStorageError('Body-sprite output is missing, shared or oversized')
            result[entry.name] = _digest(path, cancel)
    if set(result) != expected_names: raise ProjectStorageError('Body-sprite publication is incomplete')
    return result


class BodySpritePublication:
    def __init__(self, store, destination, stage, names, budget):
        self.store = store; self.destination = destination; self.stage = stage
        self.names = set(names); self.stamp = identity(stage)
        self.files = file_inventory(stage, self.names, budget.cancel); self.published = False

    def commit(self, guard, budget):
        with _lock(self.store.root/'.project.ucc.lock', timeout_s=min(3., budget.remaining())):
            guard(); self.destination.unchanged()
            if identity(protected(self.stage)) != self.stamp or file_inventory(self.stage, self.names, budget.cancel) != self.files:
                raise ProjectStorageError('Body-sprite output changed before atomic publication')
            budget.check(); rename_new(self.stage, self.destination.path); self.published = True

    def withdraw(self, error):
        """Move back only this exact newly published directory; never delete files."""
        if not self.published: return
        path = self.destination.path
        try:
            parent = protected(path.parent)
            if (self.stage.exists() or path.is_symlink() or not path.is_dir()
                    or identity(parent) != self.destination.parent_identity or identity(protected(path)) != self.stamp):
                raise ProjectStorageError('Body-sprite rollback cannot establish its exclusive directory identity')
            if file_inventory(path, self.names) != self.files:
                raise ProjectStorageError('Body-sprite rollback cannot relocate externally modified output')
            rename_new(path, self.stage); self.published = False
        except (OSError, ProjectStorageError) as rollback:
            error.add_note('Body-sprite rollback failed; retain and inspect '+str(path)+': '+str(rollback))
