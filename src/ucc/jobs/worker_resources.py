"""Locate trusted worker data in a checkout or validated frozen payload."""
from pathlib import Path
import sys

from ucc.core.errors import ValidationError
from ucc.core.worker_payload import validate_worker_payload, WorkerPayloadError, SUPPORT, ADAPTER, ADAPTER_FILES
from ucc.core.worker_payload import STATIC_ADAPTER
from ucc.core.worker_payload import UNITY_ADAPTER,UNITY_ADAPTER_FILES


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
