"""Bounded same-buffer metadata and sealed private candidate IO."""
from hashlib import sha256
import json
import os
from pathlib import Path

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_runtime_contract import (PAYLOAD_FILES, MAX_MANIFEST_BYTES,
    RegisteredRuntimeManifest, RetainedInputFile)
from .target_action_context import Budget
from .target_action_context import protected
from .godot_candidate_inputs import identity
from .export_guards import bounded_paths


FileIdentity = tuple[int,int,int,int]
DirectorySeal = tuple[FileIdentity,dict[str,FileIdentity]]


def _stamp(value: os.stat_result) -> FileIdentity:
    return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns


def read_bytes(path: Path, maximum: int, budget: Budget, *,
        expected_sha256: str | None=None) -> tuple[bytes,str]:
    """Hash and parse callers' SAME bytes; compare path/fd stamps within each API."""
    budget.check();path=protected(Path(path))
    before=path.stat()
    if not path.is_file() or not 0<=before.st_size<=maximum:
        raise ProjectStorageError("Private registered metadata exceeds its bound")
    with path.open("rb") as stream:
        opened=os.fstat(stream.fileno());payload=stream.read(maximum+1);finished=os.fstat(stream.fileno())
    after=path.stat();budget.check();protected(path)
    if (_stamp(before)!=_stamp(opened) or _stamp(opened)!=_stamp(finished)
            or _stamp(finished)!=_stamp(after) or before.st_ctime_ns!=after.st_ctime_ns
            or opened.st_ctime_ns!=finished.st_ctime_ns or len(payload)!=before.st_size
            or len(payload)>maximum):
        raise ProjectStorageError("Private registered metadata changed while reading")
    digest=sha256(payload).hexdigest()
    if expected_sha256 is not None and digest!=expected_sha256:
        raise ProjectStorageError("Private registered metadata differs from selected SHA")
    return payload,digest


def read_metadata(path: Path, maximum: int, budget: Budget, *,
        expected_sha256: str | None=None) -> tuple[dict,bytes,str]:
    payload,digest=read_bytes(path,maximum,budget,expected_sha256=expected_sha256)
    try:
        value=json.loads(payload.decode("utf-8"),object_pairs_hook=_unique_project_fields,
                         parse_constant=_nonfinite_project_number)
    except (ValueError,UnicodeError,RecursionError) as error:
        raise ValidationError("Malformed private registered-input JSON") from error
    if type(value) is not dict:
        raise ValidationError("Private registered metadata must be an object")
    canonical_bytes(value)
    return value,payload,digest


def hash_file(path: Path, maximum: int, budget: Budget) -> tuple[str,int]:
    path=protected(Path(path));before=path.stat();budget.check()
    if not path.is_file() or not 0<=before.st_size<=maximum:
        raise ProjectStorageError("Private registered input file is missing/oversized")
    digest=sha256();total=0
    with path.open("rb") as stream:
        opened=os.fstat(stream.fileno())
        for block in iter(lambda:stream.read(1024*1024),b""):
            budget.check();total+=len(block)
            if total>maximum:raise ProjectStorageError("Private input grew beyond its bound")
            digest.update(block)
        finished=os.fstat(stream.fileno())
    after=path.stat();protected(path)
    if (_stamp(before)!=_stamp(opened) or _stamp(opened)!=_stamp(finished)
            or _stamp(finished)!=_stamp(after) or before.st_ctime_ns!=after.st_ctime_ns
            or opened.st_ctime_ns!=finished.st_ctime_ns or total!=before.st_size):
        raise ProjectStorageError("Private registered input changed during hashing")
    budget.check()
    return digest.hexdigest(),total


def copy_file(source: Path,target: Path,record: RetainedInputFile,budget: Budget) -> None:
    source=protected(Path(source));target=Path(target);before=source.stat();total=0;digest=sha256()
    if before.st_size!=record.bytes:raise ProjectStorageError("Retained source length differs")
    protected(target.parent)
    with source.open("rb") as reader,target.open("xb") as writer:
        opened=os.fstat(reader.fileno())
        for block in iter(lambda:reader.read(1024*1024),b""):
            budget.check();total+=len(block)
            if total>record.bytes:raise ProjectStorageError("Retained source grew while copying")
            writer.write(block);digest.update(block)
        finished=os.fstat(reader.fileno());writer.flush();os.fsync(writer.fileno())
    after=source.stat();protected(source)
    if (_stamp(before)!=_stamp(opened) or _stamp(opened)!=_stamp(finished)
            or _stamp(finished)!=_stamp(after) or before.st_ctime_ns!=after.st_ctime_ns
            or opened.st_ctime_ns!=finished.st_ctime_ns or total!=record.bytes
            or digest.hexdigest()!=record.sha256):
        raise ProjectStorageError("Retained input copy raced a source change")
    if hash_file(target,record.bytes,budget)!=(record.sha256,record.bytes):
        raise ProjectStorageError("Retained copied bytes differ")


def seal(directory: Path, manifest: RegisteredRuntimeManifest, budget: Budget) -> DirectorySeal:
    directory=protected(Path(directory));expected={row.name:row for row in manifest.files}
    observed={};allowed=PAYLOAD_FILES|{"manifest.json"}
    for path in bounded_paths(directory,budget.cancel,maximum_entries=len(allowed)+2,
                              allowed_directories=frozenset()):
        budget.check()
        if path==directory:continue
        name=path.name
        if path.parent!=directory or name not in allowed or name in observed or not path.is_file():
            raise ProjectStorageError("Retained candidate inventory has an unknown/duplicate entry")
        if name=="manifest.json":
            raw,_=read_bytes(path,MAX_MANIFEST_BYTES,budget,expected_sha256=manifest.sha256)
            if raw!=canonical_bytes(manifest.to_dict()):
                raise ProjectStorageError("Retained manifest differs from selected canonical bytes")
        else:
            record=expected[name]
            if hash_file(path,record.bytes,budget)!=(record.sha256,record.bytes):
                raise ProjectStorageError("Retained candidate file differs from manifest")
        observed[name]=identity(path)
    if set(observed)!=allowed:
        raise ProjectStorageError("Retained candidate inventory is incomplete")
    return identity(directory),observed


def check_seal_identities(directory: Path,expected: DirectorySeal,budget: Budget) -> None:
    """Cheap final ownership fence after a final source/catalog guard."""
    directory=protected(Path(directory))
    if identity(directory)!=expected[0]:
        raise ProjectStorageError("Retained candidate directory identity changed")
    names=set()
    for path in bounded_paths(directory,budget.cancel,maximum_entries=len(expected[1])+2,
                              allowed_directories=frozenset()):
        budget.check()
        if path==directory:continue
        if (path.name in names or path.parent!=directory or not path.is_file()
                or expected[1].get(path.name)!=identity(path)):
            raise ProjectStorageError("Retained candidate file identity changed")
        names.add(path.name)
    if names!=set(expected[1]):raise ProjectStorageError("Retained candidate inventory changed")
