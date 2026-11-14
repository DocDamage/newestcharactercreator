"""Compose existing body workers and strict facial workers before one publication.

The scratch project is an explicit private transaction, never the user's saved
project. Intermediate body-only metadata is permitted only there. The original
facial intent and pointer remain authoritative until the entire build passes.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .body_revision import apply_saved_body_revision, BodyRevisionResult
from .humanoid_generation import generate_humanoid, HumanoidGeneration
from .face_revision import apply_saved_face_revision, bundled_face_assets
from .master_preview import _master_file, _digest


@dataclass(frozen=True, slots=True)
class CustomizedHumanoidBuild:
    revision: MasterRevision
    body_observed: dict
    face_observed: dict
    private_transaction: Path


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Customized humanoid build cancelled; old master remains authoritative')


def _scratch(store, initial, *, source, cancel):
    jobs = store.root/'.ucc-jobs'
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError('Customized humanoid jobs path is redirected')
    root = jobs/('custom-build-'+str(uuid4()))
    scratch = ProjectStore(root)
    project = replace(CharacterProject.new(initial.name), parameters=initial.parameters)
    project = scratch.save(project)
    if source is not None:
        path, sha = source
        staged = stage_unverified_master(scratch, path, authorized_source_root=path.parent,
                                        expected_project_id=project.project_id,
                                        expected_revision=project.revision, expected_sha256=sha, cancel=cancel)
        project = staged.project
    return scratch, project


def _face(scratch, initial, common, data_dir):
    current = scratch.load()
    intent = replace(current, schema_version=2, facial_parameters=initial.facial_parameters,
                     revision=current.revision+1, geometry_state='generated_unverified')
    intent = scratch.save(intent, expected_revision=current.revision)
    return apply_saved_face_revision(
        scratch, **common, mpfb_data_dir=data_dir, expected_project_id=intent.project_id,
        expected_revision=intent.revision, expected_master_blend=intent.master_blend)


def _build(store, *, refit, blender_exe, worker_script, mpfb_data_dir,
           expected_project_id, expected_revision, expected_master_blend=None, cancel=None, timeout_s=300):
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id or initial.revision != expected_revision
            or (refit and initial.master_blend != expected_master_blend)):
        raise ProjectConflict('Project changed while preparing customized humanoid build')
    common = dict(blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s)
    if initial.expression is not None:
        raise ValidationError('Prepared facial controls require expression-aware composition; the saved master is unchanged')
    if not initial.facial_parameters:
        if refit:
            return apply_saved_body_revision(store, **common, expected_project_id=expected_project_id,
                                             expected_revision=expected_revision,
                                             expected_master_blend=expected_master_blend)
        return generate_humanoid(store, **common, expected_project_id=expected_project_id,
                                 expected_revision=expected_revision)
    if initial.family != 'humanoid.v1' or initial.base_provider != 'mpfb' or initial.parts or initial.animations:
        raise ValidationError('Customized build supports only unattached MPFB humanoids')
    if type(timeout_s) not in (int, float) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Customized build timeout_s outside supported range')
    _cancel(cancel)
    bundled_face_assets(Path(mpfb_data_dir), cancel)
    source = _master_file(store, initial.master_blend) if initial.master_blend else None
    if source and _digest(source[0], cancel) != source[1]:
        raise ProjectStorageError('Customized source master does not match its immutable filename')
    if refit and source is None:
        raise ValidationError('Save an existing master before customized body refit')
    scratch, current = _scratch(store, initial, source=source if refit else None, cancel=cancel)
    if refit:
        # Validate the original source through actual independent facial workers
        # BEFORE the legacy body refit can adjust any rest bones.
        _face(scratch, initial, common, mpfb_data_dir)
        current = scratch.load()
        body_projection = replace(current, schema_version=1, facial_parameters=(), revision=current.revision+1)
        current = scratch.save(body_projection, expected_revision=current.revision)
        body = apply_saved_body_revision(scratch, **common, expected_project_id=current.project_id,
                                         expected_revision=current.revision, expected_master_blend=current.master_blend)
    else:
        body = generate_humanoid(scratch, **common, expected_project_id=current.project_id,
                                 expected_revision=current.revision)
    face = _face(scratch, initial, common, mpfb_data_dir)
    final, final_sha = _master_file(scratch, face.project.master_blend)
    if _digest(final, cancel) != final_sha:
        raise ProjectStorageError('Customized final master changed before publication')
    if source and _digest(source[0], cancel) != source[1]:
        raise ProjectStorageError('Customized original master changed during private build')
    bundled_face_assets(Path(mpfb_data_dir), cancel)
    if store.load() != initial:
        raise ProjectConflict('Project changed during customized build; private result remains unpublished')
    _cancel(cancel)
    revision = stage_unverified_master(store, final, authorized_source_root=scratch.root,
                                       expected_project_id=expected_project_id, expected_revision=expected_revision,
                                       expected_sha256=final_sha, cancel=cancel)
    return CustomizedHumanoidBuild(revision, body.observed, face.observed, scratch.root)


def generate_customized_humanoid(
    store: ProjectStore, *, blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
    expected_project_id: str, expected_revision: int, cancel: Event | None = None, timeout_s: float = 300,
) -> HumanoidGeneration | CustomizedHumanoidBuild:
    return _build(store, refit=False, blender_exe=blender_exe, worker_script=worker_script,
                  mpfb_data_dir=mpfb_data_dir, expected_project_id=expected_project_id,
                  expected_revision=expected_revision, cancel=cancel, timeout_s=timeout_s)


def apply_saved_customized_body_revision(
    store: ProjectStore, *, blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
    expected_project_id: str, expected_revision: int, expected_master_blend: str,
    cancel: Event | None = None, timeout_s: float = 300,
) -> BodyRevisionResult | CustomizedHumanoidBuild:
    return _build(store, refit=True, blender_exe=blender_exe, worker_script=worker_script,
                  mpfb_data_dir=mpfb_data_dir, expected_project_id=expected_project_id,
                  expected_revision=expected_revision, expected_master_blend=expected_master_blend,
                  cancel=cancel, timeout_s=timeout_s)
