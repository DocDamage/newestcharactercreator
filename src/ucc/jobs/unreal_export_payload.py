"""Closed portable Unreal inventory; source/native verification stays private."""
from pathlib import Path
from hashlib import sha256
import math
import shutil

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import UnrealExportRequest, ENGINE_VERSION, PROFILE, READINESS_FLAGS
from .export_guards import bounded_paths
from .godot_candidate_inputs import regular_file, read_json
from .master_preview import _digest
from .unreal_engine import DELIVERY_FILES, project_files

POLICY = 'UCC_UNREAL_EXPORT_TRANSACTION_V1'
RECEIPT = 'export_receipt.json'
ROOT_INPUTS = frozenset({'request.json', 'engine_recipe.json', 'README.txt'})
DIRECTORIES = frozenset({'Content', 'Content/UCC', 'Config', 'DerivedSources'})
SUCCESS_FLAGS = frozenset({'export_published', 'final_payload_verified',
    'private_static_native_verified', 'engine_import_verified', 'source_parity_verified'})
FALSE_FLAGS = frozenset({'shader_compilation_verified', 'runtime_gpu_verified',
    'pie_verified', 'player_build_verified', 'animation_clips_verified',
    'visual_quality_approved', 'distribution_license_review_complete',
    'cloud_transmission_authorized', 'project_metadata_changed'})


class _CopyReader:
    """Keep the copy primitive while enforcing its budget before every chunk."""
    def __init__(self, stream, cancel):
        self.stream, self.cancel, self.name = stream, cancel, stream.name

    def read(self, size: int=1024*1024) -> bytes:
        if self.cancel is not None and self.cancel.is_set():
            raise ProjectStorageError('Unreal payload copy cancelled or total deadline exceeded')
        data = self.stream.read(size)
        if self.cancel is not None and self.cancel.is_set():
            raise ProjectStorageError('Unreal payload copy cancelled or total deadline exceeded')
        return data


def snapshot(root: Path, cancel=None) -> dict[str, str]:
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise ProjectStorageError('Unreal export folder is missing or redirected')
    files = {}
    for path in bounded_paths(root, cancel, maximum_entries=256, allowed_directories=DIRECTORIES):
        if path != root and path.is_file():
            name = path.relative_to(root).as_posix()
            if name not in DELIVERY_FILES | ROOT_INPUTS | {RECEIPT}:
                raise ProjectStorageError('Unreal export contains an unlisted file or private cache')
            regular_file(path, root, 512*1024*1024)
            files[name] = _digest(path, cancel)
    return files


def check_snapshot(root: Path, expected: dict[str, str], cancel=None) -> None:
    if snapshot(root, cancel) != expected:
        raise ProjectStorageError('Unreal delivered payload changed, gained or lost files')


def engine_recipe(request: UnrealExportRequest, fbx_sha256: str) -> dict:
    if not is_sha256(fbx_sha256):
        raise ValidationError('Unreal derived source identity is invalid')
    return {'schema_version': 1, 'policy': 'UCC_UNREAL_PORTABLE_STATIC_PROFILE_V1',
        'profile': PROFILE, 'engine_version': ENGINE_VERSION,
        'request_sha256': request.sha256, 'source_fbx_sha256': fbx_sha256,
        'toolchain_sha256': request.toolchain_sha256,
        'scope': 'STATIC_BIND_RIG_MORPH_MATERIAL_SCENE',
        'animation_clips': False, 'runtime_gpu_verified': False,
        'shader_compilation_verified': False, 'distribution_license_review_complete': False}


