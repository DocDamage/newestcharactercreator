"""Normal desktop Unreal export with explicit review and cooperative local progress."""
from pathlib import Path
from threading import Event
from dataclasses import dataclass
from uuid import uuid4
import time
import math

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QDialog, QProgressDialog

from ucc.core.errors import UCCError, ValidationError, ProjectConflict, ProjectStorageError
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.jobs.static_export_sources import static_export_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.godot_candidate_inputs import regular_file, identity, read_json
from ucc.jobs.master_preview import _digest
from .unreal_export_dialog import UnrealExportDialog


PHASES = {
    'EDITOR_IDENTITY': 'Checking the selected installed Unreal Editor…',
    'TOOLCHAIN_REVIEW': 'Checking existing Unreal and Windows build tools…',
    'SOURCE_DISCOVERY': 'Checking the installed MPFB data for this local export…',
    'SOURCE_PREPARATION': 'Checking the saved source in fresh Blender processes…',
    'OBSERVER_BUILD': 'Building the private native verification tool with existing build tools…',
    'UNREAL_IMPORT': 'Importing the static Unreal rig, morphs, material and scene…',
    'UNREAL_REOPEN': 'Checking saved native data in a fresh Unreal process…',
    'DESTINATION_STAGING': 'Sealing the new Unreal project for publication…',
    'PUBLISHED_UNREAL_VERIFICATION': 'Checking the published static Unreal project in a private copy…',
    'COMPLETE': 'Final static Unreal checks passed; confirming the published receipt…',
}


@dataclass(frozen=True)
class UnrealDesktopReview:
    store: object
    project: object
    review: object


def review_unreal_sources(store, project, cancel):
    review, _, _ = static_export_sources(
        store, project_id=project.project_id, revision=project.revision,
        master_blend=project.master_blend, cancel=cancel, purpose='Unreal export')
    return UnrealDesktopReview(store, project, review)


class UnrealExportProgress(QObject):
    changed = Signal(str)

    def __init__(self, window, cancel):
        super().__init__(window)
        self.window = window
        self.cancel = cancel
        self.dialog = QProgressDialog('Preparing local Unreal export...', 'Cancel export', 0, 0, window)
        self.dialog.setWindowTitle('Verifying private Unreal export')
        self.dialog.setWindowModality(Qt.WindowModality.NonModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self.request_cancel)
        self.changed.connect(self.display, Qt.ConnectionType.QueuedConnection)
        self.dialog.show()

    @Slot(str)
    def display(self, phase):
        text = PHASES.get(phase, 'Verifying private Unreal export...')
        if self.cancel.is_set():
            text = 'Cancelling Unreal export; waiting for owned workers and rollback...'
        self.dialog.setLabelText(text)
        self.window.statusBar().showMessage(text)

    @Slot()
    def request_cancel(self):
        self.cancel.set()
        self.window.statusBar().showMessage('Cancelling Unreal export; waiting for owned workers and rollback...')

    def close(self):
        self.dialog.hide()
        self.dialog.deleteLater()
        self.deleteLater()


def refresh_unreal_export(window):
    window.unreal_export_action.setEnabled(
        not window.jobs.busy and window.controller.has_project and not window.controller.dirty
        and supports_material_master_intent(window.controller.require_project()))


def run_desktop_unreal_export(store, *, review, permissions, editor_identity, destination,
                             blender_exe, unreal_exe, cancel, progress=None):
    try:
        return _run_desktop_unreal_export(
            store, review=review, permissions=permissions, editor_identity=editor_identity,
            destination=destination, blender_exe=blender_exe, unreal_exe=unreal_exe,
            cancel=cancel, progress=progress)
    except Exception as error:
        # BackgroundJobs carries exception text across Qt's boundary, not __notes__.
        # Rollback notes include the exact retained path and must remain actionable.
        notes = getattr(error, '__notes__', ())
        if notes:
            detail = '\n'.join(str(note) for note in notes)[:8192]
            raise ProjectStorageError(type(error).__name__+': '+str(error)+'\n'+detail) from error
        raise


