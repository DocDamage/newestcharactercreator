"""Explicit registered-source native review with background authority admission."""
from dataclasses import dataclass
import logging
from pathlib import Path
from threading import Event
from time import monotonic
import os

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.native_body import NativeBodyPreview, preview_native_body
from ucc.jobs.native_playback import NativePlayback, prepare_native_playback
from ucc.jobs.native_preview_profiles import find_catalog_preview_profile
from ucc.jobs.native_source_authority import NativeProofReceipt, NativeSourceAuthority, bind_native_catalog_source
from ucc.jobs.persistent_native_playback import PersistentNativePreview
from ucc.jobs.runner import WorkerFailure
from .generation import bundled_worker_path
from .registered_native_binding import (
    clear_registered_native, guard_registered_native, install_binding, selected_clip,
)
from .registered_native_viewer import RegisteredNativeDock, RegisteredNativeViewer

# These are TOTAL producer-operation budgets, shared across its child workers.
# The manual workflow retains the existing API defaults.
REGISTERED_BODY_TIMEOUT_S = 900
REGISTERED_PLAYBACK_TIMEOUT_S = 1800
_LOG = logging.getLogger(__name__)

_PROGRESS_LABELS = {
    'SOURCE_AUTHORITY': 'Checking source permissions',
    'REUSE_VERIFY': 'Checking the retained playback',
    'INSPECT_SOURCE': 'Measuring the source motion',
    'VERIFY_BODY_FIRST': 'Checking motion on the saved rig',
    'VERIFY_BODY_SECOND': 'Checking the rig motion independently',
    'REOPEN_BODY': 'Reopening the verified motion',
    'BUILD_CACHE': 'Preparing frames for playback',
    'VERIFY_SURFACE': 'Checking the animated skin',
    'CHECK_CACHE': 'Validating the prepared frames',
    'FINAL_GUARD': 'Checking playback permissions and files',
}