def stage_payload(engine, destination: Path, request: UnrealExportRequest, cancel=None) -> dict[str, str]:
    receipt_path = regular_file(engine.workdir/'engine-receipt.json', engine.workdir, 2*1024*1024)
    if _digest(receipt_path, cancel) != engine.receipt_sha256:
        raise ProjectStorageError('Unreal native preparation receipt changed before delivery')
    receipt = read_json(receipt_path, 2*1024*1024)
    expected = dict(engine.files)
    if (type(receipt.get('schema_version')) is not int or receipt.get('schema_version') != 1
            or receipt.get('policy') != 'UCC_UNREAL_ENGINE_PREPARATION_V1'
            or receipt.get('request_sha256') != request.sha256
            or receipt.get('toolchain_identity_sha256') != request.toolchain_sha256
            or engine.request_sha256 != request.sha256 or set(expected) != DELIVERY_FILES
            or receipt.get('files') != expected or project_files(engine.project_directory, cancel) != expected
            or receipt.get('source_fbx_sha256') != expected['DerivedSources/character.fbx']
            or receipt.get('admission', {}).get('saved_reopened_bind_verified') is not True
            or any(receipt.get(name) is not (name in {'engine_import_verified', 'source_parity_verified'})
                   for name in READINESS_FLAGS)):
        raise ValidationError('Unreal preparation is incomplete, changed or outside static admission')
    for name, digest in sorted(expected.items()):
        source = regular_file(engine.project_directory/name, engine.project_directory, 512*1024*1024)
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(_CopyReader(src, cancel), dst, length=1024*1024)
        if _digest(source, cancel) != digest or _digest(target, cancel) != digest:
            raise ProjectStorageError('Unreal engine output changed during sealed delivery copy')
    documents = {'request.json': canonical_bytes(request.to_dict()),
        'engine_recipe.json': canonical_bytes(engine_recipe(request, expected['DerivedSources/character.fbx'])),
        'README.txt': ('Private static Unreal character\n\nOpen Character.uproject with Unreal 5.9.\n'
            'The scene includes the saved rig, twelve morph controls and owned skin material.\n'
            'Native static bind data is verified; shader rendering, animation clips, player builds,\n'
            'visual approval and distribution review remain unverified.\n'
            'Original Blender sources, verification datasets and caches are excluded.\n').encode('utf-8')}
    for name, data in documents.items():
        with (destination/name).open('xb') as stream: stream.write(data)
        expected[name] = sha256(data).hexdigest()
    check_snapshot(destination, expected, cancel)
    return expected


def verify_unreal_export_result(result, cancel=None) -> dict:
    root = Path(result.destination)
    path = regular_file(root/RECEIPT, root, 2*1024*1024)
    if _digest(path, cancel) != result.receipt_sha256:
        raise ProjectStorageError('Unreal export receipt changed after publication')
    raw = read_json(path, 2*1024*1024)
    fields = {'schema_version', 'policy', 'request_sha256', 'master_sha256', 'files',
        'engine_version', 'toolchain_sha256', 'source_verification_sha256',
        'engine_receipt_sha256', 'published_verification_sha256',
        'maximum_source_position_error_m', 'maximum_normal_angle_deg'} | SUCCESS_FLAGS | FALSE_FLAGS
    if (type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int
            or raw['schema_version'] != 1 or raw['policy'] != POLICY
            or raw['request_sha256'] != result.request_sha256 or raw['master_sha256'] != result.master_sha256
            or raw['engine_version'] != ENGINE_VERSION
            or any(type(raw[name]) not in (int, float) or not math.isfinite(raw[name])
                   or not 0 <= raw[name] <= cap for name, cap in
                   [('maximum_source_position_error_m', .000002), ('maximum_normal_angle_deg', .5)])
            or any(raw[name] is not True for name in SUCCESS_FLAGS)
            or any(raw[name] is not False for name in FALSE_FLAGS)
            or type(raw['files']) is not dict or set(raw['files']) != DELIVERY_FILES | ROOT_INPUTS
            or any(not is_sha256(value) for value in raw['files'].values())
            or any(not is_sha256(raw[name]) for name in ('toolchain_sha256',
                'source_verification_sha256', 'engine_receipt_sha256', 'published_verification_sha256'))):
        raise ValidationError('Unreal export receipt is incomplete or claims unverified readiness')
    request = UnrealExportRequest.from_bytes(regular_file(root/'request.json', root, 256*1024).read_bytes())
    if (request.sha256 != result.request_sha256 or dict(request.source_bindings)['master'] != result.master_sha256
            or request.toolchain_sha256 != raw['toolchain_sha256']
            or read_json(root/'engine_recipe.json', 128*1024) != engine_recipe(request, raw['files']['DerivedSources/character.fbx'])
            or raw['maximum_source_position_error_m'] != result.maximum_source_position_error_m
            or raw['maximum_normal_angle_deg'] != result.maximum_normal_angle_deg):
        raise ValidationError('Unreal export identity, portable profile or metrics differ')
    check_snapshot(root, raw['files'] | {RECEIPT: result.receipt_sha256}, cancel)
    return raw