def _run_desktop_unreal_export(store, *, review, permissions, editor_identity, destination,
                              blender_exe, unreal_exe, cancel, progress=None):
    """Use the same reviewed request through discovery and the export transaction."""
    from ucc.jobs.unreal_export import export_unreal
    from .generation import bundled_worker_path
    from ucc.jobs.face_discovery import discover_face_data
    from ucc.jobs.skin_material_preparation import _BudgetCancel
    from ucc.export.unreal_contract import UnrealExportRequest
    from ucc.jobs.unreal_toolchain import preflight_unreal_toolchain
    from ucc.jobs.export_guards import failure_reason
    deadline = time.monotonic()+3600
    budget = _BudgetCancel(cancel, deadline)
    if progress is not None:
        progress('EDITOR_IDENTITY')
    executable = regular_file(unreal_exe, unreal_exe.parent, 512*1024*1024)
    if identity(executable) != editor_identity:
        raise ProjectConflict('Selected Unreal Editor changed after review; choose and review it again')
    if progress is not None:
        progress('TOOLCHAIN_REVIEW')
    toolchain = preflight_unreal_toolchain(executable, cancel=budget,
        timeout_s=min(300, max(.05, deadline-time.monotonic())))
    if identity(executable) != editor_identity:
        raise ProjectConflict('Selected Unreal Editor changed while checking its toolchain')
    bound = dict(toolchain.files)
    request = UnrealExportRequest(
        str(uuid4()), review.project_id, review.revision, review.project_sha256,
        bound[str(executable)], bound[str(toolchain.build_version)], toolchain.identity_sha256,
        tuple((source.asset_id, source.sha256) for source in review.sources), permissions)
    if progress is not None:
        progress('SOURCE_DISCOVERY')
    worker = bundled_worker_path()
    data = discover_face_data(store, blender_exe=blender_exe, worker_script=worker,
                              cancel=budget, timeout_s=min(300, max(.05, deadline-time.monotonic())))
    reason, message = failure_reason(cancel, deadline)
    if reason:
        raise ProjectStorageError(message)
    return export_unreal(store, request=request, destination=destination, blender_exe=blender_exe,
                        worker_script=worker, mpfb_data_dir=data, unreal_exe=unreal_exe, toolchain=toolchain,
                        cancel=budget, timeout_s=max(.05, deadline-time.monotonic()), progress=progress)


