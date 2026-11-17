"""Explicit saved proof choices and captured local images; no execution grant."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol

from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_sha
from .godot_registered_runtime_contract import RegisteredInputSelection


@dataclass(frozen=True, slots=True)
class SelectedProofFile:
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.is_absolute() or '..' in self.path.parts:
            raise ValidationError('Select an explicit absolute saved proof file')
        checked_sha(self.sha256)


@dataclass(frozen=True, slots=True)
class CapturedPreviewFrame:
    frame: int
    png_bytes: bytes
    rgba_sha256: str
    opaque_pixels: int
    opaque_bounds: tuple[int, int, int, int]
    max_normal_vector_error: float


class PreviewGuard(Protocol):
    def __call__(self, *, cancel: Event | None = None, timeout_s: float = 300) -> None: ...


@dataclass(frozen=True, slots=True)
class LoadedSavedGodotPreview:
    draw_id: str
    selection: RegisteredInputSelection
    draw_receipt: SelectedProofFile
    body_receipt: SelectedProofFile
    retained_manifest: SelectedProofFile
    frames: tuple[CapturedPreviewFrame, ...]
    database_path: Path
    watch_paths: tuple[Path, ...]
    watched_identities: tuple[tuple[Path, tuple[int, int, int, int]], ...]
    guard: PreviewGuard

    @property
    def engine_import_verified(self) -> bool:
        return False

    @property
    def visual_quality_approved(self) -> bool:
        return False