class _RegisteredNativeProgress(QObject):
    """Update only the active inline request from queued worker messages."""

    changed = Signal(object, str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.token = None
        self.stage = 'SOURCE_AUTHORITY'
        self.started = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.changed.connect(self.advance, Qt.ConnectionType.QueuedConnection)

    def begin(self, token):
        self.token = token
        self.stage = 'SOURCE_AUTHORITY'
        self.started = monotonic()
        self.timer.start()

    def pending(self):
        pending = getattr(self.window, '_registered_native_pending', None)
        return pending if pending is not None and pending.inline and pending.token is self.token else None

    @Slot(object, str)
    def advance(self, token, stage):
        pending = self.pending()
        if pending is None or token is not self.token or pending.cancel.is_set() or stage not in _PROGRESS_LABELS:
            return
        self.stage = stage
        self.refresh()

    @Slot()
    def refresh(self):
        if self.pending() is None:
            self.timer.stop()
            return
        self.window._refresh_animation_preview()


def registered_native_progress_text(window) -> str:
    progress = getattr(window, '_registered_native_progress', None)
    pending = progress.pending() if progress is not None else None
    if pending is None:
        return 'Preparing playback…'
    if pending.cancel.is_set():
        return 'Cancelling preview…'
    minutes, seconds = divmod(int(monotonic() - progress.started), 60)
    return f'{_PROGRESS_LABELS[progress.stage]}… · {minutes}:{seconds:02d} elapsed'


def _begin_inline_progress(window, token):
    progress = getattr(window, '_registered_native_progress', None)
    if progress is None:
        progress = _RegisteredNativeProgress(window)
        window._registered_native_progress = progress
    progress.begin(token)
    return lambda stage: progress.changed.emit(token, stage)


@dataclass(frozen=True, slots=True)
class RegisteredNativePending:
    token: object
    store: ProjectStore
    root: Path
    project: CharacterProject
    clip_id: str
    cancel: Event
    preview: NativeBodyPreview | None = None
    inline: bool = False


@dataclass(frozen=True, slots=True)
class RegisteredNativeCompletion:
    token: object
    value: NativeBodyPreview | NativePlayback | None
    identities: tuple[tuple[Path, tuple[int, int, int, int]], ...]
    inline_preview: NativeBodyPreview | None = None
    restored: bool = False


def _identities(value, cancel, previous=None):
    """Union original backend receipts; no GUI hashing or later proof baseline."""
    if (not isinstance(value.source_authority, NativeSourceAuthority)
            or not isinstance(value.proof_receipt, NativeProofReceipt)):
        raise ValidationError('Registered native result is missing its original proof authority')
    identities = dict(previous or {})
    # A playback proof must itself carry the full original preview proof;
    # a detached dictionary is never a substitute for its live typed guard.
    if previous is not None:
        guarded = dict(value.source_authority.watched_identities)
        for path, stamp in value.proof_receipt.watched_identities.items():
            if path in guarded and guarded[path] != stamp:
                raise ValidationError('Registered source and playback proof identities disagree')
            guarded[path] = stamp
        if any(path not in guarded or guarded[path] != stamp for path, stamp in previous.items()):
            raise ValidationError('Registered playback lost an original preview proof authority')
    for receipt in (value.source_authority, value.proof_receipt):
        if receipt.guard(cancel=cancel) is not True:
            raise ValidationError('Registered native proof guard did not confirm its original inputs')
        for path, stamp in receipt.watched_identities.items():
            if path in identities and identities[path] != stamp:
                raise ValidationError('Registered native proof receipts disagree on original identities')
            identities[path] = stamp
        if not set(receipt.watch_paths).issubset(receipt.watched_identities):
            raise ValidationError('Registered proof watch set is incomplete')
    if value.source_authority.guard(cancel=cancel) is not True:
        raise ValidationError('Registered source policy was not confirmed after final proof checks')
    return tuple(identities.items())


def _executable(window):
    executable = window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        filename, _ = QFileDialog.getOpenFileName(window, 'Choose installed Blender for registered native preview', '',
            'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
        if not filename:
            return None
        executable = Path(filename)
        if executable.is_symlink() or not executable.is_file():
            raise ValidationError('Choose a regular installed Blender executable')
        window._blender_executable = executable
    return executable


def start_registered_native_body(window) -> None:
    _start_body(window, inline=False)


def start_inline_preview(window) -> None:
    """Resume current guarded playback or prepare the selected private preview."""
    result = getattr(window, '_native_playback', None)
    viewer = window.motion_viewer
    if (not window.jobs.busy and isinstance(result, NativePlayback)
            and isinstance(viewer, RegisteredNativeViewer) and viewer.cache is result.cache
            and viewer.clock is not None and isinstance(result.source_authority, NativeSourceAuthority)
            and guard_registered_native(window, result.source_authority)):
        try:
            if window._catalog_path() == result.source_authority.database_path:
                _reveal_registered_playback(window, result)
                _play_registered(window.motion_viewer)
                return
        except (UCCError, OSError, ValueError) as error:
            clear_registered_native(window)
            window._error(str(error))
            return
    _start_body(window, inline=True)


def _start_body(window, *, inline: bool, look_on_disk: bool = True) -> None:
    try:
        if window.jobs.busy:
            raise ValidationError('Another local task is still running')
        store = window.controller.store
        if store is None or not window.controller.has_project:
            raise ValidationError('Open a saved character project first')
        project = window.controller.require_project()
        if window.controller.dirty or project.master_blend is None:
            raise ValidationError('Save the character and its Blender master first')
        clip_id = selected_clip(window)
        if clip_id is None:
            raise ValidationError('Select one measured FBX source in the catalog')
        if not inline:
            answer = QMessageBox.question(window, 'Registered native skin preview',
                'Test the selected catalog clip on this saved character using private Blender copies? '
                'The existing reviewed catalog policy must already permit local preview. '
                'This confirmation grants no new rights. Visual, contact and engine quality remain unapproved.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        worker = bundled_worker_path()
        profile = Path(window.animations.native_body_profile.text()) if window.animations.native_body_profile.text().strip() else None
        include_hands = window.animations.native_include_hands.isChecked()
        database = window._catalog_path()
        local_data = (QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
                      if inline and profile is None and not include_hands else '')
        index_root = Path(local_data) / 'registered-previews-v1' if local_data else None
        check_retained = index_root is not None and look_on_disk
        executable = window._blender_executable
        if not check_retained or executable is not None:
            executable = _executable(window)
            if executable is None:
                return
        if inline and (window.jobs.busy or window.controller.store is not store or window.controller.dirty
                or not window.controller.has_project or window.controller.require_project() != project
                or selected_clip(window) != clip_id):
            raise ValidationError('The saved character or selected clip changed before preview')
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error)); return
    window._clear_native_review()
    pending = RegisteredNativePending(object(), store, store.root.resolve(), project, clip_id, Event(), inline=inline)
    window._registered_native_pending = pending
    progress = _begin_inline_progress(window, pending.token) if inline else None

    def prepare():
        if pending.cancel.is_set():
            raise WorkerFailure('Registered native preview cancelled')
        with AnimationCatalog(database, read_only=True) as catalog:
            asset_id = clip_id.rsplit('#clip-', 1)[0]
            entry = catalog.library.get(asset_id)
            if entry is None:
                raise ValidationError('Selected registered source is no longer available')
            catalog.library.require_permission(asset_id, 'local_preview')
        authority = bind_native_catalog_source(database, clip_id, expected_source_sha256=entry.sha256,
            expected_policy=entry.policy, local_preview_confirmed=True, cancel=pending.cancel)
        selected_profile = profile
        if pending.inline and selected_profile is None and not include_hands:
            selected_profile = find_catalog_preview_profile(authority, Path(project.master_blend).stem)
        retained = (PersistentNativePreview(index_root, store, project, authority, selected_profile, worker,
                                           pending.cancel) if index_root is not None else None)
        if retained is not None and check_retained:
            progress('REUSE_VERIFY')
            try:
                reopened = retained.restore(executable)
                if reopened is not None:
                    return RegisteredNativeCompletion(pending.token, reopened, _identities(reopened, pending.cancel),
                                                      restored=True)
            except (UCCError, OSError, ValueError, KeyError, TypeError, IndexError):
                if pending.cancel.is_set():
                    raise
                _LOG.debug('Retained native playback is unavailable', exc_info=True)
        if executable is None:
            return RegisteredNativeCompletion(pending.token, None, ())
        context = None
        if retained is not None:
            try:
                context = retained.capture_context(executable)
            except (UCCError, OSError, ValueError):
                if pending.cancel.is_set():
                    raise
                _LOG.debug('Native playback cannot be retained on disk', exc_info=True)
        inline_options = {'render_private_frames': False, 'progress': progress} if pending.inline else {}
        preview = preview_native_body(store, source_fbx=authority.source_path, mapping_profile=selected_profile,
            blender_exe=executable, worker_script=worker, permission=authority.policy,
            expected_project_id=project.project_id, expected_revision=project.revision,
            expected_master_blend=project.master_blend, cancel=pending.cancel,
            include_hands=include_hands, source_authority=authority, timeout_s=REGISTERED_BODY_TIMEOUT_S,
            **inline_options)
        identities = _identities(preview, pending.cancel)
        if pending.cancel.is_set():
            raise WorkerFailure('Registered native preview cancelled; private records are retained')
        if not pending.inline:
            return RegisteredNativeCompletion(pending.token, preview, identities)
        result, playback_identities = _prepare_playback(pending, preview, dict(identities), executable, worker,
                                                       progress=progress)
        if context is not None:
            try:
                retained.save(result, context)
            except (UCCError, OSError, ValueError):
                if pending.cancel.is_set():
                    raise
                _LOG.debug('Could not retain verified native playback', exc_info=True)
        return RegisteredNativeCompletion(pending.token, result, playback_identities, inline_preview=preview)

    window._submit('registered_native_body', prepare, cancel=pending.cancel)


def start_registered_native_playback(window) -> None:
    if window.jobs.busy:
        window._error('Another local task is still running'); return
    preview = getattr(window, '_native_review', None)
    authority = getattr(preview, 'source_authority', None)
    if authority is None or not guard_registered_native(window, authority):
        clear_registered_native(window)
        window._error('Validate the selected registered native source again before playback'); return
    if getattr(window, '_native_playback', None) is not None:
        window._error('Registered motion is already loaded. Use its transport controls or validate a new body preview.'); return
    try:
        executable = _executable(window)
        if executable is None:
            return
        worker = bundled_worker_path()
        store = window.controller.store
        project = window.controller.require_project()
        if (window._native_review is not preview or not guard_registered_native(window, authority)
                or preview.proof_receipt is None):
            raise ValidationError('Registered source changed before playback preparation')
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error)); return
    pending = RegisteredNativePending(object(), store, store.root.resolve(), project, authority.clip_id, Event(), preview)
    original = dict(window._registered_native_binding[4])
    # Own read-only catalog checks can change SHM coordination read marks.
    # Hide/drop the live view and its watches while the background guard runs;
    # the pending wrapper retains the ORIGINAL preview/authority, never a new baseline.
    clear_registered_native(window, cancel_pending=False)
    window._registered_native_pending = pending

    def prepare():
        result, identities = _prepare_playback(pending, preview, original, executable, worker)
        return RegisteredNativeCompletion(pending.token, result, identities)

    window._submit('registered_native_playback', prepare, cancel=pending.cancel)


