"""Background opening and fail-closed watching of explicitly selected saved images."""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide6.QtWidgets import QFileDialog

from ucc.core.errors import ProjectConflict, UCCError, ValidationError
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.export.godot_saved_preview import LoadedSavedGodotPreview
from .godot_saved_preview_selection import ReviewedSavedPreviewFiles, SavedPreviewPolicyDialog, review_saved_preview_files
from .godot_saved_preview_widget import SavedGodotPreviewDialog
from .target_action_preview import _stamp

KINDS = frozenset({'godot_saved_review', 'godot_saved_load'})


def _current(window, context):
    from .target_action_workflow import _current as check
    check(window, context)


def clear_saved_godot_preview(window, message='Saved preview closed'):
    request = getattr(window, '_godot_saved_request', None)
    window._godot_saved_request = None
    dialog = getattr(window, '_godot_saved_policy_dialog', None)
    if dialog is not None:
        dialog.reject()
    if request is not None and window.jobs.busy and window._work_kind in KINDS:
        cancel = getattr(window, '_target_action_cancel', None)
        if cancel is not None:
            cancel.set()
    timer = getattr(window, '_godot_saved_timer', None)
    if timer is not None:
        timer.stop(); timer.deleteLater(); window._godot_saved_timer = None
    watcher = getattr(window, '_godot_saved_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        watcher.deleteLater(); window._godot_saved_watcher = None
    viewer = getattr(window, '_godot_saved_viewer', None)
    if viewer is not None:
        viewer.clear_preview(message)
    window._godot_saved_loaded = None
    window._godot_saved_identities = {}


def _visible_guard(window):
    loaded = getattr(window, '_godot_saved_loaded', None)
    if loaded is None:
        return False
    try:
        _current(window, window._godot_saved_view_context)
        for path, expected in window._godot_saved_identities.items():
            if _stamp(path) != expected:
                raise ProjectConflict('A saved preview input or catalog coordination file changed')
        return True
    except (UCCError, OSError, ValueError) as error:
        clear_saved_godot_preview(window, str(error)+'; explicitly reopen the saved proof to view it again.')
        return False


def refresh_saved_godot_preview(window):
    _visible_guard(window)
    request = getattr(window, '_godot_saved_request', None)
    if request is not None:
        try:
            _current(window, request[0])
        except (UCCError, OSError, ValueError):
            cancel = getattr(window, '_target_action_cancel', None)
            if window.jobs.busy and window._work_kind in KINDS and cancel is not None:
                cancel.set()
            window._godot_saved_request = None
            dialog = getattr(window, '_godot_saved_policy_dialog', None)
            if dialog is not None:
                dialog.reject()


def start_saved_godot_preview(window, context, review, binding_sha):
    if window.jobs.busy:
        raise ValidationError('Another local task is running')
    _current(window, context)
    paths = []
    for title in ('Choose saved Godot draw receipt', 'Choose its linked body diagnostic receipt',
                  'Choose its retained input manifest'):
        selected, _ = QFileDialog.getOpenFileName(window, title, '', 'Saved proof JSON (*.json)')
        if not selected:
            return
        paths.append(Path(selected))
    clear_saved_godot_preview(window, 'Opening another explicitly selected saved preview')
    old = getattr(window, '_godot_saved_viewer', None)
    if old is not None:
        old.close()
    window._godot_saved_request = (context, review, binding_sha, object())
    from .target_action_workflow import _submit
    _submit(window, 'godot_saved_review',
            lambda cancel, _progress: review_saved_preview_files(*paths, cancel=cancel), progress=True)


def _selection(context, review, binding_sha):
    return RegisteredInputSelection(
        context.project.project_id, context.project.revision, context.project_sha256,
        review.master_sha256, review.source.clip_id, binding_sha,
        review.source.source_binding_sha256, review.source.catalog_record_sha256)


def finish_saved_godot_preview(window, result):
    from .target_action_workflow import _close_progress, _submit
    _close_progress(window)
    request = getattr(window, '_godot_saved_request', None)
    if request is None or window.jobs.cancel_requested:
        window._godot_saved_request = None
        return
    context, review, binding_sha, token = request
    try:
        _current(window, context)
        if window._work_kind == 'godot_saved_review':
            if type(result) is not ReviewedSavedPreviewFiles:
                raise ValidationError('Unexpected saved-preview file review')
            dialog = SavedPreviewPolicyDialog(result, window)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            window._godot_saved_policy_dialog = dialog
            def chosen():
                if getattr(window, '_godot_saved_request', None) is not request or not dialog.consent.isChecked():
                    return
                try:
                    _current(window, context)
                    selected = _selection(context, review, binding_sha)
                    def operation(cancel, progress):
                        from ucc.jobs.godot_saved_preview import load_saved_godot_preview
                        return load_saved_godot_preview(context.store, selection=selected,
                            draw_receipt=result.draw_receipt, body_receipt=result.body_receipt,
                            retained_manifest=result.retained_manifest, database_path=context.database,
                            permissions=result.permissions, local_view_confirmed=True,
                            cancel=cancel, timeout_s=300, progress=progress)
                    # The current review worker may still be releasing its QThread.
                    def start():
                        if getattr(window, '_godot_saved_request', None) is not request:
                            return
                        if window.jobs.busy:
                            QTimer.singleShot(10, start)
                        else:
                            _submit(window, 'godot_saved_load', operation, progress=True)
                    QTimer.singleShot(0, start)
                except (UCCError, OSError, ValueError) as error:
                    saved_godot_preview_error(window, str(error))
            dialog.accepted.connect(chosen)
            def finished(_code):
                if window._godot_saved_policy_dialog is dialog:
                    window._godot_saved_policy_dialog = None
                if not dialog.consent.isChecked() or _code != dialog.DialogCode.Accepted:
                    window._godot_saved_request = None
                dialog.deleteLater()
            dialog.finished.connect(finished)
            dialog.show()
            return
        if type(result) is not LoadedSavedGodotPreview or result.selection != _selection(context, review, binding_sha):
            raise ValidationError('Loaded preview differs from the current selected binding')
        identities = dict(result.watched_identities)
        if not identities or not result.watch_paths or result.database_path != context.database:
            raise ValidationError('Loaded preview lacks its current catalog or complete watch set')
        viewer = SavedGodotPreviewDialog(result, window)
        if viewer.current_frame != 1:
            message = viewer.status.text()
            viewer.deleteLater()
            raise ValidationError(message)
        watcher = QFileSystemWatcher(window)
        watched = [str(path) for path in result.watch_paths]
        if watcher.addPaths(watched):
            viewer.clear_preview('Could not monitor the complete saved preview')
            viewer.deleteLater(); watcher.deleteLater()
            raise ValidationError('Could not monitor all saved-preview inputs')
        window._godot_saved_viewer = viewer
        window._godot_saved_view_context = context
        window._godot_saved_loaded = result
        window._godot_saved_identities = identities
        window._godot_saved_watcher = watcher
        def invalidated(_path):
            if getattr(window, '_godot_saved_watcher', None) is watcher:
                clear_saved_godot_preview(window, 'A watched source, proof or catalog changed; reopen the saved preview.')
        watcher.fileChanged.connect(invalidated)
        watcher.directoryChanged.connect(invalidated)
        def closed():
            if getattr(window, '_godot_saved_viewer', None) is viewer:
                clear_saved_godot_preview(window)
                window._godot_saved_viewer = None
            viewer.deleteLater()
        viewer.closed.connect(closed)
        for button in viewer.frame_buttons.values():
            button.pressed.connect(lambda: _visible_guard(window))
        timer = QTimer(window); timer.setInterval(500)
        timer.timeout.connect(lambda: _visible_guard(window))
        window._godot_saved_timer = timer
        if not _visible_guard(window):
            window._godot_saved_viewer = None
            viewer.deleteLater()
            return
        window._godot_saved_request = None
        timer.start(); viewer.show()
        window.log.setPlainText('SAVED PRIVATE GODOT PREVIEW\nThree verified debug frames loaded from captured bytes.\n'
            'Current project binding and source policies passed. Appearance, artist approval and shipping remain unapproved.')
    except (UCCError, OSError, ValueError, TypeError) as error:
        saved_godot_preview_error(window, str(error))


def saved_godot_preview_error(window, error):
    from .target_action_workflow import _close_progress
    _close_progress(window)
    window._godot_saved_request = None
    clear_saved_godot_preview(window, 'Saved preview validation did not complete')
    window._error('Saved Godot preview was not opened. Original proof records remain unchanged.\n'+str(error))
