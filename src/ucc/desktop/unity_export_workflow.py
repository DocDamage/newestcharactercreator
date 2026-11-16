"""Normal desktop Unity export with explicit review and cooperative local progress."""
from pathlib import Path
from threading import Event
from dataclasses import dataclass
from uuid import uuid4
import time

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QDialog, QProgressDialog

from ucc.core.errors import UCCError, ValidationError, ProjectConflict, ProjectStorageError
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.jobs.static_export_sources import static_export_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.godot_candidate_inputs import regular_file, identity, read_json
from ucc.jobs.master_preview import _digest
from .unity_export_dialog import UnityExportDialog


PHASES = {
    'EDITOR_IDENTITY': 'Checking the selected installed Unity Editor…',
    'SOURCE_DISCOVERY': 'Checking the installed MPFB data for this local export…',
    'SOURCE_PREPARATION': 'Checking the saved source in fresh Blender processes…',
    'RUNTIME_SOURCE_PREPARATION': 'Reproducing source diagnostic poses in Blender…',
    'UNITY_IMPORT': 'Importing and independently reopening the Unity character…',
    'DESTINATION_STAGING': 'Sealing the new Unity project for publication…',
    'PUBLISHED_RUNTIME_VERIFICATION': 'Checking the published Unity project with actual GPU rendering…',
    'COMPLETE': 'Final Unity checks passed; confirming the published receipt…',
}


@dataclass(frozen=True)
class UnityDesktopReview:
    store: object
    project: object
    review: object


def review_unity_sources(store, project, cancel):
    review, _, _ = static_export_sources(
        store, project_id=project.project_id, revision=project.revision,
        master_blend=project.master_blend, cancel=cancel, purpose='Unity export')
    return UnityDesktopReview(store, project, review)


class UnityExportProgress(QObject):
    changed = Signal(str)

    def __init__(self, window, cancel):
        super().__init__(window)
        self.window = window
        self.cancel = cancel
        self.dialog = QProgressDialog('Preparing local Unity export…', 'Cancel export', 0, 0, window)
        self.dialog.setWindowTitle('Verifying private Unity export')
        self.dialog.setWindowModality(Qt.WindowModality.NonModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self.request_cancel)
        self.changed.connect(self.display, Qt.ConnectionType.QueuedConnection)
        self.dialog.show()

    @Slot(str)
    def display(self, phase):
        text = PHASES.get(phase, 'Verifying private Unity export…')
        if self.cancel.is_set():
            text = 'Cancelling Unity export; waiting for owned workers and rollback…'
        self.dialog.setLabelText(text)
        self.window.statusBar().showMessage(text)

    @Slot()
    def request_cancel(self):
        self.cancel.set()
        self.window.statusBar().showMessage('Cancelling Unity export; waiting for owned workers and rollback…')

    def close(self):
        self.dialog.hide()
        self.dialog.deleteLater()
        self.deleteLater()


def refresh_unity_export(window):
    window.unity_export_action.setEnabled(
        not window.jobs.busy and window.controller.has_project and not window.controller.dirty
        and supports_material_master_intent(window.controller.require_project()))


def run_desktop_unity_export(store, *, review, permissions, editor_identity, destination,
                             blender_exe, unity_exe, cancel, progress=None):
    try:
        return _run_desktop_unity_export(
            store, review=review, permissions=permissions, editor_identity=editor_identity,
            destination=destination, blender_exe=blender_exe, unity_exe=unity_exe,
            cancel=cancel, progress=progress)
    except Exception as error:
        # BackgroundJobs carries exception text across Qt's boundary, not __notes__.
        # Rollback notes include the exact retained path and must remain actionable.
        notes = getattr(error, '__notes__', ())
        if notes:
            detail = '\n'.join(str(note) for note in notes)[:8192]
            raise ProjectStorageError(type(error).__name__+': '+str(error)+'\n'+detail) from error
        raise


def _run_desktop_unity_export(store, *, review, permissions, editor_identity, destination,
                              blender_exe, unity_exe, cancel, progress=None):
    """Use the same reviewed request through discovery and the export transaction."""
    from ucc.jobs.unity_export import export_unity
    from .generation import bundled_worker_path
    from ucc.jobs.face_discovery import discover_face_data
    from ucc.jobs.skin_material_preparation import _BudgetCancel
    from ucc.export.unity_contract import UnityExportRequest
    deadline = time.monotonic()+3600
    budget = _BudgetCancel(cancel, deadline)
    if progress is not None:
        progress('EDITOR_IDENTITY')
    executable = regular_file(unity_exe, unity_exe.parent, 512*1024*1024)
    if identity(executable) != editor_identity:
        raise ProjectConflict('Selected Unity Editor changed after review; choose and review it again')
    executable_sha256 = _digest(executable, budget)
    if identity(executable) != editor_identity:
        raise ProjectConflict('Selected Unity Editor changed while checking its identity')
    request = UnityExportRequest(
        str(uuid4()), review.project_id, review.revision, review.project_sha256, executable_sha256,
        tuple((source.asset_id, source.sha256) for source in review.sources), permissions)
    if progress is not None:
        progress('SOURCE_DISCOVERY')
    worker = bundled_worker_path()
    data = discover_face_data(store, blender_exe=blender_exe, worker_script=worker,
                              cancel=budget, timeout_s=min(300, max(.05, deadline-time.monotonic())))
    if budget.is_set():
        raise ProjectStorageError('Unity export cancelled or total deadline exceeded during source discovery')
    return export_unity(store, request=request, destination=destination, blender_exe=blender_exe,
                        worker_script=worker, mpfb_data_dir=data, unity_exe=unity_exe,
                        cancel=budget, timeout_s=max(.05, deadline-time.monotonic()), progress=progress)


