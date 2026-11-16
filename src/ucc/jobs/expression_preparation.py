"""Compose actual neutral keys and compatible parts, then publish once."""
from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import build_expression_manifest, source_intent
from ucc.core.expressions import ExpressionState
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .expression_hands import verify_existing_hand, rebuild_expression_hand, publish_rebuilt_hand
from .expression_keys import stage_expression_keys, installed_expression_inputs
from .expression_storage import check_cancel, install_master_copy, publish_library, load_expression_library
from .hand_storage import load_hand_library, load_hand_receipt, installed_inputs as installed_hand_inputs
from .master_preview import _digest, _master_file


@dataclass(frozen=True, slots=True)
class ExpressionPreparation:
    project: CharacterProject
    revision: MasterRevision
    library_sha256: str
    observed: dict
    stage_job_id: str
    reopen_job_id: str


def prepare_saved_expressions(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
                              mpfb_data_dir: Path, expected_project_id: str, expected_revision: int,
                              expected_master_blend: str, cancel: Event | None = None,
                              timeout_s: float = 300) -> ExpressionPreparation:
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before expression preparation')
    if initial.expression is not None:
        raise ValidationError('Expressions are already prepared; use the verified expression preview')
    if initial.master_blend is None:
        raise ValidationError('Generate an existing MPFB master before preparing expressions')
    source_intent(initial)  # Closed unanimated humanoid/body/face admission.
    if type(timeout_s) not in (float, int) or not .05 <= timeout_s <= 3600 or not math.isfinite(timeout_s):
        raise ValidationError('Expression timeout_s is outside the supported range')
    check_cancel(cancel)
    source, source_sha = _master_file(store, initial.master_blend)
    if _digest(source, cancel) != source_sha:
        raise ProjectStorageError('Current expression source master differs from its immutable identity')
    metadata_sha = _digest(store.file, cancel)
    common = dict(blender_exe=blender_exe, worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
                  cancel=cancel, timeout_s=timeout_s)
    # Check installed data before the potentially longer existing-hand proof.
    installed_expression_inputs(mpfb_data_dir, cancel)
    previous = verify_existing_hand(store, initial, **common)
    original = source if previous is None else previous.library.source_master
    original_relative = original.relative_to(store.root).as_posix()
    keys = stage_expression_keys(store, source_master_blend=original_relative, **common)
    rebuilt = None if previous is None else rebuild_expression_hand(store, initial, keys, previous, **common)
    output = keys.scene if rebuilt is None else rebuilt.scene
    output_sha = keys.sha256 if rebuilt is None else rebuilt.sha256
    proposed_parts = initial.parts if rebuilt is None else rebuilt.parts
    manifest = build_expression_manifest(source_intent(initial), keys.recipe, keys.sha256,
                                          keys.report_sha256, keys.observation_sha256)
    published_hand = False
    identity = None

    def recheck() -> None:
        check_cancel(cancel)
        installed_expression_inputs(mpfb_data_dir, cancel)
        if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
            raise ProjectConflict('Project changed during expression preparation; old master remains authoritative')
        current_source, _ = _master_file(store, initial.master_blend)
        current_original, _ = _master_file(store, original_relative)
        if (_digest(current_source, cancel) != source_sha
                or _digest(current_original, cancel) != keys.source_sha256):
            raise ProjectStorageError('Expression source changed before atomic publication')
        for path, sha in ((keys.scene, keys.sha256), (keys.report, keys.report_sha256), (output, output_sha)):
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != sha:
                raise ProjectStorageError('Verified expression output changed before atomic publication')
        if previous is not None:
            installed_hand_inputs(mpfb_data_dir, cancel)
            old = load_hand_library(store, previous.library.sha256, cancel)
            receipt = load_hand_receipt(store, old, source_sha, previous.selection, cancel)
            if receipt['observation_sha256'] != previous.observed['observation_sha256']:
                raise ProjectStorageError('Original hand receipt changed during expression preparation')
        if rebuilt is not None:
            current = load_hand_library(rebuilt.scratch, rebuilt.library.sha256, cancel)
            if load_hand_receipt(rebuilt.scratch, current, rebuilt.sha256, previous.selection, cancel) != rebuilt.receipt:
                raise ProjectStorageError('Rebuilt hand receipt changed before publication')
            if published_hand:
                registered = load_hand_library(store, rebuilt.library.sha256, cancel)
                if load_hand_receipt(store, registered, rebuilt.sha256, previous.selection, cancel) != rebuilt.receipt:
                    raise ProjectStorageError('Registered compatible hand receipt changed before publication')
        if identity is not None:
            load_expression_library(store, identity, cancel)

    recheck()
    # Files installed before the single metadata commit are immutable. Failed
    # jobs can leave unreferenced objects; they never advance the saved pointer.
    install_master_copy(store, keys.scene, keys.sha256, keys.scene.parent, cancel)
    if rebuilt is not None:
        publish_rebuilt_hand(store, rebuilt, cancel)
        published_hand = True
    identity = publish_library(store, manifest, keys.report, cancel)
    load_expression_library(store, identity, cancel)
    recheck()
    revision = stage_unverified_master(store, output, authorized_source_root=output.parent,
        expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_sha256=output_sha, expected_project=initial, proposed_parts=proposed_parts,
        proposed_expression=ExpressionState(identity), cancel=cancel, before_project_save=recheck)
    return ExpressionPreparation(revision.project, revision, identity,
        {'neutral_keys': keys.observed, 'hand': None if rebuilt is None else rebuilt.observed,
         'original_master_preserved': True, 'authoritative_master_sha256': output_sha,
         'visual_quality_approved': False, 'engine_import_verified': False},
        keys.stage_job_id, keys.reopen_job_id)
