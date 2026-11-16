"""Adopt a validated private cache without lending native-edit controls to it."""
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtWidgets import QDockWidget

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.storage import MAX_JSON_BYTES
from .motion_viewer import MotionViewer


class TargetActionViewer(MotionViewer):
    """Use the existing transport, guarding activation and its live authority."""
    def __init__(self, guard, parent=None):
        super().__init__(parent)
        self.guard = guard
        self.guard_timer = QTimer(self)
        self.guard_timer.setInterval(500)
        self.guard_timer.timeout.connect(self._guard_playing)
        self.loop.setChecked(False)

    def toggle(self):
        if self.clock is not None and not self.guard():
            return
        super().toggle()
        if self.clock is not None and self.clock.playing:
            self.guard_timer.start()
        else:
            self.guard_timer.stop()

    def seek(self, frame):
        if self.clock is not None and not self.guard():
            return
        super().seek(frame)

    def tick(self):
        super().tick()
        if self.clock is None or not self.clock.playing:
            self.guard_timer.stop()

    def _guard_playing(self):
        if self.clock is not None and self.clock.playing:
            self.guard()

    def clear(self):
        self.guard_timer.stop()
        super().clear()

    def _failed(self, error):
        self.guard_timer.stop()
        super()._failed(error)


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
            dock = QDockWidget('Registered clip — private one-shot target preview', window)
            dock.setObjectName('RegisteredTargetActionPreviewDock')
            dock.setWidget(viewer)
            window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            window._target_action_viewer = viewer
            window._target_action_dock = dock
        viewer = window._target_action_viewer
        viewer.loop.setChecked(False)
        viewer.show_cache(cache)
        viewer.status.setText(f'Registered source: {result.clip_id}\n' + viewer.status.text())
        viewer.highlight.setChecked(False)
        viewer.focus.setChecked(False)
        for widget in (viewer.loop, viewer.try_fit, viewer.review_body, viewer.highlight,
                       viewer.focus, viewer.next_flagged, viewer.max_pairs, viewer.inspection,
                       viewer.variant, viewer.surface_status):
            widget.setEnabled(False)
            widget.hide()
        viewer.note.setText('Private one-shot preview • source frames 2–301 / saved target frames 1–300 • editing, usable-action, visual and engine quality unapproved')
        window._clear_native_review()
        window.mesh_dock.hide()
        window._target_action_owner = context.store
        window._target_action_catalog_parent = context.database.parent
        window._target_action_identities = {Path(path): expected for path, expected in identities.items()}
        window._target_action_result = result
        window._target_action_dock.show()
        window._target_action_dock.raise_()
    except BaseException:
        clear_target_action_preview(window)
        raise
