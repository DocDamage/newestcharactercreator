"""Original registered playback identities, GUI-only stat checks and closed watches."""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer

from ucc.core.errors import UCCError, ValidationError


def selected_clip(window) -> str | None:
    table = window.animations.catalog
    item = table.item(table.currentRow(), 0)
    return item.text()+'#clip-0000' if item is not None else None


def guard_registered_native(window, authority=None) -> bool:
    binding = getattr(window, '_registered_native_binding', None)
    if binding is None:
        return False
    owner, root, project, admitted, identities, proof = binding
    authority = admitted if authority is None else authority
    try:
        if (authority is not admitted or window.controller.store is not owner
                or owner.root.resolve() != root or window.controller.dirty
                or not window.controller.has_project
                or window.controller.require_project() != project
                or selected_clip(window) != authority.clip_id):
            return False
        return admitted.identities_current() and proof.identities_current()
    except (UCCError, OSError, ValueError):
        return False


def clear_registered_native(window, *, cancel_pending=True, message: str | None = None) -> None:
    pending = getattr(window, '_registered_native_pending', None)
    if cancel_pending and pending is not None:
        pending.cancel.set()
        window._registered_native_pending = None
    active = getattr(window, '_registered_native_binding', None) is not None
    window._registered_native_binding = None
    window._registered_native_epoch = None
    timer = getattr(window, '_registered_native_timer', None)
    if timer is not None:
        timer.stop()
        timer.deleteLater()
        window._registered_native_timer = None
    watcher = getattr(window, '_registered_native_watcher', None)
    if watcher is not None:
        watcher.blockSignals(True)
        paths = watcher.files()+watcher.directories()
        if paths:
            watcher.removePaths(paths)
        watcher.deleteLater()
        window._registered_native_watcher = None
    if active:
        viewer = getattr(window, 'motion_viewer', None)
        if viewer is not None:
            viewer.clear()
            window.motion_dock.hide()
        window._native_review = window._native_playback = None
        window._fitted_playback = window._body_contact_review = None
        for button in (window.animations.open_native_animation, window.animations.open_native_renders,
                       window.animations.load_native_motion):
            button.setEnabled(False)
    if message:
        window.log.setPlainText(message+'\nValidate the selected registered source again to reopen its private playback.')


def install_binding(window, owner, project, authority, identities, proof_receipt) -> None:
    """Use only the worker's ORIGINAL identities, including absent coordination files."""
    identities = dict(identities)
    expected = dict(authority.watched_identities)
    for path, stamp in proof_receipt.watched_identities.items():
        if path in expected and expected[path] != stamp:
            raise ValidationError('Registered source and proof identities disagree')
        expected[path] = stamp
    if identities != expected:
        raise ValidationError('Registered completion differs from its original guarded proof identities')
    existing = set(authority.watch_paths) | set(proof_receipt.watch_paths)
    absent = {path for path, stamp in identities.items() if stamp == (0, 0, 0, 0)}
    allowed_absent = {Path(str(authority.database_path)+suffix) for suffix in ('-wal', '-shm', '-journal')}
    if (not existing.issubset(identities) or not absent.issubset(allowed_absent)
            or any(path.parent not in existing for path in absent)):
        raise ValidationError('Registered source watch namespace is incomplete')
    clear_registered_native(window, cancel_pending=False)
    window._registered_native_binding = (owner, owner.root.resolve(), project, authority, identities, proof_receipt)
    if not guard_registered_native(window, authority):
        clear_registered_native(window)
        raise ValidationError('Registered inputs changed before publication')
    # Retired callbacks retain only an opaque token, never source/proof DTOs.
    epoch = object()
    window._registered_native_epoch = epoch
    watcher = QFileSystemWatcher(window)
    watcher.fileChanged.connect(lambda _: _invalidate(window, epoch))
    watcher.directoryChanged.connect(lambda _: _invalidate(window, epoch))
    window._registered_native_watcher = watcher
    watcher.blockSignals(False)
    if watcher.addPaths([str(path) for path in sorted(existing)]) or not guard_registered_native(window, authority):
        clear_registered_native(window)
        raise ValidationError('Registered inputs could not be monitored without a race')
    timer = QTimer(window)
    timer.setInterval(500)
    timer.timeout.connect(lambda: _check_epoch(window, epoch))
    window._registered_native_timer = timer
    timer.start()


def _invalidate(window, epoch) -> None:
    if getattr(window, '_registered_native_epoch', None) is epoch:
        clear_registered_native(window, message='A registered source or proof input changed.')


def _check_epoch(window, epoch) -> None:
    if (getattr(window, '_registered_native_epoch', None) is epoch
            and not guard_registered_native(window)):
        clear_registered_native(window, message='The registered source or saved character authority changed.')
