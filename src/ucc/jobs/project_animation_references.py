"""Atomic source-only reference transactions; the editable master is read only."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ucc.animations.project_references import MAX_PROJECT_REFERENCES
from ucc.core.commands import CharacterSession
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from .animation_reference_storage import check_registered_source, publish_source_binding
from .catalog_clip import verify_catalog_fbx_clip, _saved_reference
from .master_preview import _master_file, _digest
from .neutral_master import NeutralMasterInspection, inspect_saved_neutral_master


@dataclass(frozen=True, slots=True)
class AnimationReferenceResult:
    project: CharacterProject
    clip_id: str
    operation: str
    changed: bool
    binding: dict | None
    neutral: NeutralMasterInspection | None


def _context(store, expected_project_id, expected_revision, expected_master_blend, cancel):
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before animation-reference transaction')
    if initial.master_blend is None:
        raise ValidationError('Generate and save a neutral MPFB master before attaching references')
    master, master_sha = _master_file(store, initial.master_blend)
    metadata_sha = _digest(store.file, cancel)
    def unchanged():
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError('Animation-reference transaction cancelled; project unchanged')
        current, sha = _master_file(store, initial.master_blend)
        if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
            raise ProjectConflict('Project changed during animation-reference transaction')
        if current != master or sha != master_sha or _digest(current, cancel) != master_sha:
            raise ProjectStorageError('Editable master changed during animation-reference transaction')
    unchanged()
    return initial, master_sha, metadata_sha, unchanged


def _neutral(store, initial, master_sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s):
    result = inspect_saved_neutral_master(store, blender_exe=blender_exe, worker_script=worker_script,
        expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_master_blend=initial.master_blend, cancel=cancel, timeout_s=timeout_s)
    if (result.project_id != initial.project_id or result.revision != initial.revision
            or result.master_sha256 != master_sha or result.project_metadata_sha256 != metadata_sha):
        raise ProjectConflict('Neutral observation belongs to another project snapshot')
    return result


def attach_catalog_reference(store: ProjectStore, database_path: Path, clip_id: str, *,
                              expected_source_sha256: str, expected_policy: LicensePolicy,
                              blender_exe: Path, worker_script: Path, expected_project_id: str,
                              expected_revision: int, expected_master_blend: str,
                              cancel: Event | None = None, timeout_s: float = 300) -> AnimationReferenceResult:
    initial, master_sha, metadata_sha, unchanged = _context(
        store, expected_project_id, expected_revision, expected_master_blend, cancel)
    session = CharacterSession(initial); proposed = session.attach_animation_reference(clip_id)
    if len(proposed.animations) > MAX_PROJECT_REFERENCES:
        raise ValidationError('This reference policy supports up to 128 sources per character')
    if not isinstance(expected_policy, LicensePolicy):
        raise ValidationError('Select the exact reviewed source policy')
    allowed, reason = expected_policy.allow('local_preview')
    if not allowed: raise AssetPolicyError(reason)
    _saved_reference(database_path, clip_id, expected_source_sha256, expected_policy)
    for existing in initial.animations:
        check_registered_source(store, database_path, initial.project_id, existing, cancel)
    neutral = _neutral(store, initial, master_sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s)
    unchanged()
    source = verify_catalog_fbx_clip(database_path, clip_id, expected_source_sha256=expected_source_sha256,
        expected_policy=expected_policy, blender_exe=blender_exe, worker_script=worker_script,
        jobs_root=store.root/'.ucc-jobs', cancel=cancel, timeout_s=timeout_s)
    if (source.clip_id != clip_id or source.source_sha256 != expected_source_sha256
            or source.license_policy != expected_policy):
        raise ProjectStorageError('Fresh source verification belongs to a different reference or policy')
    unchanged()
    binding = publish_source_binding(store, initial.project_id, source, cancel)
    for existing in proposed.animations:
        check_registered_source(store, database_path, initial.project_id, existing, cancel)
    unchanged()
    if proposed == initial:
        return AnimationReferenceResult(initial, clip_id, 'attach', False, binding, neutral)
    saved = store.save(proposed, expected_revision=initial.revision, expected_project=initial)
    return AnimationReferenceResult(saved, clip_id, 'attach', True, binding, neutral)


def detach_catalog_reference(store: ProjectStore, clip_id: str, *, blender_exe: Path, worker_script: Path,
                              expected_project_id: str, expected_revision: int, expected_master_blend: str,
                              cancel: Event | None = None, timeout_s: float = 300) -> AnimationReferenceResult:
    initial, master_sha, metadata_sha, unchanged = _context(
        store, expected_project_id, expected_revision, expected_master_blend, cancel)
    session = CharacterSession(initial); proposed = session.detach_animation_reference(clip_id)
    if proposed == initial:
        return AnimationReferenceResult(initial, clip_id, 'detach', False, None, None)
    # Removing an ID cannot be used to hide a real Action from the old edit guards.
    neutral = _neutral(store, initial, master_sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s)
    unchanged()
    saved = store.save(proposed, expected_revision=initial.revision, expected_project=initial)
    # Immutable source bindings remain available for undo, redo and old revisions.
    return AnimationReferenceResult(saved, clip_id, 'detach', True, None, neutral)
