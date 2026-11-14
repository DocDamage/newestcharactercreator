"""Project-bound static 3D preview of a real saved Blender humanoid.

No Qt/bpy imports. Export occurs through the existing isolated Blender worker,
using an immutable master only as an input to an on-demand private conversion.
The generated GLB is diagnostic-only, never a certified engine export.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from threading import Event

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import MAX_BLEND_BYTES
from ucc.core.storage import ProjectStore
from ucc.preview.glb_mesh import MAX_SOURCE_BYTES, PreviewMesh, load_glb_preview

from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class MasterPreview:
    mesh: PreviewMesh
    project_id: str
    revision: int
    master_blend: str
    master_sha256: str
    glb_sha256: str
    selected_vertex_count: int
    blender_version: str
    full_surface: bool = False

    @property
    def certified_for_engine_import(self) -> bool:
        return False


def _digest(path: Path, cancel: Event | None = None) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            _check_cancel(cancel)
            h.update(block)
    return h.hexdigest()


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("Saved-master preview cancelled; no project data modified")


def _master_file(store: ProjectStore, relative: str) -> tuple[Path, str]:
    """Accept only safe content-addressed masters, never arbitrary external .blend."""
    match = re.fullmatch(r"master/versions/([a-f0-9]{64})\.blend", relative)
    if match is None:
        raise ValidationError("Preview requires an immutable content-addressed UCC master")
    root = store.root
    if any((root / part).is_symlink() for part in ("master", "master/versions", relative)):
        raise ProjectStorageError("Saved master or parent directory is redirected")
    source = root / relative
    if source.is_symlink() or not source.is_file():
        raise ProjectStorageError("Saved master is missing or a symlink")
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ProjectStorageError("Saved master escaped the project directory")
    size = resolved.stat().st_size
    if not 1024 <= size <= MAX_BLEND_BYTES:
        raise ProjectStorageError("Saved master exceeds preview size limits")
    with resolved.open("rb") as stream:
        if stream.read(7) != b"BLENDER":
            raise ProjectStorageError("Saved master is not an uncompressed Blender file")
    return resolved, match.group(1)


def preview_saved_master(
    store: ProjectStore,
    *,
    blender_exe: Path,
    worker_script: Path,
    expected_project_id: str,
    expected_revision: int,
    expected_master_blend: str,
    cancel: Event | None = None,
    timeout_s: float = 300,
    full_surface: bool = False,
) -> MasterPreview:
    """Read and preview the selected saved master without changing project JSON."""
    project = store.load()
    if type(full_surface) is not bool:
        raise ValidationError('Full static preview selection must be explicit Boolean')
    if (project.project_id != expected_project_id or
            project.revision != expected_revision or
            project.master_blend != expected_master_blend):
        raise ProjectConflict("Project changed; reopen it before previewing its master")
    if type(timeout_s) not in (int, float) or not 0.05 <= timeout_s <= 3600:
        raise ValidationError("Invalid Blender preview worker timeout")
    exe, script = Path(blender_exe), Path(worker_script)
    if exe.is_symlink() or not exe.is_file():
        raise ValidationError("Select a real installed Blender executable")
    if script.is_symlink() or not script.is_file():
        raise ValidationError("UCC Blender worker script is missing or redirected")
    _check_cancel(cancel)

    master, expected_hash = _master_file(store, expected_master_blend)
    if _digest(master, cancel) != expected_hash:
        raise ProjectStorageError("Content-addressed master digest mismatch; no preview generated")
    work_root = store.root / ".ucc-jobs"
    if work_root.is_symlink() or not work_root.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError("Private Blender job directory is redirected")

    runner = BlenderJobRunner(exe, work_root, script)
    job = JobRequest.new("export_preview_glb", input_project="candidate.blend")
    outcome, directory = runner.run(job, timeout_s=timeout_s, cancel=cancel,
                                    staged_inputs={"candidate.blend": master})
    details = outcome.details
    if (details.get("staged_glb") != "preview.glb" or
            details.get("static_only") is not True or
            details.get("evaluated_geometry_baked") is not True or
            details.get("animation_exported") is not False or
            details.get("skinning_exported") is not False or
            details.get("textures_included") is not False or
            details.get("engine_import_verified") is not False or
            type(details.get("selected_vertex_count")) is not int or
            details["selected_vertex_count"] <= 100 or
            type(details.get("selected_mesh_count")) is not int or
            not 1 <= details["selected_mesh_count"] <= 64 or
            not isinstance(details.get("blender_version"), str) or
            not details["blender_version"]):
        raise ProjectStorageError("Blender preview worker returned invalid or unsafe evidence")

    copied_master = directory / "candidate.blend"
    output = directory / "preview.glb"
    if (copied_master.is_symlink() or not copied_master.is_file() or
            _digest(copied_master, cancel) != expected_hash):
        raise ProjectStorageError("Blender preview used a different master revision")
    if output.is_symlink() or not output.is_file() or not (
        20 < output.stat().st_size <= MAX_SOURCE_BYTES
    ):
        raise ProjectStorageError("Blender preview GLB is missing or oversized")
    _check_cancel(cancel)
    mesh = load_glb_preview(output, full_surface=True) if full_surface else load_glb_preview(output)
    if mesh.source_face_count == 0:
        raise ProjectStorageError("Blender preview contains no displayable mesh faces")
    glb_hash = _digest(output, cancel)

    # An external editor may save another project revision while Blender runs.
    current = store.load()
    if (current.project_id != expected_project_id or
            current.revision != expected_revision or
            current.master_blend != expected_master_blend or
            _digest(master, cancel) != expected_hash):
        raise ProjectConflict("Saved master or project changed during preview; discard old preview")
    return MasterPreview(mesh, project.project_id, project.revision, expected_master_blend,
                         expected_hash, glb_hash, details["selected_vertex_count"],
                         details["blender_version"], full_surface)