def _prepare_playback(pending, preview, original, executable, worker, *, progress=None):
    authority = preview.source_authority
    authority.guard(cancel=pending.cancel)
    preview.proof_receipt.guard(cancel=pending.cancel)
    result = prepare_native_playback(pending.store, preview, source_fbx=authority.source_path,
        permission=authority.policy, blender_exe=executable, worker_script=worker, cancel=pending.cancel,
        timeout_s=REGISTERED_PLAYBACK_TIMEOUT_S, progress=progress)
    if progress is not None:
        progress('FINAL_GUARD')
    identities = _identities(result, pending.cancel, previous=original)
    if pending.cancel.is_set():
        raise WorkerFailure('Registered playback cancelled; private records are retained')
    return result, identities


def finish_registered_native(window, result) -> bool:
    """Consume opaque registered completions before any legacy publication branch."""
    pending = getattr(window, '_registered_native_pending', None)
    if pending is None:
        return False
    if not isinstance(result, RegisteredNativeCompletion):
        clear_registered_native(window)
        window._error('Registered native preparation returned an invalid completion'); return True
    if result.token is not pending.token:
        return False
    window._registered_native_pending = None
    value = result.value
    try:
        if (pending.cancel.is_set() or window.controller.store is not pending.store
                or pending.store.root.resolve() != pending.root or window.controller.dirty
                or not window.controller.has_project or window.controller.require_project() != pending.project
                or selected_clip(window) != pending.clip_id):
            raise ValidationError('Registered selection changed or was cancelled; private results are retained')
        expected_type = NativePlayback if pending.inline or pending.preview is not None else NativeBodyPreview
        if value is None and pending.inline and not result.restored:
            window._registered_native_pending = pending

            def prompt_when_idle():
                if window._registered_native_pending is not pending:
                    return
                if window.jobs.busy:
                    QTimer.singleShot(25, prompt_when_idle)
                    return
                window._registered_native_pending = None
                if not pending.cancel.is_set():
                    _start_body(window, inline=True, look_on_disk=False)

            QTimer.singleShot(0, prompt_when_idle)
            return True
        if not isinstance(value, expected_type):
            raise ValidationError('Registered native preparation returned an invalid result')
        inline_preview = result.inline_preview
        if result.restored:
            if not pending.inline or inline_preview is not None:
                raise ValidationError('Retained playback can only open in the Animation Library')
        elif pending.inline:
            if (not isinstance(inline_preview, NativeBodyPreview)
                    or not isinstance(inline_preview.proof_receipt, NativeProofReceipt)
                    or inline_preview.source_authority is not value.source_authority
                    or (inline_preview.project_id, inline_preview.revision, inline_preview.master_sha256,
                        inline_preview.source_sha256) != (value.project_id, value.revision, value.master_sha256,
                                                           value.source_sha256)):
                raise ValidationError('Inline playback lost its exact original body preview')
        elif inline_preview is not None:
            raise ValidationError('Unexpected inline body preview in a manual completion')
        if isinstance(value, NativePlayback) and window._native_review is not None:
            raise ValidationError('Registered native review was superseded before playback')
        authority = value.source_authority
        if (not isinstance(authority, NativeSourceAuthority) or not isinstance(value.proof_receipt, NativeProofReceipt)
                or authority.clip_id != pending.clip_id
                or value.project_id != pending.project.project_id or value.revision != pending.project.revision
                or value.source_sha256 != authority.source_sha256
                or (pending.inline and window._catalog_path() != authority.database_path)):
            raise ValidationError('Registered native result lost its source authority')
        if isinstance(value, NativePlayback) and (
                value.cache.frame_count != authority.clock.frame_count or value.cache.fps != authority.clock.fps
                or value.cache.source_first_frame != authority.clock.source_first_frame):
            raise ValidationError('Registered native playback differs from the stored complete source clock')
        install_binding(window, pending.store, pending.project, authority, result.identities, value.proof_receipt)
        if isinstance(value, NativeBodyPreview):
            from .native_body import native_result_text
            window._native_review = value
            window.animations.open_native_animation.setEnabled(False)
            window.animations.open_native_renders.setEnabled(False)
            window.animations.load_native_motion.setEnabled(value.evidence.get('skin_deformation_policy') in {
                'BOUND_CORRECTIVE_SMOOTH_V1', 'BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2'})
            window.log.setPlainText(native_result_text(value)+'\n'+_source_text(authority)+
                '\nRegistered source policy remains bound; private-open and fitting actions are unavailable in this mode.')
        else:
            window._native_review = inline_preview if pending.inline else pending.preview
            _publish_registered_playback(window, value)
            if pending.inline:
                _play_registered(window.motion_viewer)
        return True
    except (UCCError, OSError, ValueError) as error:
        clear_registered_native(window)
        window._error(str(error)); return True


