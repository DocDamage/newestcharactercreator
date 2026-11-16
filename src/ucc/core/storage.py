"""Atomic versioned metadata storage with optimistic revision and file locking.

Never edits Blender files. A checked Blender work product must be promoted by a
future project-transaction coordinator, not through this JSON-only store.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterator

from .errors import ProjectConflict, ProjectStorageError, ValidationError
from .models import CharacterProject, safe_relative_path

PROJECT_FILE = "project.ucc.json"
LOCK_FILE = ".project.ucc.lock"
MAX_JSON_BYTES = 4 * 1024 * 1024


def _unique_project_fields(rows: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in rows:
        if key in result:
            raise ValidationError(f"Duplicate project JSON field: {key}")
        result[key] = value
    return result


def _nonfinite_project_number(value: str) -> None:
    raise ValidationError(f"Nonfinite project JSON number: {value}")


@contextmanager
def _lock(path: Path, timeout_s: float = 3.0) -> Iterator[None]:
    start = time.monotonic()
    handle: int | None = None
    while handle is None:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(handle, f"{os.getpid()}\n".encode())
        except FileExistsError as exc:
            if time.monotonic() - start >= timeout_s:
                raise ProjectConflict(f"Project is locked: {path.name}") from exc
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(handle)
        path.unlink(missing_ok=True)


class ProjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        if self.root.is_symlink():
            raise ProjectStorageError("Root cannot be a symlink")
        self.root = self.root.resolve(strict=False)
        self.file = self.root / PROJECT_FILE
        self.history = self.root / "history"

    def _check_safety(self) -> None:
        if self.root.exists() and not self.root.is_dir():
            raise ProjectStorageError("Project root is not a directory")
        if self.file.is_symlink() or self.history.is_symlink():
            raise ProjectStorageError("Project storage cannot contain redirected symlinks")
        for path in (self.file, self.history):
            if not path.resolve(strict=False).is_relative_to(self.root):
                raise ProjectStorageError("Project path escaped authorized root")

    def _read(self) -> CharacterProject:
        self._check_safety()
        if not self.file.is_file():
            raise FileNotFoundError(self.file)
        if self.file.stat().st_size > MAX_JSON_BYTES:
            raise ProjectStorageError("Project JSON exceeds safety limit")
        try:
            content = json.loads(self.file.read_text(encoding="utf-8"),
                                 object_pairs_hook=_unique_project_fields,
                                 parse_constant=_nonfinite_project_number)
            return CharacterProject.from_dict(content)
        except (OSError, ValueError, TypeError, KeyError, RecursionError, ValidationError) as exc:
            raise ProjectStorageError(f"Could not open project; no changes made: {exc}") from exc

    def load(self) -> CharacterProject:
        """Unknown/newer schema is never rewritten automatically."""
        return self._read()

    def _check_master(self, p: CharacterProject) -> None:
        if p.geometry_state == "not_generated":
            return
        assert p.master_blend is not None  # validated in immutable model
        relative = safe_relative_path(p.master_blend, "master_blend")
        master_source = self.root / relative
        master = master_source.resolve(strict=False)
        if master_source.is_symlink() or not master.is_relative_to(self.root):
            raise ProjectStorageError("Master model path escapes project")
        if not master.is_file() or master.stat().st_size < 16:
            raise ProjectStorageError("Master model missing or empty")
        with master.open("rb") as stream:
            if stream.read(7) != b"BLENDER":
                raise ProjectStorageError("Master is not a Blender-format file")
        # Structural header check does NOT claim a real successful Blender reopen.

    def save(self, project: CharacterProject, *, expected_revision: int | None = None,
             expected_project: CharacterProject | None = None) -> CharacterProject:
        """Write full metadata transactionally. Caller supplies original disk revision.

        For new projects pass expected_revision=None. For edits pass the loaded
        revision, avoiding lost updates across two IDEs/processes.
        """
        if expected_project is not None and not isinstance(expected_project,CharacterProject):
            raise ValidationError('Expected project snapshot must be character metadata')
        self._check_safety()
        self.root.mkdir(parents=True, exist_ok=True)
        with _lock(self.root / LOCK_FILE):
            self._check_safety()
            existing = self._read() if self.file.exists() else None
            if expected_project is not None and existing != expected_project:
                raise ProjectConflict('Project changed from the expected complete snapshot')
            if existing is None:
                if expected_revision is not None:
                    raise ProjectConflict("Project does not exist for requested revision")
                if project.revision != 0:
                    raise ProjectConflict("New project must begin at revision 0")
                result = replace(project, revision=1)
            else:
                if expected_revision is None or expected_revision != existing.revision:
                    raise ProjectConflict(f"Revision conflict: stored={existing.revision}, expected={expected_revision}")
                if project.project_id != existing.project_id:
                    raise ProjectConflict("Cannot replace project identity")
                if project.revision <= existing.revision:
                    raise ProjectConflict("Modified metadata must have newer revision")
                result = project
            self._check_master(result)
            payload = (json.dumps(result.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            if len(payload) > MAX_JSON_BYTES:
                raise ProjectStorageError("Project metadata too large")
            self._write_locked(payload, existing)
            return result

    def _write_locked(self, payload: bytes, existing: CharacterProject | None) -> None:
        try:
            if existing is not None:
                self.history.mkdir(exist_ok=True)
                self._check_safety()
                old = self.file.read_bytes()
                old_hash = hashlib.sha256(old).hexdigest()[:16]
                backup = self.history / f"project-r{existing.revision:08d}-{old_hash}.ucc.json"
                if not backup.exists():
                    self._atomic_bytes(backup, old)
            self._atomic_bytes(self.file, payload)
        except (OSError, ValueError) as exc:
            raise ProjectStorageError(f"Save failed; previous project retained: {exc}") from exc

    def _atomic_bytes(self, target: Path, payload: bytes) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".ucc-staged-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def list_backups(self) -> tuple[Path, ...]:
        self._check_safety()
        if not self.history.is_dir():
            return ()
        return tuple(sorted(self.history.glob("project-r*.ucc.json")))
