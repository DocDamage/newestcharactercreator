"""Versioned source-data payload validation; stdlib only, no worker execution.

The builder also copies this exact module to the isolated Blender bridge. The
manifest detects damage and binds job dependencies; it is not a code signature
or a distribution/license approval.
"""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys

POLICY = 'UCC_WORKER_PAYLOAD_V4'
LEGACY_POLICY = 'UCC_WORKER_PAYLOAD_V1'
GODOT_ANIMATION_POLICY = 'UCC_WORKER_PAYLOAD_V2'
UNITY_ANIMATION_POLICY = 'UCC_WORKER_PAYLOAD_V3'
ADAPTER_FILES = frozenset({'validate.gd', 'configure.gd', 'clay.gdshader', 'project.godot'})
SUPPORT = 'worker_support'
MANIFEST = 'payload.v1.json'
ADAPTER = SUPPORT + '/adapters/godot/native_runtime'
STATIC_ADAPTER = SUPPORT + '/adapters/godot/static_export'
STATIC_ADAPTER_FILES = frozenset({'configure.gd', 'inspect.gd', 'export.gd', 'ucc_skin_adapter.gd'})
REGISTERED_CORRECTION_ADAPTER = SUPPORT + '/adapters/godot/registered_correction'
REGISTERED_CORRECTION_FILES = frozenset({'runtime_kernel.gd', 'ucc_skin_adapter.gd', 'smooth.glsl',
    'corners.glsl', 'combine.glsl', 'normal_faces.glsl', 'normal_vertices.glsl'})
REGISTERED_BODY_ADAPTER = SUPPORT + '/adapters/godot/registered_body300'
REGISTERED_BODY_FILES = frozenset({'configure.gd', 'validate.gd', 'project.godot'})
REGISTERED_PLAYBACK_ADAPTER = SUPPORT + '/adapters/godot/registered_playback'
REGISTERED_PLAYBACK_FILES = frozenset({'pack.gd', 'playback.gd', 'project.godot', 'verify.gd'})
UNITY_ADAPTER = SUPPORT + '/adapters/unity'
UNITY_ADAPTER_FILES = frozenset({'UccNativeNormals.cs','UccNativeMeshIdentity.cs','UccQuadSourceData.cs',
    'UccQuadNormals.compute','UccNativeSkinWarmup.shader','Editor/UccSourceWeights.cs','Editor/UccUnityImport.cs',
    'Editor/UccUnityObservation.cs','Editor/UccUnityExportJobs.cs','UccUnityRuntimeObserver.cs','Editor/UccUnityRuntimeJob.cs'})
UNITY_REGISTERED_ANIMATION_ADAPTER = UNITY_ADAPTER + '/registered_animation'
UNITY_REGISTERED_ANIMATION_FILES = frozenset({'Editor/UccRegisteredAnimationJob.cs',
    'UccRegisteredAnimatorSampler.cs', 'UccRegisteredAnimationObserver.cs'})
UNITY_REGISTERED_CORRECTION_ADAPTER = UNITY_ADAPTER + '/registered_correction'
UNITY_REGISTERED_CORRECTION_FILES = frozenset({'Editor/UccRegisteredCorrectionJob.cs',
    'Editor/UccRegisteredCorrectionVerify.cs', 'UccRegisteredCorrectionObserver.cs',
    'UccRegisteredCorrection.cs', 'UccRegisteredCorrection.compute', 'UccRegisteredQuadNormals.compute'})
UNITY_REGISTERED_CORRECTION_BINDING = 'UccRegisteredNormalsCorrectionBinding.cs'
UNREAL_ADAPTER = SUPPORT + '/adapters/unreal'
UNREAL_ADAPTER_FILES = frozenset({'README.md', 'project.uproject', 'DefaultEngine.ini',
    'capture_common.py', 'stage.py', 'reopen.py', 'UccNativeObservation.uplugin',
    'Source/UccNativeObservation/UccNativeObservation.Build.cs',
    'Source/UccNativeObservation/Public/UccNativeObservationLibrary.h',
    'Source/UccNativeObservation/Private/UccNativeObservationLibrary.cpp',
    'Source/UccNativeObservation/Private/UccNativeObservationModule.cpp'})
