"""Adopt a validated private cache without lending native-edit controls to it."""
from hashlib import sha256
from pathlib import Path
import time
from typing import Callable

from PySide6.QtCore import QEvent, QFileSystemWatcher, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSpinBox, QWidget

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.storage import MAX_JSON_BYTES
from ucc.preview.idle_loop_clock import IdleLoopClock
from ucc.preview.playback_window import PlaybackWindow, WindowPlaybackClock
from ucc.preview.motion_cache import MotionCache
from .motion_viewer import MotionViewer


_PREVIEW_NOTE = ('Private one-shot preview • source frames 2–301 / saved target frames 1–300 • '
                 'editing, usable-action, visual and engine quality unapproved')


class TargetActionViewer(MotionViewer):
    """Use the existing transport, guarding activation and its live authority."""
    review_idle_loop_requested = Signal()

    def __init__(self, guard: Callable[[], bool], parent: QWidget | None = None):
        super().__init__(parent)
        self.guard = guard
        self._idle_guard = None
        self._idle_watcher = None
        self._idle_decision = None
        self.guard_timer = QTimer(self)
        self.guard_timer.setInterval(500)
        self.guard_timer.timeout.connect(self._guard_playing)
        self.loop.setChecked(False)
        self.review_window: PlaybackWindow | None = None
        self.target_start = QSpinBox()
        self.target_end = QSpinBox()
        for control in (self.target_start, self.target_end):
            control.setRange(1, 300)
        self.target_end.setValue(300)
        bounds = QHBoxLayout()
        for title, control in (('Target start', self.target_start), ('Target end', self.target_end)):
            label = QLabel(title)
            label.setTextFormat(Qt.TextFormat.PlainText)
            bounds.addWidget(label); bounds.addWidget(control)
        self.layout.addLayout(bounds)
        self.apply_window = QPushButton('Apply review window')
        self.go_start = QPushButton('Go to window start')
        self.review_idle_loop = QPushButton('Review idle loop…')
        self.review_idle_loop.setVisible(False)
        self.record_idle_decision = QPushButton('Record visual decision…')
        self.record_idle_decision.setVisible(False)
        self.loop.setText('Loop preview')
        self.loop.setVisible(False)
        actions = QHBoxLayout()
        actions.addWidget(self.apply_window); actions.addWidget(self.go_start)
        actions.addWidget(self.review_idle_loop)
        actions.addWidget(self.record_idle_decision)
        self.layout.addLayout(actions)
        self.window_status = QLabel('No review window loaded.')
        self.window_status.setTextFormat(Qt.TextFormat.PlainText)
        self.window_status.setWordWrap(True)
        self.layout.addWidget(self.window_status)
        self.apply_window.clicked.connect(self.apply_review_window)
        self.go_start.clicked.connect(self.go_to_window_start)
        self.review_idle_loop.clicked.connect(self.review_idle_loop_requested.emit)
        self.record_idle_decision.clicked.connect(self._record_idle_decision)
        self._enable(False)

    def _enable(self, enabled: bool) -> None:
        super()._enable(enabled)
        self.loop.setEnabled(False)
        if hasattr(self, 'target_start'):
            for control in (self.target_start, self.target_end, self.apply_window, self.go_start):
                control.setEnabled(enabled)
            if self.review_window is not None and self.review_window.is_static:
                self.play.setEnabled(False)
            self.review_idle_loop.setEnabled(enabled)
            self.loop.setEnabled(enabled and self._idle_guard is not None and self.review_window == PlaybackWindow())
            self.record_idle_decision.setEnabled(enabled and self._idle_decision is not None)

    def show_cache(self, cache: MotionCache) -> None:
        if cache.frame_count != 300 or cache.fps != 30 or cache.source_first_frame != 2:
            raise ValidationError('Review windows require the complete registered 300-frame cache')
        super().show_cache(cache)
        self.review_window = PlaybackWindow()
        self.clock = WindowPlaybackClock(self.review_window)
        self._window_label()
        self._present()

    def _authorized(self) -> bool:
        try:
            if self.clock is not None and self.guard():
                return True
        except (UCCError, OSError, ValueError):
            pass
        self.clear()
        return False

    def _window_label(self) -> None:
        window = self.review_window
        self.window_status.setText(
            f'Review only: target {window.target_first_frame}–{window.target_last_frame}; '
            f'source {window.source_first_frame_selected}–{window.source_last_frame_selected}. '
            f'{window.sample_count} samples; sample span {window.sample_span_s:.6f} s; '
            f'nominal sample coverage {window.nominal_coverage_s:.6f} s. '
            'The original 300-frame cache and saved Action remain unchanged.')

    def offer_idle_loop_review(self, enabled: bool) -> None:
        self.review_idle_loop.setVisible(enabled)

    def install_idle_loop(self, guard: Callable[[], bool], watch_paths=(), *,
                          record_decision: Callable[[], None] | None = None) -> None:
        if self.review_window != PlaybackWindow() or not self._authorized() or not guard():
            raise ProjectConflict('The reviewed idle no longer matches the full target preview')
        if self._idle_guard is not None:
            self.clear_idle_loop_review()
        files = [str(path) for path in watch_paths if path.is_file()]
        if files:
            watcher = QFileSystemWatcher(self)
            if watcher.addPaths(files) or not guard():
                watcher.deleteLater()
                raise ProjectStorageError('Could not watch the current authored idle proof')
            watcher.fileChanged.connect(lambda _path: self._idle_file_changed(watcher))
            self._idle_watcher = watcher
        self._idle_guard = guard
        self._idle_decision = record_decision
        self.record_idle_decision.setVisible(record_decision is not None)
        self.record_idle_decision.setEnabled(record_decision is not None and not self._gpu_failed)
        self.loop.setVisible(True)
        self.loop.setEnabled(not self._gpu_failed)
        self.loop.setChecked(False)
        self.window_status.setText('Idle loop reviewed. Enable Loop preview to play continuously.')

    def _stop_idle_loop(self, *, block_paint: bool = False) -> None:
        self._idle_guard = None
        self._idle_decision = None
        self.record_idle_decision.setVisible(False)
        self.record_idle_decision.setEnabled(False)
        watcher = self._idle_watcher
        self._idle_watcher = None
        if watcher is not None:
            watcher.blockSignals(True)
            watcher.deleteLater()
        with QSignalBlocker(self.loop):
            self.loop.setChecked(False)
        self.loop.setEnabled(False)
        self.loop.setVisible(False)
        self.note.setText(_PREVIEW_NOTE)
        if self.canvas is not None and hasattr(self.canvas, 'clear_idle_loop_sample'):
            self.canvas.clear_idle_loop_sample(block_paint=block_paint)

    def _record_idle_decision(self) -> None:
        if self._idle_decision is not None and self._authorized() and self._idle_current():
            self._idle_decision()

    def _idle_file_changed(self, watcher) -> None:
        if watcher is not self._idle_watcher:
            return
        if isinstance(self.clock, IdleLoopClock):
            self._failed('Idle loop authority changed. Load and review the binding again.')
        else:
            self._stop_idle_loop()
            if self.review_window is not None:
                self._window_label()

    def _idle_current(self) -> bool:
        try:
            return self._idle_guard is not None and self._idle_guard()
        except (UCCError, OSError, ValueError):
            return False

    def clear_idle_loop_review(self) -> None:
        self.loop.setChecked(False)
        self._stop_idle_loop()

    def apply_review_window(self) -> None:
        if not self._authorized():
            return
        try:
            window = PlaybackWindow(self.target_start.value(), self.target_end.value())
            clock = WindowPlaybackClock(window)
        except (ValidationError, ValueError) as error:
            self.window_status.setText('Review window was not applied: ' + str(error))
            return
        # GUI callbacks are serialized. Stop the old clock before replacing it;
        # queued timeout/paint events subsequently read only this new frame.
        self.timer.stop(); self.guard_timer.stop()
        self._stop_idle_loop()
        self.review_window = window; self.clock = clock
        self.scrub.blockSignals(True)
        self.scrub.setRange(window.first_index, window.last_index)
        self.scrub.setValue(window.first_index)
        self.scrub.blockSignals(False)
        self.play.setEnabled(not window.is_static and not self._gpu_failed)
        self._window_label()
        self._present()

    def go_to_window_start(self) -> None:
        if not self._authorized():
            return
        self.timer.stop(); self.guard_timer.stop()
        self.clock.reset(time.monotonic())
        self._present()
        if isinstance(self.clock, IdleLoopClock):
            self.guard_timer.start()

    def _connect_canvas(self, canvas):
        canvas.failed.connect(lambda error: self._failed(error) if self.canvas is canvas else None)

    def _loop_changed(self, checked):
        active = isinstance(self.clock, IdleLoopClock)
        if self.clock is None or (checked and (self.review_window != PlaybackWindow()
                or not self._idle_current() or not hasattr(self.canvas, 'set_idle_loop_sample'))):
            with QSignalBlocker(self.loop):
                self.loop.setChecked(False)
            return
        if checked == active:
            return
        self.timer.stop()
        self.guard_timer.stop()
        frame = self.clock.frame
        self.clock = IdleLoopClock() if checked else WindowPlaybackClock(self.review_window)
        self.clock.seek(frame, time.monotonic())
        if not checked:
            self.canvas.clear_idle_loop_sample()
            self._window_label()
            self.note.setText(_PREVIEW_NOTE)
        else:
            self.guard_timer.start()
            self.window_status.setText('Private continuous idle preview • 300 samples • 10-second cycle')
            self.note.setText('Private continuous idle preview • visual quality and engine use pending')
        self._present()

    def toggle(self):
        if not self._authorized():
            return
        if self.review_window is not None and self.review_window.is_static:
            self.timer.stop(); self.guard_timer.stop()
            return
        super().toggle()
        if self.clock is not None and (self.clock.playing or isinstance(self.clock, IdleLoopClock)):
            self.guard_timer.start()
        else:
            self.guard_timer.stop()

    def seek(self, frame):
        if not self._authorized():
            return
        if self.review_window is not None and not self.review_window.contains_index(frame):
            self.window_status.setText('Select a frame inside the applied review window.')
            return
        super().seek(frame)

    def _present(self):
        if self.clock is None:
            return
        window = getattr(self, 'review_window', None)
        if window is not None and not window.contains_index(self.clock.frame):
            self._failed('A frame outside the applied review window was refused')
            return
        if isinstance(self.clock, IdleLoopClock):
            if not self._idle_current():
                self._failed('Idle loop authority changed. Load and review the binding again.')
                return
            self.canvas.set_idle_loop_sample(self.clock.sample, self._idle_current)
        super()._present()
        if window is not None:
            frame = self.clock.frame
            self.position.setText(f'Source frame {frame + self.cache.source_first_frame} • '
                f'target {frame + 1} / 300 • window {frame - window.first_index + 1} / '
                f'{window.sample_count} • window elapsed {(frame - window.first_index) / self.clock.fps:.3f} s')

    def tick(self):
        if self.clock is not None:
            self.clock.advance(time.monotonic())
            self._present()
        if self.clock is None or not self.clock.playing:
            self.timer.stop()
        if self.clock is None or (not self.clock.playing and not isinstance(self.clock, IdleLoopClock)):
            self.guard_timer.stop()

    def _guard_playing(self):
        if isinstance(self.clock, IdleLoopClock) and not self._idle_current():
            self._failed('Idle loop authority changed. Load and review the binding again.')
            return
        if self.clock is not None and self.clock.playing:
            self._authorized()

    def clear(self):
        self.guard_timer.stop()
        self._stop_idle_loop(block_paint=True)
        self.offer_idle_loop_review(False)
        self.review_window = None
        super().clear()
        if hasattr(self, 'target_start'):
            self.target_start.setValue(1); self.target_end.setValue(300)
            self.window_status.setText('No review window loaded.')

    def _failed(self, error):
        self.clear()
        super()._failed(error)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.clear()
        super().closeEvent(event)


