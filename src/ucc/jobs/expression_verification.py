"""Verify the actual registered prepared master without changing project state."""
import re
from pathlib import Path
from threading import Event

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.hand_parts import ensure_source_intent, hand_selection
from ucc.core.storage import ProjectStore
from .expression_hands import verify_existing_hand
from .expression_inspection import CheckedExpressionMaster, _inspect_expression_copy
from .expression_revisions import admit_expression_source
from .expression_storage import load_expression_library, check_cancel
from .hand_storage import load_hand_library, load_hand_receipt
from .master_preview import _master_file, _digest


def registered_expression_source(store: ProjectStore, project, cancel: Event | None = None) -> tuple:
    if project.expression is None or project.master_blend is None:
        raise ValidationError('Prepare neutral expression keys before expression verification')
    library = load_expression_library(store, project.expression.library_sha256, cancel)
    master, sha = _master_file(store, project.master_blend)
    if _digest(master, cancel) != sha:
        raise ProjectStorageError('Prepared source differs from its immutable master identity')
    if not project.parts:
        return library, admit_expression_source(store, library, sha, cancel)
    if len(project.parts) != 1:
        raise ValidationError('Prepared expressions support one registered compatible left hand')
    match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', project.parts[0].part_asset_id)
    if match is None:
        raise ValidationError('Prepared hand does not have a compatible registered library identity')
    hand = load_hand_library(store, match[1], cancel)
    ensure_source_intent(project, hand.manifest['recipe'])
    selection = hand_selection(project, hand.sha256)
    load_hand_receipt(store, hand, sha, selection, cancel)
    original_sha = hand.manifest['recipe']['bindings']['master_sha256']
    admit_expression_source(store, library, original_sha, cancel)
    return library, None


def verify_saved_expression_master(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
                                   mpfb_data_dir: Path, expected_project_id: str, expected_revision: int,
                                   expected_master_blend: str, cancel: Event | None = None,
                                   timeout_s: float = 300) -> CheckedExpressionMaster:
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before prepared expression verification')
    check_cancel(cancel); metadata_sha = _digest(store.file, cancel)
    library, receipt = registered_expression_source(store, initial, cancel)
    if initial.parts:
        verify_existing_hand(store, initial, blender_exe=blender_exe, worker_script=worker_script,
            mpfb_data_dir=mpfb_data_dir, cancel=cancel, timeout_s=timeout_s)
    checked = _inspect_expression_copy(store, master_blend=initial.master_blend,
        blender_exe=blender_exe, worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
        cancel=cancel, timeout_s=timeout_s)
    observed_sha = canonical_digest(checked.observed['observation'])
    if not initial.parts:
        expected = library.manifest['observation_sha256'] if receipt is None else receipt['observation_sha256']
        if observed_sha != expected or (receipt is not None
                and checked.observed['expression_keys_sha256'] != receipt['expression_keys_sha256']):
            raise ProjectStorageError('Prepared neutral master differs from its registered observation')
    if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
        raise ProjectConflict('Project changed during prepared expression verification')
    registered_expression_source(store, initial, cancel); check_cancel(cancel)
    return checked