def _publish_registered_playback(window, result: NativePlayback) -> None:
    if not guard_registered_native(window, result.source_authority):
        raise ValidationError('Registered native authority changed before display')
    old = window.motion_viewer
    if not isinstance(old, RegisteredNativeViewer):
        if old is not None:
            old.clear()
            dock = window.motion_dock
            window.removeDockWidget(dock)
            dock.hide(); dock.deleteLater()
        window.motion_viewer = RegisteredNativeViewer(lambda: guard_registered_native(window), window)
        viewer = window.motion_viewer
        viewer.invalidated.connect(lambda: clear_registered_native(window,
            message='Registered private playback authority is no longer current.')
            if window.motion_viewer is viewer else None)
        window.motion_dock = RegisteredNativeDock(window)
        window.motion_dock.setObjectName('RegisteredNativeSkinDock')
        window.motion_dock.setWidget(window.motion_viewer)
        mount = getattr(window, 'mount_animation_motion', None)
        if mount is None:
            window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, window.motion_dock)
        else:
            mount(window.motion_dock)
    window._native_playback = result
    window.animations.load_native_motion.setEnabled(False)
    window._fitted_playback = window._body_contact_review = None
    window.motion_viewer.show_cache(result.cache)
    if window._native_playback is not result or not guard_registered_native(window, result.source_authority):
        raise ValidationError('Registered playback changed during adoption')
    _reveal_registered_playback(window, result)
    window.log.setPlainText('REGISTERED PRIVATE NATIVE SKIN PLAYBACK\n'
        +_source_text(result.source_authority)+'\n'
        f'{result.cache.frame_count} complete cached frames at {result.cache.fps:g} fps.\n'
        'Existing catalog source rights remain bound. Visual/contact/engine quality and usable-motion acceptance remain unapproved.')


def _reveal_registered_playback(window, result: NativePlayback) -> None:
    window.mesh_dock.hide()
    reveal = getattr(window, 'reveal_animation_motion', None)
    if reveal is None:
        window.motion_dock.show()
        window.motion_dock.raise_()
    else:
        reveal()
    if window._native_playback is not result or not guard_registered_native(window, result.source_authority):
        raise ValidationError('Registered playback changed while revealing the viewer')


def _play_registered(viewer: RegisteredNativeViewer) -> None:
    # Background success can precede busy-clear on the containing workspace.
    if viewer.clock is not None and not viewer.clock.playing:
        viewer.toggle()
    if viewer.clock is None or not viewer.clock.playing:
        raise ValidationError('The registered preview could not start playback')


def _source_text(authority) -> str:
    clock = authority.clock
    return (f'Registered clip: {authority.clip_id}\n'
        f'Stored source frames {clock.source_first_frame}â€“{clock.source_last_frame} at {clock.fps:g} fps; '
        f'sample span {clock.sample_span_s:.6f} s, nominal coverage {clock.nominal_coverage_s:.6f} s.\n'
        f'Source SHA-256: {authority.source_sha256}')
