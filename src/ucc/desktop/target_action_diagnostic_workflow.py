"""Read-only registered-clip diagnostics with fail-closed desktop ownership."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtWidgets import QMainWindow

from ucc.core.errors import ProjectConflict, UCCError, ValidationError
from .target_action_preview import _stamp

KINDS = frozenset({'target_action_diagnostic'})
if TYPE_CHECKING:
    from ucc.animations.target_action_diagnostic import TargetActionDiagnosticSelection
    from ucc.jobs.target_action import TargetActionSourceReview
    from .target_action_workflow import TargetActionContext


def _current(window: QMainWindow, context: TargetActionContext) -> None:
    """Check desktop ownership only; full IO admission belongs to the worker."""
    controller = window.controller
    if (not controller.has_project or controller.store is not context.store
            or controller.dirty or controller.require_project() != context.project):
        raise ProjectConflict('The saved character selection changed during diagnostic work')


def _selection(context: TargetActionContext, review: TargetActionSourceReview,
               binding_sha256: str) -> TargetActionDiagnosticSelection:
    from ucc.animations.target_action_diagnostic import TargetActionDiagnosticSelection
    return TargetActionDiagnosticSelection(
        context.project.project_id, context.project.revision, context.project_sha256,
        review.master_sha256, review.source.clip_id, binding_sha256,
        review.source.source_binding_sha256, review.source.catalog_record_sha256)


def clear_target_action_diagnostic(window: QMainWindow, message: str = 'Diagnostic report closed') -> None:
    request = getattr(window, '_target_diagnostic_request', None)
    window._target_diagnostic_request = None
    if request is not None and window.jobs.busy and window._work_kind in KINDS:
        cancel = getattr(window, '_target_action_cancel', None)
        if cancel is not None:
            cancel.set()
    timer = getattr(window, '_target_diagnostic_timer', None)
    window._target_diagnostic_timer = None
    if timer is not None:
        timer.stop()
        timer.deleteLater()
    watcher = getattr(window, '_target_diagnostic_watcher', None)
    window._target_diagnostic_watcher = None
    if watcher is not None:
        watcher.blockSignals(True)
        watcher.deleteLater()
    viewer = getattr(window, '_target_diagnostic_viewer', None)
    if viewer is not None:
        viewer.clear_report(message)
    window._target_diagnostic_loaded = None
    window._target_diagnostic_identities = {}
    window._target_diagnostic_context = None


def _visible_guard(window: QMainWindow) -> bool:
    if getattr(window, '_target_diagnostic_loaded', None) is None:
        return False
    try:
        _current(window, window._target_diagnostic_context)
        for path, expected in window._target_diagnostic_identities.items():
            if _stamp(path) != expected:
                raise ProjectConflict('A diagnostic source, proof or catalog input changed')
        return True
    except (UCCError, OSError, ValueError) as error:
        clear_target_action_diagnostic(window, str(error) + '; explicitly inspect the saved binding again.')
        return False


def refresh_target_action_diagnostic(window: QMainWindow) -> None:
    _visible_guard(window)
    request = getattr(window, '_target_diagnostic_request', None)
    if request is not None:
        try:
            _current(window, request[0])
        except (UCCError, OSError, ValueError):
            clear_target_action_diagnostic(window, 'The selected saved character changed')


def start_target_action_diagnostic(window: QMainWindow, context: TargetActionContext,
                                   review: TargetActionSourceReview, binding_sha256: str,
                                   *, local_preview_confirmed: bool) -> None:
    if window.jobs.busy:
        raise ValidationError('Another local task is running')
    _current(window, context)
    if local_preview_confirmed is not True or not binding_sha256:
        raise ValidationError('Explicitly select a saved binding and confirm private local preview')
    selection = _selection(context, review, binding_sha256)
    clear_target_action_diagnostic(window, 'Another diagnostic binding was selected')
    old = getattr(window, '_target_diagnostic_viewer', None)
    if old is not None:
        old.close()
    token = object()
    window._target_diagnostic_request = (context, selection, token)
    from .target_action_workflow import _submit
    def operation(cancel, progress):
        from ucc.jobs.target_action_diagnostic import inspect_saved_target_action
        loaded = inspect_saved_target_action(
            context.store, selection=selection, database_path=context.database,
            local_preview_confirmed=True, cancel=cancel, timeout_s=300, progress=progress)
        return token, loaded
    try:
        _submit(window, 'target_action_diagnostic', operation, progress=True)
    except Exception:
        window._target_diagnostic_request = None
        raise


def finish_target_action_diagnostic(window: QMainWindow, result: object) -> None:
    from .target_action_workflow import _close_progress
    from .target_action_diagnostic_dialog import TargetActionDiagnosticDialog
    from ucc.jobs.target_action_diagnostic import LoadedTargetActionDiagnostics
    _close_progress(window)
    request = getattr(window, '_target_diagnostic_request', None)
    if request is None or window.jobs.cancel_requested:
        clear_target_action_diagnostic(window, 'Diagnostic loading cancelled or superseded')
        return
    context, selection, token = request
    viewer = watcher = None
    try:
        _current(window, context)
        if (type(result) is not tuple or len(result) != 2 or result[0] is not token
                or type(result[1]) is not LoadedTargetActionDiagnostics):
            raise ValidationError('Unexpected or superseded diagnostic result')
        loaded = result[1]
        if loaded.report.selection != selection:
            raise ValidationError('Diagnostic report differs from the selected saved binding')
        identities = dict(loaded.watched_identities)
        watched = set(loaded.watch_paths)
        absent = {path for path, stamp in identities.items() if stamp == (0, 0, 0, 0)}
        coordination = {Path(str(context.database) + suffix)
                        for suffix in ('-wal', '-shm', '-journal')}
        if (loaded.database_path != context.database or not identities or not loaded.watch_paths
                or len(identities) != len(loaded.watched_identities)
                or len(watched) != len(loaded.watch_paths)
                or set(identities) - absent != watched or not absent <= coordination
                or any(path.parent not in watched for path in absent)
                or context.database not in watched):
            raise ValidationError('Diagnostic report lacks a complete current-input watch set')
        viewer = TargetActionDiagnosticDialog(loaded.report, window)
        watcher = QFileSystemWatcher(window)
        if watcher.addPaths([str(path) for path in loaded.watch_paths]):
            raise ValidationError('Could not monitor every diagnostic input')
        window._target_diagnostic_viewer = viewer
        window._target_diagnostic_loaded = loaded
        window._target_diagnostic_context = context
        window._target_diagnostic_identities = identities
        window._target_diagnostic_watcher = watcher
        def invalidated(_path):
            if getattr(window, '_target_diagnostic_watcher', None) is watcher:
                clear_target_action_diagnostic(window, 'A watched input changed; inspect the saved binding again.')
        watcher.fileChanged.connect(invalidated)
        watcher.directoryChanged.connect(invalidated)
        def closed():
            if getattr(window, '_target_diagnostic_viewer', None) is viewer:
                clear_target_action_diagnostic(window)
                window._target_diagnostic_viewer = None
            viewer.deleteLater()
        viewer.closed.connect(closed)
        timer = QTimer(window)
        timer.setInterval(500)
        timer.timeout.connect(lambda: _visible_guard(window))
        window._target_diagnostic_timer = timer
        if not _visible_guard(window):
            window._target_diagnostic_viewer = None
            viewer.deleteLater()
            return
        window._target_diagnostic_request = None
        timer.start()
        viewer.show()
        window.log.setPlainText('PRIVATE REGISTERED CLIP DIAGNOSTICS\n'
            'Position-only measurements from the selected saved binding.\n'
            'No walking, usable-action, automatic-loop or broader approval is granted.')
    except (UCCError, OSError, ValueError, TypeError, AttributeError) as error:
        if watcher is not None and getattr(window, '_target_diagnostic_watcher', None) is not watcher:
            watcher.deleteLater()
        if viewer is not None:
            viewer.clear_report('Diagnostic loading did not complete')
            viewer.deleteLater()
            if getattr(window, '_target_diagnostic_viewer', None) is viewer:
                window._target_diagnostic_viewer = None
        target_action_diagnostic_error(window, str(error))


def target_action_diagnostic_error(window: QMainWindow, error: str) -> None:
    from .target_action_workflow import _close_progress
    _close_progress(window)
    clear_target_action_diagnostic(window, 'Diagnostic validation did not complete')
    window._error('The diagnostic report was not opened. Saved records remain unchanged.\n' + str(error))
