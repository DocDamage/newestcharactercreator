"""Content-addressed Blender master revisions with atomic project-pointer update.

This is a safe *staging* operation, NOT an MPFB integration or a geometry
validator. A blend placed by this function is always marked unverified. Only
an external fresh-Blender inspection may subsequently authorize validation.

Immutable master files avoid an impossible two-file atomic rename: the .blend
is installed first, then the small project JSON pointer is replaced atomically.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from threading import Event
from typing import Callable

from .errors import ProjectConflict, ProjectStorageError, ValidationError
from .models import CharacterProject, PartInstance
from .storage import ProjectStore

MAX_BLEND_BYTES = 2 * 1024 * 1024 * 1024
COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class MasterRevision:
    project: CharacterProject
    master_path: Path
    sha256: str
    bytes_copied: int
    reused: bool
    status: str = "generated_unverified"

    def __post_init__(self) -> None:
        if self.status != "generated_unverified":
            raise ValidationError("Master staging cannot produce geometry-validation status")


def _existing_or_new_root(directory: Path) -> Path:
    if directory.is_symlink():
        raise ProjectStorageError("Master path is a symlink")
    if directory.exists() and not directory.is_dir():
        raise ProjectStorageError("Master location is not a directory")
    directory.mkdir(parents=True, exist_ok=True)
    resolved = directory.resolve(strict=True)
    if not resolved.is_dir():
        raise ProjectStorageError("Master location cannot be resolved")
    return resolved


def _copy_staged(source: Path, directory: Path, max_bytes: int) -> tuple[Path, str, int]:
    fd, name = tempfile.mkstemp(prefix=".ucc-blend-stage-", suffix=".tmp", dir=directory)
    temporary = Path(name)
    size = 0
    digest = sha256()
    initial_stat = source.stat()
    try:
        with source.open("rb") as inp, os.fdopen(fd, "wb") as out:
            if inp.read(7) != b"BLENDER":
                raise ProjectStorageError("Source is not a Blender-format file")
            inp.seek(0)
            while True:
                chunk = inp.read(COPY_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ProjectStorageError("Source Blender file exceeds configured size limit")
                out.write(chunk)
                digest.update(chunk)
            out.flush()
            os.fsync(out.fileno())
        final_stat = source.stat()
        if (initial_stat.st_size != final_stat.st_size or
                initial_stat.st_mtime_ns != final_stat.st_mtime_ns):
            raise ProjectStorageError("Blender file changed during staging; retry")
        if size < 16:
            raise ProjectStorageError("Blender file is unexpectedly short")
        return temporary, digest.hexdigest(), size
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def stage_unverified_master(
    store: ProjectStore,
    blender_file: str | Path,
    *,
    authorized_source_root: str | Path,
    max_bytes: int = MAX_BLEND_BYTES,
    expected_revision: int | None = None,
    expected_project_id: str | None = None,
    expected_sha256: str | None = None,
    expected_project: CharacterProject | None = None,
    proposed_parts: tuple[PartInstance, ...] | None = None,
    cancel: Event | None = None,
    before_project_save: Callable[[], None] | None = None,
) -> MasterRevision:
    """Copy a Blender worker product to an immutable revision and advance JSON.

    This function never creates a mesh and never asserts source validity beyond
    a BLENDER signature and nonempty file. `authorized_source_root` MUST be an
    explicit worker job output directory, not a whole drive or home folder.
    `before_project_save` is test-only failure injection; do not use in UI.
    """
    if type(max_bytes) is not int or max_bytes < 16:
        raise ValidationError("max_bytes must be an integer >= 16")
    if expected_project is not None and not isinstance(expected_project,CharacterProject):
        raise ValidationError('Expected master project snapshot must be character metadata')
    if proposed_parts is not None and (type(proposed_parts) is not tuple or any(
            not isinstance(part, PartInstance) or part.status != 'proposed' for part in proposed_parts)):
        raise ValidationError('Master staging accepts only explicit proposed part instances')
    if expected_revision is not None and (
        type(expected_revision) is not int or expected_revision < 0
    ):
        raise ValidationError("expected_revision must be a nonnegative integer")
    if expected_project_id is not None and (
        not isinstance(expected_project_id, str) or not expected_project_id
    ):
        raise ValidationError("expected_project_id must be nonempty text")
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str) or len(expected_sha256) != 64
        or any(c not in "0123456789abcdef" for c in expected_sha256)
    ):
        raise ValidationError("expected_sha256 must be a lowercase SHA-256 digest")
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("Master staging cancelled before file copy")
    authorized = Path(authorized_source_root).expanduser()
    if authorized.is_symlink() or not authorized.is_dir():
        raise ProjectStorageError("Authorized worker output directory is missing/redirected")
    allowed = authorized.resolve(strict=True)
    source = Path(blender_file).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ProjectStorageError("Source Blender file is missing or a symlink")
    source_resolved = source.resolve(strict=True)
    if not source_resolved.is_relative_to(allowed):
        raise ProjectStorageError("Source file must be in the authorized worker output directory")
    original = store.load()  # Never create a project as an accidental side effect.
    if expected_project is not None and original != expected_project:
        raise ProjectConflict('Project changed from the verified master source snapshot')
    if proposed_parts is not None:
        # Validate the entire replacement before installing any immutable file.
        # This is intent staging, never a claim that a part passed geometry QA.
        replace(original, parts=proposed_parts)
    if expected_project_id is not None and original.project_id != expected_project_id:
        raise ProjectConflict("Character project changed during master generation")
    if expected_revision is not None and original.revision != expected_revision:
        raise ProjectConflict(
            f"Master generation is stale: expected revision {expected_revision}, "
            f"stored revision {original.revision}"
        )
    store._check_safety()
    master_dir = store.root / "master"
    if master_dir.is_symlink():
        raise ProjectStorageError("Master directory cannot be a symlink")
    revisions = master_dir / "versions"
    if revisions.is_symlink():
        raise ProjectStorageError("Versions directory cannot be a symlink")
    _existing_or_new_root(revisions)
    if not revisions.resolve(strict=True).is_relative_to(store.root):
        raise ProjectStorageError("Master versions directory escaped project root")
    temporary, digest, size = _copy_staged(source_resolved, revisions, max_bytes)
    destination = revisions / f"{digest}.blend"
    reused = False
    try:
        if expected_sha256 is not None and digest != expected_sha256:
            raise ProjectStorageError("Validated worker master changed before staging")
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError("Master staging cancelled before promotion")
        # A content-addressed destination is never overwritten. Hard links
        # could alias user data, so existing objects must be plain files.
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise ProjectStorageError("Existing master revision is redirected")
            check = sha256()
            with destination.open("rb") as stream:
                for chunk in iter(lambda: stream.read(COPY_CHUNK), b""):
                    check.update(chunk)
            if check.hexdigest() != digest:
                raise ProjectStorageError("Master revision digest mismatch")
            reused = True
        else:
            # Ensure no overwrite of an existing file; destination name is SHA-256
            # and staged content is fully fsynced before install.
            try:
                os.link(temporary, destination)
            except FileExistsError:
                # Concurrent writers may have installed identical bytes.
                if destination.is_symlink() or not destination.is_file():
                    raise ProjectStorageError("Concurrent master revision is invalid")
                check = sha256()
                with destination.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(COPY_CHUNK), b""):
                        check.update(chunk)
                if check.hexdigest() != digest:
                    raise ProjectStorageError("Concurrent master revision digest mismatch")
                reused = True
        # Only now swap the version pointer, via ProjectStore's serialized,
        # revision-checked, backup-preserving save.
        metadata = replace(
            original,
            master_blend=f"master/versions/{digest}.blend",
            geometry_state="generated_unverified",
            rig_profile=None,  # Old rig state may not describe this revision.
            parts=tuple(replace(part, status="proposed") for part in
                        (original.parts if proposed_parts is None else proposed_parts)),
            revision=original.revision + 1,
        )
        if before_project_save is not None:
            before_project_save()
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError("Master staging cancelled before project commit")
        saved = store.save(metadata, expected_revision=original.revision, expected_project=original)
        return MasterRevision(saved, destination, digest, size, reused)
    finally:
        temporary.unlink(missing_ok=True)
