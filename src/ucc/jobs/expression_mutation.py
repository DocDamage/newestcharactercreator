"""Preserve prepared neutral keys through real private body/face transactions."""
from dataclasses import replace
import math
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.master_versions import stage_unverified_master
from .expression_inspection import _inspect_expression_copy
from .expression_keys import installed_expression_inputs, stage_expression_keys
from .expression_revisions import publish_expression_receipt, read_expression_receipt, admit_expression_source
from .expression_storage import check_cancel, safe_directory, install_master_copy
from .expression_verification import registered_expression_source, verify_saved_expression_master
from .master_preview import _master_file, _digest


def preserve_expressions(store: ProjectStore, *, operation: str, blender_exe: Path, worker_script: Path,
                          mpfb_data_dir: Path, expected_project_id: str, expected_revision: int,
                          expected_master_blend: str, cancel: Event | None = None, timeout_s: float = 300):
    from .customized_humanoid import CustomizedHumanoidBuild, _face
    from .body_revision import apply_saved_body_revision
    from .humanoid_generation import generate_humanoid
    from .face_revision import FaceRevisionResult, apply_saved_face_revision, bundled_face_assets
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before expression-aware editing')
    if (initial.expression is None or initial.master_blend is None or initial.family != 'humanoid.v1'
            or initial.base_provider != 'mpfb' or initial.parts or initial.animations):
        raise ValidationError('Expression-aware body/face editing requires a prepared unattached MPFB master; restore Original hand first')
    if operation not in {'body_generation', 'body_refit', 'face_revision'}:
        raise ValidationError('Unknown expression-preserving operation')
    if type(timeout_s) not in (int, float) or not .05 <= timeout_s <= 3600 or not math.isfinite(timeout_s):
        raise ValidationError('Expression-aware timeout_s is outside the supported range')
    if operation == 'face_revision' and not initial.facial_parameters:
        raise ValidationError('Save explicit facial intent before an expression-aware face revision')
    common = dict(blender_exe=blender_exe, worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
                  cancel=cancel, timeout_s=timeout_s)
    metadata_sha = _digest(store.file, cancel)
    before = verify_saved_expression_master(store, **common, expected_project_id=initial.project_id,
        expected_revision=initial.revision, expected_master_blend=initial.master_blend)
    library, _ = registered_expression_source(store, initial, cancel)
    root = safe_directory(store, '.ucc-jobs', create=True)/('expression-edit-'+str(uuid4()))
    root.mkdir(exist_ok=False); scratch = ProjectStore(root)
    generate = operation == 'body_generation'
    if not generate:
        install_master_copy(scratch, before.master, before.sha256, before.master.parent, cancel)
    private = scratch.save(replace(initial, revision=0, schema_version=2 if initial.facial_parameters else 1,
        expression=None, master_blend=None if generate else initial.master_blend, rig_profile=None,
        geometry_state='not_generated' if generate else 'generated_unverified'))
    expected = dict(expected_project_id=private.project_id, expected_revision=private.revision)
    body = None; face = None
    if operation == 'face_revision':
        edited = apply_saved_face_revision(scratch, **common, **expected, expected_master_blend=private.master_blend)
    else:
        # Compose the existing low-level workers in THIS private transaction.
        # A nested customized transaction can exceed Blender's Windows path
        # limits, even though the host Python can read the exact staged bytes.
        runtime = dict(blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s)
        if not generate and initial.facial_parameters:
            _face(scratch, initial, runtime, mpfb_data_dir)
        current = scratch.load()
        if current.facial_parameters:
            current = scratch.save(replace(current, schema_version=1, facial_parameters=(),
                                           revision=current.revision+1), expected_revision=current.revision)
        expected = dict(expected_project_id=current.project_id, expected_revision=current.revision)
        if generate:
            body = generate_humanoid(scratch, **runtime, **expected)
        else:
            body = apply_saved_body_revision(scratch, **runtime, **expected,
                                             expected_master_blend=current.master_blend)
        if initial.facial_parameters:
            face = _face(scratch, initial, runtime, mpfb_data_dir)
    current = scratch.load(); final_relative = current.master_blend
    if generate:
        keys = stage_expression_keys(scratch, source_master_blend=final_relative, **common)
        install_master_copy(scratch, keys.scene, keys.sha256, keys.scene.parent, cancel)
        final_relative = 'master/versions/'+keys.sha256+'.blend'
    checked = _inspect_expression_copy(scratch, master_blend=final_relative, **common)

    def recheck() -> None:
        check_cancel(cancel)
        if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
            raise ProjectConflict('Project changed during expression-aware editing; old master remains authoritative')
        registered_expression_source(store, initial, cancel)
        original, _ = _master_file(store, initial.master_blend)
        if _digest(original, cancel) != before.sha256:
            raise ProjectStorageError('Original expression master changed before publication')
        for path, sha in ((checked.master, checked.sha256), (checked.report, checked.report_sha256)):
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != sha:
                raise ProjectStorageError('Verified expression-preserving output changed before publication')
        installed_expression_inputs(mpfb_data_dir, cancel)
        if initial.facial_parameters: bundled_face_assets(mpfb_data_dir, cancel)

    recheck()
    extra = {'expression_preservation': checked.observed, 'original_master_preserved': True}
    if operation == 'face_revision' and edited.revision is None:
        if checked.sha256 != before.sha256:
            raise ProjectStorageError('Verified facial no-op unexpectedly changed the prepared master')
        return FaceRevisionResult(initial, None, {**edited.observed, **extra}, edited.stage_job_id, edited.reopen_job_id)
    receipt = None
    if checked.sha256 != before.sha256:
        receipt = publish_expression_receipt(store, library, before.sha256, checked, operation, cancel)

    def at_commit() -> None:
        recheck()
        if receipt is not None and read_expression_receipt(store, library, checked.sha256, cancel) != receipt:
            raise ProjectStorageError('Expression revision registration changed before atomic commit')
        admit_expression_source(store, library, checked.sha256, cancel)

    revision = stage_unverified_master(store, checked.master, authorized_source_root=scratch.root,
        expected_project_id=initial.project_id, expected_revision=initial.revision, expected_project=initial,
        expected_sha256=checked.sha256, cancel=cancel, before_project_save=at_commit)
    if operation == 'face_revision':
        return FaceRevisionResult(revision.project, revision, {**edited.observed, **extra,
            'authoritative_master_sha256': checked.sha256}, edited.stage_job_id, edited.reopen_job_id)
    return CustomizedHumanoidBuild(revision, {**body.observed, **extra},
                                    {} if face is None else face.observed, scratch.root)
