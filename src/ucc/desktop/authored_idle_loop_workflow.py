"""Review a local authored-idle receipt for the current target viewer."""
from hashlib import sha256
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ucc.animations.target_action_diagnostic import TargetActionDiagnosticSelection
from ucc.core.errors import ProjectConflict, UCCError, ValidationError
from ucc.preview.playback_window import PlaybackWindow


KIND = 'target_action_idle_loop_review'


def cancel_idle_loop_review(window):
    request = getattr(window, '_idle_loop_review', None)
    window._idle_loop_review = None
    if request is not None and getattr(window, '_work_kind', None) == KIND:
        cancel = getattr(window, '_target_action_cancel', None)
        if cancel is not None:
            cancel.set()


def _is_current(window, context, active, viewer):
    controller = window.controller
    return (getattr(window, '_target_action_result', None) is active
            and window._target_action_preview_context is context
            and window._target_action_viewer is viewer and viewer.cache is active.cache
            and controller.store is context.store and controller.has_project and not controller.dirty
            and controller.require_project() == context.project)


def start_idle_loop_review(window):
    from .target_action_workflow import _submit

    try:
        if window.jobs.busy:
            raise ValidationError('Another local task is running')
        active = getattr(window, '_target_action_result', None)
        if active is None:
            raise ValidationError('Load the saved idle target preview first')
        context = window._target_action_preview_context
        review = window._target_action_preview_review
        viewer = window._target_action_viewer
        if not _is_current(window, context, active, viewer) or viewer.review_window != PlaybackWindow():
            raise ValidationError('Load the complete target preview before reviewing its loop')
        selected, _ = QFileDialog.getOpenFileName(window, 'Select authored idle proof', '', 'Idle proof (*.json)')
        if not selected:
            return
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        if QMessageBox.question(window, 'Review idle loop', 'Use this proof for private local loop preview?',
                buttons, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        if not _is_current(window, context, active, viewer):
            raise ProjectConflict('The saved target selection changed during review')
        selection = TargetActionDiagnosticSelection(context.project.project_id, context.project.revision,
            context.project_sha256, review.master_sha256, active.clip_id, active.binding_sha256,
            review.source.source_binding_sha256, review.source.catalog_record_sha256)
        viewer.clear_idle_loop_review()
        token = object()
        window._idle_loop_review = (token, context, active, viewer)

        def operation(cancel, _progress):
            from ucc.jobs.authored_idle_loop_preview import load_authored_idle_loop_preview

            result = load_authored_idle_loop_preview(context.store, proof_file=Path(selected),
                selection=selection, database_path=context.database, local_preview_confirmed=True,
                cancel=cancel)
            if result.binding_sha256 != active.binding_sha256 or result.cache_sha256 != sha256(active.cache.packed).hexdigest():
                raise ProjectConflict('The saved idle proof differs from the active preview cache')
            return token, result

        _submit(window, KIND, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        cancel_idle_loop_review(window)
        window._error(str(error))


def finish_idle_loop_review(window, output):
    from ucc.jobs.authored_idle_loop_preview import AuthoredIdleLoopPreview
    from .target_action_workflow import _close_progress

    _close_progress(window)
    request = getattr(window, '_idle_loop_review', None)
    window._idle_loop_review = None
    if request is None or window.jobs.cancel_requested:
        return
    token, context, active, viewer = request
    try:
        if (type(output) is not tuple or len(output) != 2 or output[0] is not token
                or type(output[1]) is not AuthoredIdleLoopPreview or output[1].database_path != context.database):
            raise ValidationError('Unexpected idle loop review result')
        admitted = output[1]

        def still_current():
            return _is_current(window, context, active, viewer) and admitted.identities_current()

        viewer.install_idle_loop(still_current, admitted.watch_paths)
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))


def idle_loop_review_error(window, error):
    from .target_action_workflow import _close_progress

    _close_progress(window)
    pending = getattr(window, '_idle_loop_review', None)
    window._idle_loop_review = None
    if pending is not None and not window.jobs.cancel_requested:
        window._error(error)
