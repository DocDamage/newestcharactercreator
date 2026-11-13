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
        from .contact_fit import start_contact_fit
        window.motion_viewer.fit_requested.connect(lambda:start_contact_fit(window))
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
    window._native_playback=result
    window.mesh_dock.hide();window.motion_dock.show();window.motion_dock.raise_()
    window.log.setPlainText("VERIFIED CACHED SKIN PLAYBACK READY IN UCC\n"
        f"{result.cache.frame_count} complete frames at {result.cache.fps:g} fps; full visible mesh.\n"
        "Play/Pause, frame scrub, loop, orbit, pan and zoom are available in the animation view.\n"
        "Blender evaluated this precomputed motion from the independently reopened saved Action.\n"
        "Original files unchanged. Joint correction is private; visual/contact/engine quality remains unapproved.")


def publish_comparison(window,original,fitted):
    """Attach only the currently selected, verified original/fitted pair."""
    if (window._native_review is not fitted.original_preview or
        any(getattr(original,k)!=getattr(fitted,k) for k in ('project_id','revision','master_sha256','source_sha256')) or
        not window.animations.local_preview_review.isChecked()):
        raise ValidationError('Original/fitted selection or local-preview permission changed')
    preview=fitted.fitted_preview;bindings=preview.verification['bindings']
    paths={Path(preview.fit_policy_used):fitted.fit_policy_sha256,
           Path(preview.private_fitted_scene):fitted.fitted_scene_sha256,
           Path(preview.private_timeline):bindings['fit_report_sha256']}
    if (bindings['review_sha256']!=_digest(Path(window._native_review.private_visual_review_blend)) or
        bindings['timeline_sha256']!=_digest(Path(window._native_review.private_timeline)) or
        any(p.is_symlink() or not p.is_file() or _digest(p)!=digest for p,digest in paths.items())):
        raise ValidationError('Fitted comparison policy, source review or saved fitted evidence changed')
    publish_playback(window,original)
    watch_paths=sorted({str(p) for p in paths}|{str(p.parent) for p in paths})
    missing=[p for p in watch_paths if p not in window._motion_watcher.files()+window._motion_watcher.directories()]
    if missing and window._motion_watcher.addPaths(missing):
        window._clear_native_review();raise ValidationError('Could not monitor fitted originals; comparison not published')
    try:window.motion_viewer.show_comparison(original.cache,fitted.cache)
    except Exception:
        window._clear_native_review();raise
    window.log.setPlainText('VERIFIED ORIGINAL / FITTED MOTION COMPARISON\n'
        f'{fitted.cache.frame_count} full frames at {fitted.cache.fps:g} fps. Switch Original motion / Fitted motion in the viewer.\n'
        'The source frame, camera and playback clock are shared. Focus resets when switching.\n'
        'Fitting changes target motion; it does not change the source animation or character master.\n'
        'Only hand/opposite-arm surface crossings were checked. Grasp, visual and engine quality remain unapproved.')