def start_unity_export(window):
    try:
        if window.jobs.busy:
            raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:
            raise ValidationError('Open a saved character first')
        if window.controller.dirty:
            raise ValidationError('Save character settings before exporting')
        project = window.controller.require_project()
        store = window.controller.store
        cancel = Event()
        window._submit('unity_export_review', lambda: review_unity_sources(store, project, cancel), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        window._error(str(error))


def finish_unity_source_review(window, result):
    if window.jobs.cancel_requested:
        window.log.setPlainText('Unity source review cancelled. No export was started.')
        return
    if not isinstance(result, UnityDesktopReview):
        window._error('Unexpected Unity source review result')
        return
    window._unity_pending_review = result


def resume_unity_source_review(window):
    """The single BackgroundJobs thread must exit before starting the export job."""
    pending = getattr(window, '_unity_pending_review', None)
    if pending is None or window.jobs.busy:
        return
    window._unity_pending_review = None
    try:
        store, project, review = pending.store, pending.project, pending.review
        if (window.controller.store is not store or window.controller.require_project() != project
                or window.controller.dirty or store.load() != project):
            raise ProjectConflict('Saved character changed during Unity source review; review it again')
        dialog = UnityExportDialog(review, window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        destination = plan_destination(Path(dialog.destination.text().strip()), store.root)
        selected = Path(dialog.editor.text().strip())
        unity = regular_file(selected, selected.parent, 512*1024*1024)
        editor_identity = identity(unity)
        permissions = dialog.permissions()
        from .hand_workflow import _executable
        blender = _executable(window)
        if blender is None:
            return
        if store.load() != project or window.controller.require_project() != project or window.controller.dirty:
            raise ProjectConflict('Saved character changed during Unity export review; review it again')
        cancel = Event()
        progress = UnityExportProgress(window, cancel)
        window._unity_export_progress = progress
        window._unity_export_context = (store, project, review)
        window._clear_preview()
        window._submit('unity_export', lambda: run_desktop_unity_export(
            store, review=review, permissions=permissions, editor_identity=editor_identity,
            destination=destination, blender_exe=blender, unity_exe=unity, cancel=cancel,
            progress=progress.changed.emit), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        close_unity_progress(window)
        window._error(str(error))


def close_unity_progress(window):
    progress = getattr(window, '_unity_export_progress', None)
    if progress is not None:
        window._unity_export_progress = None
        progress.close()


def finish_unity_export(window, result):
    close_unity_progress(window)
    try:
        from ucc.jobs.unity_export import UnityExport
        if not isinstance(result, UnityExport):
            raise ValidationError('Unexpected Unity export result')
        context = getattr(window, '_unity_export_context', None)
        if context is None:
            raise ValidationError('Unity export has no matching reviewed desktop operation')
        store, project, review = context
        if (window.controller.store is not store or window.controller.require_project() != project
                or window.controller.dirty or store.load() != project):
            raise ProjectConflict('Saved character context changed; inspect the retained export separately')
        # The transaction verifies the entire final payload on its worker before returning.
        # Confirm only the bounded receipt here so large mesh hashing cannot freeze Qt.
        receipt = regular_file(result.destination/'export_receipt.json', result.destination, 2*1024*1024)
        if _digest(receipt) != result.receipt_sha256:
            raise ValidationError('Unity export receipt changed after final verification')
        record = read_json(receipt, 2*1024*1024)
        if (record.get('request_sha256') != result.request_sha256
                or record.get('master_sha256') != result.master_sha256
                or result.master_sha256 != dict((s.asset_id, s.sha256) for s in review.sources)['master']
                or any(record.get(key) is not True for key in
                       ('export_published', 'final_payload_verified', 'private_runtime_diagnostics_verified'))
                or any(record.get(key) is not False for key in
                       ('animation_clips_verified', 'visual_quality_approved', 'distribution_license_review_complete'))):
            raise ValidationError('Unity receipt differs from this reviewed published export')
        window.log.setPlainText(
            'Private Unity character project created:\n'+str(result.destination)+'\n'
            'Fresh Blender source checks, Unity import/reopen and published-project GPU diagnostics passed.\n'
            'Open this project with the reviewed Unity Editor and inspect its saved character scene.\n'
            'No animation clips are included. Editable master and history were preserved. '
            'Player builds, visual quality and public distribution remain unapproved.')
        window.statusBar().showMessage('Private Unity export verified; review the project and retained receipt')
    except (UCCError, OSError, ValueError, TypeError, KeyError) as error:
        window._error('Unity output could not be confirmed. Inspect retained logs and receipt: '+str(error))


def unity_export_error(window, error):
    close_unity_progress(window)
    # Preserve rollback failure/path diagnostics even when cancellation was requested.
    window._error('Unity export did not complete. Inspect retained staging/logs before retrying. '+str(error))
