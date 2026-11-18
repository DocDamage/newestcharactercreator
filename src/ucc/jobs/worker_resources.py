"""Locate trusted worker data in a checkout or validated frozen payload."""
from pathlib import Path
import sys

from ucc.core.errors import ValidationError
from ucc.core.worker_payload import validate_worker_payload, WorkerPayloadError, SUPPORT, ADAPTER, ADAPTER_FILES
from ucc.core.worker_payload import STATIC_ADAPTER
from ucc.core.worker_payload import UNITY_ADAPTER,UNITY_ADAPTER_FILES
from ucc.core.worker_payload import UNITY_REGISTERED_ANIMATION_ADAPTER, UNITY_REGISTERED_ANIMATION_FILES
from ucc.core.worker_payload import (UNITY_REGISTERED_CORRECTION_ADAPTER, UNITY_REGISTERED_CORRECTION_FILES,
    UNITY_REGISTERED_CORRECTION_BINDING)
from ucc.core.worker_payload import UNREAL_ADAPTER,UNREAL_ADAPTER_FILES
from ucc.core.worker_payload import (
    REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES,
    REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES,
    REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES,
)


def worker_dependency_files(worker: Path) -> set[Path]:
    worker = Path(worker)
    base = worker.parent.parent
    if (base / SUPPORT).exists() or (base / SUPPORT).is_symlink() or (worker.parent / 'payload_contract.py').exists():
        try:
            return set(validate_worker_payload(base))
        except (WorkerPayloadError, OSError) as error:
            raise ValidationError('Isolated Blender worker payload is incomplete or changed') from error
    return set(worker.parent.glob('*.py'))


def bundled_native_adapter_path() -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        try:
            validate_worker_payload(base)
        except (WorkerPayloadError, OSError) as error:
            raise ValidationError('Bundled native Godot resources are incomplete or changed') from error
        return base / ADAPTER
    path = Path(__file__).resolve().parents[3] / 'engine_adapters/godot/native_runtime'
    if any((path / name).is_symlink() or not (path / name).is_file() or (path / name).resolve() != path / name for name in ADAPTER_FILES):
        raise ValidationError('Native Godot adapter resources are unavailable')
    return path