def start_unreal_export(window):
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
        window._submit('unreal_export_review', lambda: review_unreal_sources(store, project, cancel), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        window._error(str(error))


def finish_unreal_source_review(window, result):
    if window.jobs.cancel_requested:
        window.log.setPlainText('Unreal source review cancelled. No export was started.')
        return
    if not isinstance(result, UnrealDesktopReview):
        window._error('Unexpected Unreal source review result')
        return
    window._unreal_pending_review = result


def resume_unreal_source_review(window):
    """The single BackgroundJobs thread must exit before starting the export job."""
    pending = getattr(window, '_unreal_pending_review', None)
    if pending is None or window.jobs.busy:
        return
    window._unreal_pending_review = None
    try:
        store, project, review = pending.store, pending.project, pending.review
        if (window.controller.store is not store or window.controller.require_project() != project
                or window.controller.dirty or store.load() != project):
            raise ProjectConflict('Saved character changed during Unreal source review; review it again')
        dialog = UnrealExportDialog(review, window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        destination = plan_destination(Path(dialog.destination.text().strip()), store.root)
        selected = Path(dialog.editor.text().strip())
        unreal = regular_file(selected, selected.parent, 512*1024*1024)
        editor_identity = identity(unreal)
        permissions = dialog.permissions()
        from .hand_workflow import _executable
        blender = _executable(window)
        if blender is None:
            return
        if (window.controller.store is not store or store.load() != project
                or window.controller.require_project() != project or window.controller.dirty):
            raise ProjectConflict('Saved character changed during Unreal export review; review it again')
        cancel = Event()
        progress = UnrealExportProgress(window, cancel)
        window._unreal_export_progress = progress
        window._unreal_export_context = (store, project, review)
        window._clear_preview()
        window._submit('unreal_export', lambda: run_desktop_unreal_export(
            store, review=review, permissions=permissions, editor_identity=editor_identity,
            destination=destination, blender_exe=blender, unreal_exe=unreal, cancel=cancel,
            progress=progress.changed.emit), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        close_unreal_progress(window)
        window._error(str(error))


def close_unreal_progress(window):
    progress = getattr(window, '_unreal_export_progress', None)
    if progress is not None:
        window._unreal_export_progress = None
        progress.close()


def finish_unreal_export(window, result):
    close_unreal_progress(window)
    try:
        from ucc.jobs.unreal_export import UnrealExport
        if not isinstance(result, UnrealExport):
            raise ValidationError('Unexpected Unreal export result')
        context = getattr(window, '_unreal_export_context', None)
        if context is None:
            raise ValidationError('Unreal export has no matching reviewed desktop operation')
        store, project, review = context
        if (window.controller.store is not store or window.controller.require_project() != project
                or window.controller.dirty or store.load() != project):
            raise ProjectConflict('Saved character context changed; inspect the retained export separately')
        # The transaction verifies the entire final payload on its worker before returning.
        # Confirm only the bounded receipt here so large mesh hashing cannot freeze Qt.
        receipt = regular_file(result.destination/'export_receipt.json', result.destination, 2*1024*1024)
        if _digest(receipt) != result.receipt_sha256:
            raise ValidationError('Unreal export receipt changed after final verification')
        record = read_json(receipt, 2*1024*1024)
        if (type(record.get('schema_version')) is not int or record['schema_version'] != 1
                or record.get('policy') != 'UCC_UNREAL_EXPORT_TRANSACTION_V1'
                or record.get('request_sha256') != result.request_sha256
                or record.get('master_sha256') != result.master_sha256
                or result.master_sha256 != dict((s.asset_id, s.sha256) for s in review.sources)['master']
                or any(record.get(key) is not True for key in
                       ('export_published', 'final_payload_verified', 'private_static_native_verified',
                        'engine_import_verified', 'source_parity_verified'))
                or any(record.get(key) is not False for key in
                       ('shader_compilation_verified', 'runtime_gpu_verified', 'pie_verified', 'player_build_verified',
                        'animation_clips_verified', 'visual_quality_approved', 'distribution_license_review_complete',
                        'cloud_transmission_authorized', 'project_metadata_changed'))
                or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in
                       (result.maximum_source_position_error_m, result.maximum_normal_angle_deg))
                or record.get('maximum_source_position_error_m') != result.maximum_source_position_error_m
                or record.get('maximum_normal_angle_deg') != result.maximum_normal_angle_deg):
            raise ValidationError('Unreal receipt differs from this reviewed published export')
        window.log.setPlainText(
            'Private Unreal character project created:\n'+str(result.destination)+'\n'
            'Fresh Blender checks and static rig, morph, material and scene native checks passed on the published project.\n'
            'Open this project with the reviewed Unreal Editor and inspect its saved character scene.\n'
            'No animation clips are included. Editable master and history were preserved. '
            'Shader/GPU rendering, PIE, player builds, visual quality and public distribution remain unapproved.')
        window.statusBar().showMessage('Private Unreal export verified; review the project and retained receipt')
    except (UCCError, OSError, ValueError, TypeError, KeyError) as error:
        window._error('Unreal output could not be confirmed. Inspect retained logs and receipt: '+str(error))


def unreal_export_error(window, error):
    close_unreal_progress(window)
    # Preserve rollback failure/path diagnostics even when cancellation was requested.
    window._error('Unreal export did not complete. Inspect retained staging/logs before retrying. '+str(error))
