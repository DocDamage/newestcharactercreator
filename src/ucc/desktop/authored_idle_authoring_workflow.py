"""Explicit desktop review and private creation for original motion."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from ucc.core.authored_idle import PROFILE, AuthoredIdleInspectionRequest
from ucc.core.errors import ProjectConflict, UCCError, ValidationError
from ucc.core.storage import MAX_JSON_BYTES
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.export_destination import plan_destination
from .catalog_location import existing_catalog_path
from .generation import bundled_worker_path

if TYPE_CHECKING:
    from ucc.jobs.authored_idle_loop_proof import PublishedAuthoredIdleLoopProof
    from ucc.jobs.authored_idle_receipt import AuthoredIdleCandidate
    from ucc.jobs.authored_walk import AuthoredWalkCandidate


SOURCE_REVIEW = 'authored_idle_source_review'
AUTHOR_IDLE = 'authored_idle_author'
WALK_SOURCE_REVIEW = 'authored_walk_source_review'
AUTHOR_WALK = 'authored_walk_author'
WALK_KINDS = frozenset({WALK_SOURCE_REVIEW, AUTHOR_WALK})
KINDS = frozenset({SOURCE_REVIEW, AUTHOR_IDLE}) | WALK_KINDS


@dataclass(frozen=True, slots=True)
class _AuthoredOutput:
    candidate: AuthoredIdleCandidate | AuthoredWalkCandidate
    proof: PublishedAuthoredIdleLoopProof | None
    proof_error: str | None


def _ready(window, *, walk=False):
    controller = window.controller
    if not controller.has_project or controller.store is None or controller.dirty:
        return False
    project = controller.require_project()
    return (project.family == 'humanoid.v1' and project.base_provider == 'mpfb'
            and project.master_blend is not None and (not walk or not project.parts))


def _same_owner(window, context, *, walk=False):
    return (_ready(window, walk=walk) and window.controller.store is context.store
            and window.controller.require_project() == context.project)


def _current(window, context, *, walk=False):
    from .target_action_preview import _small_digest

    if (not _same_owner(window, context, walk=walk)
            or existing_catalog_path(window._catalog_path()) != context.database
            or _small_digest(context.store.file, MAX_JSON_BYTES) != context.project_sha256):
        motion = 'walk' if walk else 'idle'
        raise ProjectConflict(f'The saved character or selected catalog changed during original {motion} authoring')


def _discard_dialog(window, dialog):
    if getattr(window, '_authored_idle_dialog', None) is dialog:
        window._authored_idle_dialog = None
        window._authored_idle_context = None
    dialog.deleteLater()


def refresh_authored_idle_authoring(window):
    for action_name, walk in (('authored_idle_action', False), ('authored_walk_action', True)):
        action = getattr(window, action_name, None)
        if action is not None:
            action.setEnabled(_ready(window, walk=walk) and not window.jobs.busy)
    context = getattr(window, '_authored_idle_context', None)
    if context is None or _same_owner(window, context):
        return
    dialog = getattr(window, '_authored_idle_dialog', None)
    if dialog is not None:
        dialog.reject()
    elif window.jobs.busy and window._work_kind in KINDS:
        window.jobs.cancel()


def start_authored_idle_authoring(window):
    _start_authoring(window, walk=False)


def start_authored_walk_authoring(window):
    _start_authoring(window, walk=True)


def _start_authoring(window, *, walk):
    from .target_action_preview import _small_digest
    from .target_action_workflow import TargetActionContext, _submit

    if window.jobs.busy:
        window._error('Another local task is running')
        return
    if not _ready(window):
        window._error('Open a clean saved MPFB humanoid with an editable master')
        return
    if walk and window.controller.require_project().parts:
        window._error('Original walk authoring requires a saved character with no installed parts')
        return
    dialog = getattr(window, '_authored_idle_dialog', None)
    if dialog is not None:
        dialog.raise_()
        return
    try:
        store = window.controller.store
        context = TargetActionContext(store, window.controller.require_project(),
            existing_catalog_path(window._catalog_path()), _small_digest(store.file, MAX_JSON_BYTES))
        _current(window, context, walk=walk)
        window._authored_idle_context = context

        def operation(cancel, progress):
            from ucc.jobs.authored_idle import inspect_idle_authoring_sources

            progress('REVIEW_AUTHORED_WALK_SOURCES' if walk else 'REVIEW_AUTHORED_IDLE_SOURCES')
            return context, inspect_idle_authoring_sources(store, cancel=cancel)

        _submit(window, WALK_SOURCE_REVIEW if walk else SOURCE_REVIEW, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        window._authored_idle_context = None
        window._error(str(error))


def _selected_blender(window, *, walk=False):
    executable = window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        motion = 'walk' if walk else 'idle'
        selected, _ = QFileDialog.getOpenFileName(window, f'Choose installed Blender for original {motion} authoring', '',
            'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
        if not selected:
            return None
        executable = Path(selected)
    if not executable.is_absolute() or executable.is_symlink() or not executable.is_file():
        raise ValidationError('Choose a regular installed Blender executable')
    window._blender_executable = executable
    return executable


def _accepted(window, context, dialog, *, walk=False):
    from .target_action_workflow import _submit

    choice = dialog.choice
    if getattr(window, '_authored_idle_dialog', None) is not dialog:
        return
    _discard_dialog(window, dialog)
    if choice is None:
        return
    try:
        _current(window, context, walk=walk)
        if window.jobs.busy:
            raise ValidationError('Another local task is running')
        executable = _selected_blender(window, walk=walk)
        if executable is None:
            return
        _current(window, context, walk=walk)
        worker = bundled_worker_path()
        request = AuthoredIdleInspectionRequest(str(uuid4()), canonical_bytes(context.project.to_dict()),
            choice.permissions, choice.purpose, choice.original_procedural_recipe_declared,
            choice.private_authored_output_preview_confirmed, profile=PROFILE if walk else choice.profile)
        destination = plan_destination(choice.candidate_destination, context.store.root)
        proof = (plan_destination(choice.proof_destination, context.store.root)
                 if not walk and choice.proof_destination else None)
        if proof is not None and (proof.path.is_relative_to(destination.path) or destination.path.is_relative_to(proof.path)):
            raise ValidationError('Choose separate new folders for the idle candidate and loop proof')
        window._authored_idle_context = context

        def operation(cancel, progress):
            if walk:
                from ucc.jobs.authored_walk import author_original_walk as author
            else:
                from ucc.jobs.authored_idle import author_original_idle as author

            common = dict(source_policy_records=choice.source_policy_records, database_path=context.database,
                blender_exe=executable, worker_script=worker, cancel=cancel)
            progress('AUTHOR_ORIGINAL_WALK' if walk else 'AUTHOR_ORIGINAL_IDLE')
            candidate = author(context.store, inspection_request=request, destination=destination, **common)
            if proof is None:
                return context, _AuthoredOutput(candidate, None, None)
            try:
                from ucc.jobs.authored_idle_loop_proof import publish_authored_idle_loop_proof

                progress('SAVE_AUTHORED_IDLE_PROOF')
                published = publish_authored_idle_loop_proof(context.store, directory=candidate.directory,
                    expected_receipt_sha256=candidate.receipt_sha256, destination=proof, **common)
            except (UCCError, OSError, ValueError) as error:
                return context, _AuthoredOutput(candidate, None, str(error))
            return context, _AuthoredOutput(candidate, published, None)

        _submit(window, AUTHOR_WALK if walk else AUTHOR_IDLE, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        window._authored_idle_context = None
        window._error(str(error))


def finish_authored_idle_authoring(window, result):
    from .target_action_workflow import _close_progress

    _close_progress(window)
    context = getattr(window, '_authored_idle_context', None)
    if context is None:
        return
    walk = window._work_kind in WALK_KINDS
    motion = 'walk' if walk else 'idle'
    try:
        if type(result) is not tuple or len(result) != 2 or result[0] is not context:
            raise ValidationError(f'Unexpected original {motion} authoring result')
        value = result[1]
        if window._work_kind in {SOURCE_REVIEW, WALK_SOURCE_REVIEW}:
            if window.jobs.cancel_requested:
                window._authored_idle_context = None
                return
            _current(window, context, walk=walk)
            from .authored_idle_authoring_dialog import AuthoredIdleAuthoringDialog

            dialog = AuthoredIdleAuthoringDialog(value, window, walk=walk)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            window._authored_idle_dialog = dialog
            dialog.accepted.connect(lambda: _accepted(window, context, dialog, walk=walk))
            dialog.rejected.connect(lambda: _discard_dialog(window, dialog))
            dialog.show()
            return
        if type(value) is not _AuthoredOutput:
            raise ValidationError(f'Unexpected original {motion} delivery')
        window._authored_idle_context = None
        message = (f"Private original {motion} candidate saved at {value.candidate.directory}"
                   f"\nReceipt SHA-256 {value.candidate.receipt_sha256}")
        if walk:
            window.log.setPlainText(message + '\nKeep the saved authoring project and retained worker records. '
                                    'Visual review and engine use remain pending.')
            return
        if value.proof is not None:
            message += f"\nPrivate loop proof saved at {value.proof.path}"
        elif value.proof_error:
            message += f"\nLoop proof publication needs another attempt. {value.proof_error}"
        message += ('\nKeep the saved authoring project and retained worker records. Choose File > Create separate '
                    'target copy before attachment. Visual quality and engine use remain pending.')
        window.log.setPlainText(message)
    except (UCCError, OSError, ValueError) as error:
        window._authored_idle_context = None
        window._error(str(error))


def authored_idle_authoring_error(window, error):
    from .target_action_workflow import _close_progress

    _close_progress(window)
    window._authored_idle_context = None
    if window.jobs.cancel_requested:
        motion = 'walk' if window._work_kind in WALK_KINDS else 'idle'
        window.statusBar().showMessage(f'Original {motion} operation cancelled')
        return
    window._error(error)