UNREAL_REGISTERED_ANIMATION = UNREAL_ADAPTER + '/registered_animation'
UNREAL_REGISTERED_PREVIEW = UNREAL_ADAPTER + '/registered_preview'
UNREAL_REGISTERED_ANIMATION_FILES = frozenset({'UccNativeAnimation.uplugin',
    'Source/UccNativeAnimation/UccNativeAnimation.Build.cs',
    *('Source/UccNativeAnimation/Private/'+name for name in (
        'UccNativeAnimation.h', 'UccNativeAnimationCommandlet.h', 'UccNativeAnimationCommandlet.cpp',
        'UccNativeAnimationImport.cpp', 'UccNativeAnimationObserve.cpp',
        'UccNativeAnimationPreviewStage.cpp', 'UccNativeAnimationPreviewVerify.cpp'))})
UNREAL_REGISTERED_PREVIEW_FILES = frozenset({'UccRegisteredPreview.uplugin',
    'Source/UccRegisteredPreview/UccRegisteredPreview.Build.cs',
    *('Source/UccRegisteredPreview/Public/'+name for name in (
        'UccRegisteredPreviewActor.h', 'UccRegisteredCorrection.h')),
    *('Source/UccRegisteredPreview/Private/'+name for name in (
        'UccRegisteredPreviewActor.cpp', 'UccRegisteredPreviewModule.cpp', 'UccRegisteredCorrection.cpp'))})


class WorkerPayloadError(ValueError):
    """Incomplete, redirected or changed isolated worker resources."""