class _TargetActionDock(QDockWidget):
    """Closing the preview or its owner releases existing cache authority."""
    def __init__(self, title: str, owner: QMainWindow):
        super().__init__(title, owner)
        self._owner = owner
        owner.installEventFilter(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        clear_target_action_preview(self._owner)
        super().closeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._owner and event.type() == QEvent.Type.Close:
            clear_target_action_preview(self._owner)
        return super().eventFilter(watched, event)


def _small_digest(path: Path, maximum: int) -> str:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ProjectStorageError('Preview metadata is missing or redirected')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if not 0 < len(data) <= maximum:
        raise ProjectStorageError('Preview metadata exceeds its bound')
    return sha256(data).hexdigest()


def _stamp(path: Path) -> tuple[int, int, int, int]:
    if path.is_symlink() or path.is_junction() or path.resolve() != path:
        raise ProjectStorageError('A bound target-preview path was redirected')
    if not path.exists():
        return (0, 0, 0, 0)
    value = path.stat()
    if path.is_dir():
        return (value.st_dev, value.st_ino, 0, 0)
    if not path.is_file():
        raise ProjectStorageError('A bound target-preview input is not a regular file')
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def clear_target_action_preview(window, message: str | None = None) -> None:
    from .authored_idle_loop_workflow import cancel_idle_loop_review
    cancel_idle_loop_review(window)
    watcher = getattr(window, '_target_action_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files() + watcher.directories()
        if paths:
            watcher.removePaths(paths)
    viewer = getattr(window, '_target_action_viewer', None)
    if viewer is not None:
        viewer.clear()
        window._target_action_dock.hide()
    window._target_action_result = None
    window._target_action_identities = {}
    if message:
        window.log.setPlainText(message + '\nSaved private target Action records are retained; validate an explicit binding to load again.')


def refresh_target_action_preview(window) -> None:
    result = getattr(window, '_target_action_result', None)
    if result is None:
        return
    controller = window.controller
    if (not controller.has_project or controller.store is not window._target_action_owner
            or controller.dirty or controller.require_project().project_id != result.project_id
            or controller.require_project().revision != result.revision
            or result.clip_id not in controller.require_project().animations):
        clear_target_action_preview(window, 'The target preview is stale for the current saved character.')


def _check_catalog(window):
    from ucc.jobs.target_action import check_target_action_catalog
    context = window._target_action_preview_context
    identities = window._target_action_identities
    try:
        check_target_action_catalog(
            context.database, window._target_action_binding.source,
            expected_database_identity=identities[context.database][:2],
            expected_parent_identity=identities[context.database.parent][:2])
    except Exception as error:
        raise ProjectStorageError('Registered source catalog could not be revalidated: ' + str(error)[:1500]) from error


def _matches(context, path, expected):
    actual = _stamp(path)
    if path in (context.database, context.database.parent):
        return actual[:2] == expected[:2]
    return actual == expected


def _catalog_namespace(window):
    database = window._target_action_preview_context.database
    result = {}
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = Path(str(database) + suffix)
        if path.is_dir():
            raise ProjectStorageError('Catalog coordination path is not a regular file')
        result[path] = _stamp(path)[:2]
    return result


def _sync_catalog_watches(window, watcher):
    namespace = _catalog_namespace(window)
    previous = getattr(window, '_target_action_catalog_namespace', {})
    database = window._target_action_preview_context.database
    for suffix in ('-wal', '-journal'):
        path = Path(str(database) + suffix)
        registered = str(path) in watcher.files()
        if registered and previous.get(path) != namespace[path]:
            watcher.removePath(str(path))
            registered = False
        if namespace[path] != (0, 0) and not registered:
            if not watcher.addPath(str(path)):
                raise ProjectStorageError('Could not monitor catalog data coordination')
    window._target_action_catalog_namespace = namespace


def _active_guard(window):
    if getattr(window, '_target_action_result', None) is None:
        return False
    try:
        context = window._target_action_preview_context
        _check_context(window, context, window._target_action_preview_review, window._target_action_result)
        _check_catalog(window)
        _sync_catalog_watches(window, window._target_action_watcher)
        if any(not _matches(context, path, expected)
               for path, expected in window._target_action_identities.items()):
            raise ProjectStorageError('A bound target-preview input changed')
        return True
    except (UCCError, OSError, ValueError, KeyError) as error:
        clear_target_action_preview(window, str(error))
        return False


def _changed(window, path: str, *, directory: bool) -> None:
    try:
        if directory:
            parent = Path(path)
            if parent == window._target_action_catalog_parent:
                if _stamp(parent)[:2] != window._target_action_identities[parent][:2]:
                    raise ProjectStorageError('Registered source catalog parent was replaced')
                if _catalog_namespace(window) != window._target_action_catalog_namespace:
                    _check_catalog(window)
                    _sync_catalog_watches(window, window._target_action_watcher)
            for item, expected in window._target_action_identities.items():
                if item.parent == parent and not _matches(window._target_action_preview_context, item, expected):
                    raise ProjectStorageError('A bound target-preview input changed')
        else:
            database = window._target_action_preview_context.database
            if Path(path) in {database, Path(str(database)+'-wal'), Path(str(database)+'-journal')}:
                _check_catalog(window)
                _sync_catalog_watches(window, window._target_action_watcher)
            else:
                raise ProjectStorageError('A bound target-preview input changed')
    except (OSError, UCCError, ValueError, KeyError) as error:
        clear_target_action_preview(window, str(error))


def _check_context(window, context, review, result):
    controller = window.controller
    if (controller.store is not context.store or not controller.has_project or controller.dirty
            or controller.require_project() != context.project or result.project_id != context.project.project_id
            or result.revision != context.project.revision or result.clip_id != review.source.clip_id
            or result.clip_id not in context.project.animations
            or result.project_sha256 != review.project_sha256
            or result.master_sha256 != review.master_sha256 or result.source_sha256 != review.source.source_sha256):
        raise ProjectConflict('The saved target record belongs to a stale character or source selection')
    if _small_digest(context.store.file, MAX_JSON_BYTES) != review.project_sha256:
        raise ProjectConflict('Saved character metadata changed before preview publication')
    from ucc.jobs.animation_reference_storage import load_source_binding
    record = load_source_binding(context.store, result.project_id, result.clip_id)
    if canonical_digest(record) != review.source.source_binding_sha256:
        raise ProjectConflict('Registered source binding changed before preview publication')


def publish_target_action(window, context, review, result, *, selected_binding: str | None = None) -> None:
    from ucc.jobs.target_action import PreparedTargetAction, read_target_action_binding
    if type(result) is not PreparedTargetAction:
        raise ValidationError('Unexpected target-preview result type')
    _check_context(window, context, review, result)
    binding = read_target_action_binding(context.store, result.binding_sha256)
    expected_directory = context.store.root/'animations'/'actions'/result.binding_sha256
    if (result.directory != expected_directory or result.binding_path != expected_directory/'binding.json'
            or binding.sha256 != result.binding_sha256 or binding.source != review.source
            or binding.target.project_sha256 != review.project_sha256
            or binding.target.master_sha256 != result.master_sha256
            or binding.target.project_id != result.project_id or binding.target.revision != result.revision
            or (selected_binding is not None and selected_binding != result.binding_sha256)):
        raise ValidationError('Saved target-preview receipt differs from the exact reviewed selection')
    cache = result.cache
    if cache.frame_count != 300 or cache.fps != 30 or cache.source_first_frame != 2:
        raise ValidationError('The complete registered target-preview clock differs')
    identities = dict(result.watched_identities)
    if not 1 <= len(identities) == len(result.watched_identities) <= 256:
        raise ValidationError('Target-preview watch inventory is missing, duplicated or oversized')
    from ucc.jobs.animation_reference_storage import _binding_path
    expected_files = {result.directory/name: item.sha256 for name, item in binding.file_map.items()}
    expected_files.update({result.binding_path: result.binding_sha256,
        context.store.file: review.project_sha256,
        context.store.root/context.project.master_blend: review.master_sha256,
        review.source_path: review.source.source_sha256,
        _binding_path(context.store, result.clip_id): review.source.source_binding_sha256})
    if (dict(result.watched_inputs) != expected_files or len(result.watched_inputs) != len(expected_files)
            or not set(expected_files).issubset(identities)):
        raise ValidationError('Target-preview watches do not cover the exact saved proof and source closure')
    if context.database not in identities or context.database.parent not in identities:
        raise ValidationError('Target-preview catalog identity closure is missing')
    if any(not _matches(context, Path(path), expected) for path, expected in identities.items()):
        raise ProjectStorageError('Target-preview inputs changed before watches were installed')
    clear_target_action_preview(window)
    window._target_action_preview_context = context
    window._target_action_preview_review = review
    window._target_action_binding = binding
    window._target_action_catalog_parent = context.database.parent
    window._target_action_identities = {Path(path): expected for path, expected in identities.items()}
    _check_catalog(window)
    watcher = getattr(window, '_target_action_watcher', None)
    if watcher is None:
        watcher = QFileSystemWatcher(window)
        watcher.fileChanged.connect(lambda path: _changed(window, path, directory=False))
        watcher.directoryChanged.connect(lambda path: _changed(window, path, directory=True))
        window._target_action_watcher = watcher
    parents = {Path(path).parent for path in identities}
    paths = {Path(path) for path in identities if Path(path).exists()} | parents
    paths.add(context.database.parent)
    watcher.blockSignals(False)
    try:
        if watcher.addPaths(sorted(map(str, paths))):
            raise ProjectStorageError('Could not monitor every bound target-preview input')
        _sync_catalog_watches(window, watcher)
        if any(not _matches(context, Path(path), expected) for path, expected in identities.items()):
            raise ProjectStorageError('Target-preview inputs changed while installing watches')
        _check_catalog(window)
        _sync_catalog_watches(window, watcher)
        _check_context(window, context, review, result)
        if getattr(window, '_target_action_viewer', None) is None:
            viewer = TargetActionViewer(lambda: _active_guard(window))
            from .authored_idle_loop_workflow import start_idle_loop_review
            viewer.review_idle_loop_requested.connect(lambda: start_idle_loop_review(window))
            dock = _TargetActionDock('Registered clip — private one-shot target preview', window)
            dock.setObjectName('RegisteredTargetActionPreviewDock')
            dock.setWidget(viewer)
            mount = getattr(window, 'mount_animation_motion', None)
            if mount is not None:
                mount(dock)
            else:
                window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            window._target_action_viewer = viewer
            window._target_action_dock = dock
        viewer = window._target_action_viewer
        viewer.loop.setChecked(False)
        viewer.show_cache(cache)
        viewer.offer_idle_loop_review(binding.root_motion_policy == 'ARMATURE_ORIGIN_DISPLACEMENT_V1')
        viewer.status.setText(f'Registered source: {result.clip_id}\n' + viewer.status.text())
        viewer.highlight.setChecked(False)
        viewer.focus.setChecked(False)
        for widget in (viewer.loop, viewer.try_fit, viewer.review_body, viewer.highlight,
                       viewer.focus, viewer.next_flagged, viewer.max_pairs, viewer.inspection,
                       viewer.variant, viewer.surface_status):
            widget.setEnabled(False)
            widget.hide()
        viewer.note.setText(_PREVIEW_NOTE)
        window._clear_native_review()
        window.mesh_dock.hide()
        window._target_action_owner = context.store
        window._target_action_catalog_parent = context.database.parent
        window._target_action_identities = {Path(path): expected for path, expected in identities.items()}
        window._target_action_result = result
        reveal = getattr(window, 'reveal_animation_motion', None)
        if reveal is not None:
            reveal(window._target_action_dock)
        else:
            window._target_action_dock.show()
            window._target_action_dock.raise_()
    except BaseException:
        clear_target_action_preview(window)
        raise
