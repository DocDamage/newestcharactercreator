"""Closed source-bound idle worker inputs; never consumes an existing clip."""
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from ucc.core.authored_idle import AuthoredIdleInspectionRequest, AuthoredIdleRequest
from ucc.core.target_action_format import canonical_bytes, MAX_BYTES, checked_uuid

MAX_EVIDENCE_BYTES = 16 * 1024 * 1024

OPERATIONS = {
    'inspect_authored_idle_target': {'request_sha256'},
    'author_original_idle_source': {'request_sha256'},
    'verify_authored_idle_source': {'request_sha256', 'review_sha256', 'source_sha256', 'recipe_sha256'},
}
FRAME_PROFILE = 'UCC_MEASURED_MPFB_IDLE_ANATOMY_V1'
SOURCE_PROFILE = 'UCC_ORIGINAL_MPFB_IDLE_SOURCE_V1'
ACTION_NAME = 'UCC_ORIGINAL_RELAXED_IDLE_UNAPPROVED'
QUALITY = {'human_visual_review_approved': False, 'loop_quality_approved': False,
           'usable_action_approved': False, 'engine_import_verified': False,
           'sprite_use_authorized': False, 'source_redistribution_authorized': False,
           'quality_measurements_verified': False, 'source_authorship_proven': False}


class AuthoredIdleError(ValueError):
    """A closed original-idle boundary or actual observation failed."""


def require(value: Any, message: str) -> None:
    if not value:
        raise AuthoredIdleError(message)


def checked_sha(value: Any) -> str:
    require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
            'Idle worker requires an exact lowercase SHA256')
    return value


def canonical_path(root: Path, name: str) -> Path:
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root, 'Idle workspace is not canonical')
    path = root / name
    require(Path(name).name == name and name not in ('', '.', '..'), 'Idle filenames are fixed basenames')
    require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'Idle workspace/input cannot be redirected')
    return path


def digest(path: Path, limit=512 * 1024 * 1024) -> str:
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
            'Idle input is missing, redirected, empty or oversized')
    before = path.stat()
    h = sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(chunk)
            require(size <= limit, 'Idle input grew beyond its finite limit')
            h.update(chunk)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and size == before.st_size,
            'Idle input changed while being hashed')
    return h.hexdigest()


def payload(root: Path, name: str, expected: str, limit: int=MAX_EVIDENCE_BYTES) -> bytes:
    path = canonical_path(root, name)
    require(digest(path, limit) == checked_sha(expected), 'Idle staged input digest differs')
    with path.open('rb') as stream:
        data = stream.read(limit+1)
    require(len(data) <= limit and sha256(data).hexdigest() == expected, 'Idle staged bytes changed')
    return data


def private_bytes(value: Any, limit: int=MAX_EVIDENCE_BYTES) -> bytes:
    """Private evidence has a separate finite cap from the 256KiB intent DTO."""
    result=bytearray()
    try:
        encoder=json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        for piece in encoder.iterencode(value):
            encoded=piece.encode('utf8')
            require(len(result)+len(encoded)<=limit,'Idle private evidence exceeds its explicit byte limit')
            result.extend(encoded)
    except (ValueError,TypeError,UnicodeError,RecursionError) as error:
        raise AuthoredIdleError('Invalid or oversized canonical idle evidence') from error
    return bytes(result)


def canonical_digest(value: Any) -> str:
    return sha256(private_bytes(value)).hexdigest()


def document(root: Path, name: str, expected: str, limit: int=MAX_EVIDENCE_BYTES) -> dict:
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate idle JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite idle JSON')
    data = payload(root, name, expected, limit)
    result = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    require(type(result) is dict and private_bytes(result,limit) == data, 'Idle JSON must be canonical and closed')
    return result


def write_document(root: Path, name: str, value: dict) -> dict:
    path = canonical_path(root, name)
    data = private_bytes(value)
    with path.open('xb') as stream:
        stream.write(data)
    return {'name': name, 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def output_record(root: Path, name: str) -> dict:
    path = canonical_path(root, name)
    return {'name': name, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def checked_job(job: dict, root: Path) -> tuple:
    operation = job.get('operation')
    checked_uuid(job.get('job_id'))
    options = job.get('options')
    require(operation in OPERATIONS and job.get('input_project') == 'candidate.blend'
            and type(options) is dict and set(options) == OPERATIONS[operation], 'Idle operation/options differ')
    for value in options.values():
        checked_sha(value)
    inspect = operation == 'inspect_authored_idle_target'
    name = 'idle_inspection_request.json' if inspect else 'idle_authoring_request.json'
    raw = payload(root, name, options['request_sha256'],MAX_BYTES)
    request = (AuthoredIdleInspectionRequest if inspect else AuthoredIdleRequest).from_bytes(raw)
    require(canonical_bytes(request.to_dict()) == raw, 'Idle request bytes are not canonical')
    require((job.get('job_id') == request.job_id) if operation != 'verify_authored_idle_source'
            else job.get('job_id') != request.job_id, 'Idle phase worker/intent identity differs')
    master_sha = dict(request.to_dict()['consumed_sources'])['master_and_derived_rig']
    expected = {'candidate.blend': master_sha, name: options['request_sha256']}
    if not inspect:
        expected['idle_anatomical_frame.json'] = request.anatomical_frame_sha256
    if operation == 'verify_authored_idle_source':
        expected.update({'authored_idle_review.blend': options['review_sha256'],
                         'original_idle.fbx': options['source_sha256'],
                         'authored_idle_recipe.json': options['recipe_sha256']})
    unchanged(root, expected)
    return request, expected


def unchanged(root: Path, expected: dict) -> None:
    for name, pin in expected.items():
        require(digest(canonical_path(root, name)) == pin, 'Idle phase changed a bound input')


def finite_vector(value: Any) -> tuple[float, float, float]:
    require(len(value) == 3 and all(type(x) in (int,float) and math.isfinite(x) and abs(x) < 10000 for x in value),
            'Idle anatomy contains a nonfinite/unbounded vector')
    return tuple(float(x) for x in value)


def finite_matrix(value: Any) -> list[float]:
    require(type(value) in (list,tuple) and len(value)==16
            and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=1e6 for x in value),
            'Nonfinite, unbounded or incomplete idle observed matrix')
    return [float(x) for x in value]
