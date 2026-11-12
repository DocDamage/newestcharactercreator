"""Publish only current verified cached motion; watch bound inputs for changes."""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtWidgets import QDockWidget

from ucc.core.errors import ValidationError
from ucc.jobs.master_preview import _digest
from .motion_viewer import MotionViewer


def publish_playback(window,result):
    controller=window.controller;preview=window._native_review
    if not controller.has_project or controller.store is None or preview is None or controller.dirty:
        raise ValidationError("Character or animation selection changed; prepared motion stays private")
    project=controller.require_project()
    source=Path(window.animations.selected.text())
    if (project.project_id!=result.project_id or project.revision!=result.revision or
            controller.store.load()!=project or preview.source_sha256!=result.source_sha256 or
            source.is_symlink() or _digest(source)!=result.source_sha256 or
            _digest(controller.master_path())!=result.master_sha256):
        raise ValidationError("Saved character or source changed before playback publication")
    if window.motion_viewer is None:
        window.motion_viewer=MotionViewer()
        window.motion_dock=QDockWidget("Verified cached animation — private preview",window)
        window.motion_dock.setObjectName("MotionPreviewDock");window.motion_dock.setWidget(window.motion_viewer)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,window.motion_dock)
        window.mesh_action.parent().addAction(window.motion_dock.toggleViewAction())
        window._motion_watcher=QFileSystemWatcher(window)
        window._motion_watcher.fileChanged.connect(lambda _path:window._clear_native_review())
        window._motion_watcher.directoryChanged.connect(lambda _path:window._clear_native_review())
    watcher=window._motion_watcher
    watcher.blockSignals(True)
    old=watcher.files()+watcher.directories()
    if old:watcher.removePaths(old)
    paths=[source,controller.master_path(),controller.store.root/"project.ucc.json",Path(preview.mapping_profile_used),
           Path(preview.private_timeline),Path(preview.private_visual_review_blend)]
    # Watch parent directories too: an atomic replacement may remove a file watch.
    watch_paths=sorted({str(p) for p in paths}|{str(p.parent) for p in paths})
    failed=watcher.addPaths(watch_paths);watcher.blockSignals(False)
    if failed:
        window._clear_native_review();raise ValidationError("Could not monitor animation originals; playback was not published")
    window.motion_viewer.show_cache(result.cache)
    window.mesh_dock.hide();window.motion_dock.show();window.motion_dock.raise_()
    window.log.setPlainText("VERIFIED CACHED SKIN PLAYBACK READY IN UCC\n"
        f"{result.cache.frame_count} complete frames at {result.cache.fps:g} fps; full visible mesh.\n"
        "Play/Pause, frame scrub, loop, orbit, pan and zoom are available in the animation view.\n"
        "Blender evaluated this precomputed motion from the independently reopened saved Action.\n"
        "Original files unchanged. Joint correction is private; visual/contact/engine quality remains unapproved.")
