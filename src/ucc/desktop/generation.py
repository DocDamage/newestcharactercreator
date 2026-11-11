"""Desktop binding for UCC's existing isolated Blender worker.

The source and frozen builds must both ship the exact trusted bridge script.
This module never installs Blender/MPFB, selects an executable without user
action, or starts a job on import.
"""
from __future__ import annotations

from pathlib import Path
import sys
from threading import Event

from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.jobs.humanoid_generation import HumanoidGeneration, generate_humanoid
from ucc.jobs.master_preview import MasterPreview, preview_saved_master


def bundled_worker_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[3]
    worker = base / "blender_bridge" / "entrypoint.py"
    service = worker.parent / "mpfb_service.py"
    preview = worker.parent / "preview_export.py"
    if (not worker.is_file() or worker.is_symlink()
            or not service.is_file() or service.is_symlink()
            or not preview.is_file() or preview.is_symlink()):
        raise ValidationError(
            "Blender worker bridge is unavailable. Run from the repo checkout "
            "or a complete Windows alpha archive."
        )
    return worker


def generate_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    cancel: Event,
) -> HumanoidGeneration:
    return generate_humanoid(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        cancel=cancel, timeout_s=300,
    )


def preview_master_from_desktop(
    store: ProjectStore,
    *,
    blender_exe: Path,
    project_id: str,
    revision: int,
    master_blend: str,
    cancel: Event,
) -> MasterPreview:
    return preview_saved_master(
        store, blender_exe=blender_exe, worker_script=bundled_worker_path(),
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel, timeout_s=300,
    )