def bundled_static_adapter_paths() -> dict[str, Path]:
    """Resolve only first-party static scripts; frozen data must match its manifest."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        try:
            validate_worker_payload(base)
        except (WorkerPayloadError, OSError) as error:
            raise ValidationError('Bundled static Godot resources are incomplete or changed') from error
        root = base / STATIC_ADAPTER
        shared = root / 'ucc_skin_adapter.gd'
    else:
        root = Path(__file__).resolve().parents[3] / 'engine_adapters/godot/static_export'
        shared = root.parent / 'ucc_skin_adapter.gd'
    files = {'configure.gd': root / 'configure.gd', 'inspect.gd': root / 'inspect.gd',
             'ucc_export.gd': root / 'export.gd', 'ucc_skin_adapter.gd': shared}
    if any(path.is_symlink() or not path.is_file() or path.resolve() != path
           or not 0 < path.stat().st_size <= 256 * 1024 for path in files.values()):
        raise ValidationError('Static Godot adapter resources are unavailable')
    return files


def _registered_godot_resources(adapter: str, names: frozenset[str], source_folder: str) -> dict[str, Path]:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        files = {name: base/adapter/name for name in sorted(names)}
        try:
            available = set(validate_worker_payload(base))
        except (WorkerPayloadError, OSError) as error:
            raise ValidationError('Bundled registered Godot resources are incomplete or changed') from error
        if not set(files.values()).issubset(available):
            raise ValidationError('This package does not contain the registered Godot adapter')
    else:
        godot = Path(__file__).resolve().parents[3]/'engine_adapters/godot'
        files = {name: (godot if name == 'ucc_skin_adapter.gd' else godot/source_folder)/name
                 for name in sorted(names)}
    if any(path.is_symlink() or not path.is_file() or path.resolve() != path
           or not 0 < path.stat().st_size <= 256 * 1024 for path in files.values()):
        raise ValidationError('Registered Godot resources are missing, redirected or oversized')
    return files


def bundled_registered_correction_paths() -> dict[str, Path]:
    """Return only the first-party correction code shipped with this app."""
    return _registered_godot_resources(REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES,
                                       'registered_correction')


def bundled_registered_body_paths() -> dict[str, Path]:
    """Return the registered-body engine verification entry points."""
    return _registered_godot_resources(REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES,
                                       'registered_body300')


def bundled_registered_playback_paths() -> dict[str, Path]:
    """Return the private animated-project builder and playback verification code."""
    return _registered_godot_resources(REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES,
                                       'registered_playback')


def bundled_unity_adapter_paths() -> dict[str,Path]:
    """Only enumerated first-party scripts/shaders; manifest validation in frozen apps."""
    if getattr(sys,'frozen',False):
        base=Path(sys._MEIPASS)
        try:validate_worker_payload(base)
        except (WorkerPayloadError,OSError) as error:raise ValidationError('Bundled Unity adapter is incomplete or changed') from error
        root=base/UNITY_ADAPTER
    else:root=Path(__file__).resolve().parents[3]/'engine_adapters/unity'
    files={name:root/name for name in sorted(UNITY_ADAPTER_FILES)}
    if any(path.is_symlink() or not path.is_file() or path.resolve()!=path or not 0<path.stat().st_size<=256*1024 for path in files.values()):
        raise ValidationError('Unity adapter resources are missing, redirected or oversized')
    return files


def bundled_unity_registered_animation_paths() -> dict[str, Path]:
    """Resolve the animated importer and only the static scripts shared with it."""
    shared = bundled_unity_adapter_paths()
    files = _registered_unity_resources({name: ('registered_animation', UNITY_REGISTERED_ANIMATION_ADAPTER)
                                        for name in UNITY_REGISTERED_ANIMATION_FILES})
    files.update({name: shared[name] for name in ('Editor/UccSourceWeights.cs', 'UccNativeMeshIdentity.cs')})
    return files


def bundled_unity_registered_correction_paths() -> dict[str, Path]:
    """Resolve only first-party resources needed to attach the corrected draw path."""
    shared = bundled_unity_adapter_paths()
    sources = {name: ('registered_correction', UNITY_REGISTERED_CORRECTION_ADAPTER)
               for name in UNITY_REGISTERED_CORRECTION_FILES}
    sources[UNITY_REGISTERED_CORRECTION_BINDING] = ('registered_animation', UNITY_REGISTERED_ANIMATION_ADAPTER)
    files = _registered_unity_resources(sources)
    files.update({name: shared[name] for name in ('UccNativeNormals.cs', 'UccQuadSourceData.cs',
                                                 'UccNativeSkinWarmup.shader')})
    return files


def _registered_unity_resources(sources: dict[str, tuple[str, str]]) -> dict[str, Path]:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        files = {name: base/adapter/name for name, (_, adapter) in sorted(sources.items())}
        try:
            available = set(validate_worker_payload(base))
        except (WorkerPayloadError, OSError) as error:
            raise ValidationError('Bundled Unity animation resources are incomplete or changed') from error
        if not set(files.values()).issubset(available):
            raise ValidationError('This package lacks the Unity animation importer')
    else:
        root = Path(__file__).resolve().parents[3]/'engine_adapters/unity'
        files = {name: root/folder/name for name, (folder, _) in sorted(sources.items())}
    if any(path.is_symlink() or not path.is_file() or path.resolve() != path
           or not 0 < path.stat().st_size <= 256 * 1024 for path in files.values()):
        raise ValidationError('Unity animation adapter resources are missing, redirected or oversized')
    return files


def bundled_unreal_adapter_paths() -> dict[str,Path]:
    """Enumerated first-party editor verification sources, never installed SDKs."""
    if getattr(sys,'frozen',False):
        base=Path(sys._MEIPASS)
        try:validate_worker_payload(base)
        except (WorkerPayloadError,OSError) as error:
            raise ValidationError('Bundled Unreal adapter is incomplete or changed') from error
        root=base/UNREAL_ADAPTER
    else:root=Path(__file__).resolve().parents[3]/'engine_adapters/unreal'
    files={name:root/name for name in sorted(UNREAL_ADAPTER_FILES)}
    if any(path.is_symlink() or not path.is_file() or path.resolve()!=path
           or not 0<path.stat().st_size<=256*1024 for path in files.values()):
        raise ValidationError('Unreal adapter sources are missing, redirected or oversized')
    return files
