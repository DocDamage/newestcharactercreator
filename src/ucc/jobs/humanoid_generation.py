"""Real MPFB humanoid generation, independent Blender reopen, safe project staging.

This is the sole application coordinator for the first humanoid vertical slice.
It never marks geometry "validated": inspecting saved meshes/bones does not
prove skinning, morph deformation, retargeting or game-engine compatibility.
The worker runs offline using the Blender executable the user explicitly chose.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Any

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.storage import ProjectStore

from .geometry_evidence import EvidenceError, verify_geometry
from .phenotype import from_saved_parameters, verify_evaluated_shape
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class HumanoidGeneration:
    """Result of two real Blender processes and a completed project pointer swap."""
    revision: MasterRevision
    observed: dict[str, Any]
    create_job_id: str
    inspect_job_id: str

    @property
    def geometry_state(self) -> str:
        return self.revision.project.geometry_state


def _sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cancelled(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise ProjectStorageError("Humanoid generation cancelled; no master was committed")


def generate_humanoid(
    store: ProjectStore,
    *,
    blender_exe: Path,
    worker_script: Path,
    expected_project_id: str,
    expected_revision: int,
    cancel: Event | None = None,
    timeout_s: float = 300,
) -> HumanoidGeneration:
    """Generate, independently inspect, then stage an immutable master.

    The store's revision/project identity is captured *before* the long worker
    run and rechecked at staging. Any competing editor save makes promotion
    fail closed. Old masters and project metadata remain authoritative on error.
    The private .ucc-jobs folder retains failed worker logs for local diagnosis;
    it is never included in published artifacts.
    """
    initial = store.load()
    if not isinstance(expected_project_id, str) or initial.project_id != expected_project_id:
        raise ProjectConflict("Selected character project is not the saved project")
    if type(expected_revision) is not int or initial.revision != expected_revision:
        raise ProjectConflict("Project changed since the generation task was prepared")
    if initial.family != "humanoid.v1" or initial.base_provider != "mpfb":
        raise ValidationError("Only the MPFB humanoid family is supported by this worker")
    if initial.parts or initial.animations:
        raise ValidationError(
            "Cannot regenerate a new base while character parts or animation "
            "references are attached; create a clean project for this operation"
        )
    macros = from_saved_parameters(initial.parameters)
    if type(timeout_s) not in (int, float) or not 0.05 <= timeout_s <= 3600:
        raise ValidationError("timeout_s must be between 0.05 and 3600 seconds")

    executable = Path(blender_exe)
    script = Path(worker_script)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("Select an installed, regular Blender executable")
    if script.is_symlink() or not script.is_file():
        raise ValidationError("Bundled Blender bridge script is missing or redirected")
    _cancelled(cancel)

    root = store.root
    jobs_root = root / ".ucc-jobs"
    if jobs_root.is_symlink() or not jobs_root.resolve(strict=False).is_relative_to(root):
        raise ProjectStorageError("Private Blender job directory is redirected")

    runner = BlenderJobRunner(executable, jobs_root, script)
    create_job = JobRequest.new(
        "create_human", options={"macro_parameters": macros},
    )
    created, create_dir = runner.run(create_job, timeout_s=timeout_s, cancel=cancel)
    if created.details.get("staged_blend") != "generated_human.blend":
        raise EvidenceError("Worker returned an unrecognized generated master path")
    master = create_dir / "generated_human.blend"
    if master.is_symlink() or not master.is_file() or master.stat().st_size < 1024:
        raise EvidenceError("Creation produced no substantial real Blender master")
    digest = _sha256(master)
    _cancelled(cancel)

    inspect_job = JobRequest.new(
        "inspect_character", input_project="candidate.blend",
        options={"macro_parameters": macros},
    )
    reopened, inspect_dir = runner.run(
        inspect_job, timeout_s=timeout_s, cancel=cancel,
        staged_inputs={"candidate.blend": master},
    )
    inspected_copy = inspect_dir / "candidate.blend"
    if (inspected_copy.is_symlink() or not inspected_copy.is_file()
            or _sha256(inspected_copy) != digest or _sha256(master) != digest):
        raise EvidenceError("Inspected Blender file differs from generated master")
    observed = verify_geometry(created.details, reopened.details)
    observed.update(verify_evaluated_shape(macros, created.details, reopened.details))
    _cancelled(cancel)

    revision = stage_unverified_master(
        store, master, authorized_source_root=create_dir,
        expected_project_id=expected_project_id,
        expected_revision=expected_revision,
        expected_sha256=digest,
        cancel=cancel,
    )
    return HumanoidGeneration(revision, observed, create_job.job_id, inspect_job.job_id)