def _unique(pairs: list[tuple]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise WorkerPayloadError('Duplicate worker payload field')
        value[key] = item
    return value


def _file(base: Path, relative: str, maximum: int) -> Path:
    path = base.joinpath(*PurePosixPath(relative).parts)
    if (path.is_symlink() or not path.is_file() or path.resolve() != path
            or not 0 <= path.stat().st_size <= maximum):
        raise WorkerPayloadError('Worker payload file is missing, redirected or oversized: ' + relative)
    return path


def validate_worker_payload(base: Path) -> tuple[Path, ...]:
    """Validate the closed payload, including all bridge scripts and import data."""
    base = Path(base)
    if base.is_symlink() or not base.is_dir() or base.resolve() != base:
        raise WorkerPayloadError('Worker payload base must be a canonical directory')
    manifest = _file(base, SUPPORT + '/' + MANIFEST, 256 * 1024)
    try:
        raw = json.loads(manifest.read_bytes(), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WorkerPayloadError('Invalid worker payload manifest') from error
    if (type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'files', 'modules',
            'engine_import_verified', 'distribution_license_review_complete'}
            or type(raw['schema_version']) is not int
            or (raw['schema_version'], raw['policy']) not in ((1, LEGACY_POLICY), (2, GODOT_ANIMATION_POLICY),
                (3, UNITY_ANIMATION_POLICY), (4, POLICY))
            or raw['engine_import_verified'] is not False
            or raw['distribution_license_review_complete'] is not False
            or type(raw['files']) is not dict or not 10 <= len(raw['files']) <= 512
            or type(raw['modules']) is not list or not raw['modules']
            or any(type(name) is not str or not re.fullmatch(r'ucc(?:\.[a-z_][a-z_0-9]*)*', name) for name in raw['modules'])
            or raw['modules'] != sorted(set(raw['modules']))):
        raise WorkerPayloadError('Unsupported worker payload contract')
    groups = [(ADAPTER, ADAPTER_FILES), (STATIC_ADAPTER, STATIC_ADAPTER_FILES),
              (UNITY_ADAPTER, UNITY_ADAPTER_FILES), (UNREAL_ADAPTER, UNREAL_ADAPTER_FILES)]
    if raw['schema_version'] >= 2:
        groups.extend(((REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES),
                       (REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES),
                       (REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES)))
    if raw['schema_version'] >= 3:
        groups.extend(((UNITY_REGISTERED_ANIMATION_ADAPTER, UNITY_REGISTERED_ANIMATION_FILES |
                        {UNITY_REGISTERED_CORRECTION_BINDING}),
                       (UNITY_REGISTERED_CORRECTION_ADAPTER, UNITY_REGISTERED_CORRECTION_FILES)))
    if raw['schema_version'] >= 4:
        groups.extend(((UNREAL_REGISTERED_ANIMATION, UNREAL_REGISTERED_ANIMATION_FILES),
                       (UNREAL_REGISTERED_PREVIEW, UNREAL_REGISTERED_PREVIEW_FILES)))
    resources = {root + '/' + name for root, files in groups for name in files}
    paths = []
    for relative, record in raw['files'].items():
        if (type(relative) is not str or '\\' in relative or ':' in relative
                or str(PurePosixPath(relative)) != relative or '..' in PurePosixPath(relative).parts
                or not (re.fullmatch(r'blender_bridge/[a-z_][a-z_0-9]*\.py', relative)
                    or re.fullmatch(r'worker_support/ucc/(?:[a-z_][a-z_0-9]*/)*[a-z_][a-z_0-9]*\.py', relative)
                    or relative in resources)
                or type(record) is not dict or set(record) != {'bytes', 'sha256'}
                or type(record['bytes']) is not int or not 0 <= record['bytes'] <= 2 * 1024 * 1024
                or type(record['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])):
            raise WorkerPayloadError('Invalid worker payload path or byte binding')
        path = _file(base, relative, 2 * 1024 * 1024)
        data = path.read_bytes()
        if len(data) != record['bytes'] or sha256(data).hexdigest() != record['sha256']:
            raise WorkerPayloadError('Worker payload content changed: ' + relative)
        paths.append(path)
    names = set(raw['files'])
    required = {'blender_bridge/entrypoint.py', 'blender_bridge/payload_contract.py',
        SUPPORT + '/ucc/__init__.py', SUPPORT + '/ucc/core/worker_payload.py'}
    required.update(resources)
    if not required <= names:
        raise WorkerPayloadError('Worker payload is incomplete')
    for name in raw['modules']:
        module = SUPPORT + '/' + name.replace('.', '/')
        if not {module + '.py', module + '/__init__.py'} & names:
            raise WorkerPayloadError('Worker payload module is absent')
    if raw['files']['blender_bridge/payload_contract.py'] != raw['files'][SUPPORT + '/ucc/core/worker_payload.py']:
        raise WorkerPayloadError('Worker payload validator copies differ')
    # A bytecode cache can bypass the checked Python source. The worker disables
    # cache writes before loading this module. Never accept unlisted import data.
    observed = {str(p.relative_to(base)).replace('\\', '/')
        for directory in (base / 'blender_bridge', base / SUPPORT)
        for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    if observed != names | {SUPPORT + '/' + MANIFEST}:
        raise WorkerPayloadError('Worker payload contains unlisted files or bytecode')
    return (manifest, *paths)


def activate_worker_payload(base: Path) -> Path:
    """Activate only checked sources in a fresh Blender process."""
    validate_worker_payload(base)
    support = Path(base) / SUPPORT
    for name, module in tuple(sys.modules.items()):
        if name == 'ucc' or name.startswith('ucc.'):
            origin = getattr(module, '__file__', None)
            if origin is None or not Path(origin).resolve().is_relative_to(support):
                raise WorkerPayloadError('An unrelated UCC package was already imported')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(support))
    return support
