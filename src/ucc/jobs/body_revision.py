"""Save a modified MPFB body as a new immutable revision of an EXISTING master.

Only a fixed, already-installed Blender/MPFB worker is invoked. This avoids
rebuilding the original rig and preserves the exact source .blend bytes.
Rig/weight integrity and shape evidence are checked before pointer promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.storage import ProjectStore

from .geometry_evidence import EvidenceError
from .master_preview import _digest, _master_file
from .phenotype import from_saved_parameters, verify_evaluated_shape, verify_macro_report
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class BodyRevisionResult:
    revision: MasterRevision
    observed: dict[str, Any]
    refit_job_id: str
    reopen_job_id: str


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError("MPFB body refit cancelled; old master remains authoritative")


def _validated_rig(created: Any, reopened: Any) -> dict[str, Any]:
    if not isinstance(created, dict) or not isinstance(reopened, dict):
        raise EvidenceError("Missing MPFB existing-rig inspection details")
    before = created.get("previous_rig")
    after = created.get("updated_rig")
    reread = reopened.get("rig_binding")
    if not all(isinstance(x, dict) for x in (before, after, reread)):
        raise EvidenceError("No Blender rig-binding evidence was produced")
    if after != reread:
        raise EvidenceError("Refitted armature weights/rest pose changed during independent reopen")
    for field in ("bone_count", "bone_names", "bone_weight_groups",
                  "weighted_vertices", "weight_sha256", "armature_modifier_count"):
        if before.get(field) != after.get(field):
            raise EvidenceError("Refit unexpectedly lost original rig weight data: " + field)
    if (after.get("rig_binding_verified") is not True or
            after.get("animation_deformation_verified") is not False or
            type(after.get("bone_count")) is not int or after["bone_count"] < 5 or
            type(after.get("weighted_vertices")) is not int or
            after["weighted_vertices"] <= 100):
        raise EvidenceError("Refit rig-binding proof is insufficient")
    return {
        "rig_binding_verified": True,
        "reopened_bones": after["bone_count"],
        "weighted_vertices": after["weighted_vertices"],
        "weight_sha256": after["weight_sha256"],
        "rig_rest_sha256": after["rig_rest_sha256"],
        "previous_rig_rest_sha256": before["rig_rest_sha256"],
        "animation_deformation_verified": False,
    }


def apply_saved_body_revision(
    store: ProjectStore,
    *,
    blender_exe: Path,
    worker_script: Path,
    expected_project_id: str,
    expected_revision: int,
    expected_master_blend: str,
    cancel: Event | None = None,
    timeout_s: float = 300,
) -> BodyRevisionResult:
    """Refit existing master; re-open copy; atomically save a *new* master pointer."""
    initial = store.load()
    if (initial.project_id != expected_project_id or
            initial.revision != expected_revision or
            initial.master_blend != expected_master_blend):
        raise ProjectConflict("Project changed while preparing saved MPFB body refit")
    if initial.family != "humanoid.v1" or initial.base_provider != "mpfb":
        raise ValidationError("Body refit supports only saved MPFB humanoid projects")
    if initial.parts or initial.animations:
        raise ValidationError("Body refit with external parts/animations is not validated yet")
    if initial.expression is not None:
        raise ValidationError('Prepared facial controls require expression-aware body refit; the saved master is unchanged')
    if initial.facial_parameters:
        raise ValidationError("Saved facial intent requires face-aware refit; body-only refit cannot discard it")
    if type(timeout_s) not in (int, float) or not 0.05 <= timeout_s <= 3600:
        raise ValidationError("timeout_s outside supported range")
    macro = from_saved_parameters(initial.parameters)
    executable, script = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("Select an existing installed Blender executable")
    if script.is_symlink() or not script.is_file():
        raise ValidationError("Bundled Blender bridge is missing or redirected")
    _check_cancel(cancel)

    source, source_hash = _master_file(store, expected_master_blend)
    if _digest(source, cancel) != source_hash:
        raise ProjectStorageError("Existing Blender master SHA-256 does not match file name")
    job_root = store.root / ".ucc-jobs"
    if job_root.is_symlink() or not job_root.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError("Private Blender jobs path is redirected")

    runner = BlenderJobRunner(executable, job_root, script)
    change = JobRequest.new(
        "refit_human", input_project="candidate.blend",
        options={"macro_parameters": macro},
    )
    modified, workdir = runner.run(
        change, staged_inputs={"candidate.blend": source}, timeout_s=timeout_s,
        cancel=cancel,
    )
    info = modified.details
    if info.get("staged_blend") != "refitted_human.blend" or info.get("refit_saved") is not True:
        raise EvidenceError("Blender did not report a saved, refitted master")
    verify_macro_report(macro, info.get("macro_parameters_observed"), "refit")
    if not isinstance(info.get("previous_macros"), dict):
        raise EvidenceError("MPFB did not report original master phenotype")

    candidate = workdir / "candidate.blend"
    output = workdir / "refitted_human.blend"
    if (candidate.is_symlink() or not candidate.is_file() or
            _digest(candidate, cancel) != source_hash or
            _digest(source, cancel) != source_hash):
        raise ProjectStorageError("Source Blender master changed during refit")
    if output.is_symlink() or not output.is_file() or output.stat().st_size < 1024:
        raise EvidenceError("Blender produced no refitted .blend file")
    updated_hash = _digest(output, cancel)
    if updated_hash == source_hash:
        raise EvidenceError("Refit produced byte-identical Blender master")

    _check_cancel(cancel)
    inspect = JobRequest.new(
        "inspect_character", input_project="refit_candidate.blend",
        options={"macro_parameters": macro, "verify_rig_binding": True},
    )
    verified, verify_dir = runner.run(
        inspect, staged_inputs={"refit_candidate.blend": output},
        timeout_s=timeout_s, cancel=cancel,
    )
    inspected = verify_dir / "refit_candidate.blend"
    if (inspected.is_symlink() or not inspected.is_file() or
            _digest(inspected, cancel) != updated_hash or
            _digest(output, cancel) != updated_hash or
            _digest(source, cancel) != source_hash):
        raise ProjectStorageError("Refitted master or original changed before validation")
    shape = verify_evaluated_shape(macro, info, verified.details)
    rig = _validated_rig(info, verified.details)
    if (info.get("previous_evaluated_sha256") == shape["macro_evaluated_sha256"] or
            not isinstance(info.get("previous_evaluated_sha256"), str)):
        raise EvidenceError("Saved body macros did not cause measured geometry changes")
    _check_cancel(cancel)

    committed = stage_unverified_master(
        store, output, authorized_source_root=workdir,
        expected_project_id=expected_project_id,
        expected_revision=expected_revision,
        expected_sha256=updated_hash, cancel=cancel,
    )
    return BodyRevisionResult(
        revision=committed,
        observed={
            **shape, **rig, "previous_macros": info["previous_macros"],
            "previous_master_sha256": source_hash,
            "new_master_sha256": updated_hash,
            "refit_method": info.get("refit_method"),
            "original_master_preserved": True,
            "engine_import_verified": False,
        },
        refit_job_id=change.job_id, reopen_job_id=inspect.job_id,
    )
