"""Desktop native-body workflow; local reviewed inputs and private outputs only."""
from pathlib import Path
from threading import Event
import os
import subprocess

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ucc.core.errors import UCCError, ValidationError
from ucc.library.provenance import LicensePolicy
from ucc.jobs.native_body import preview_native_body
from ucc.jobs.native_evidence import bound_file
from .generation import bundled_worker_path


def start_native_body(window):
    if window.jobs.busy:
        window._error("Another local task is still running");return
    if window.controller.store is None or not window.controller.has_project:
        window._error("Open a saved character project first");return
    snapshot=window.controller.require_project()
    if window.controller.dirty or snapshot.master_blend is None:
        window._error("Save the character and generate its Blender master before testing FBX motion");return
    pane=window.animations
    source=Path(pane.selected.text())
    if not source.is_file() or source.is_symlink() or source.suffix.lower()!=".fbx":
        window._error("Choose a regular local FBX animation file");return
    if (not pane.local_preview_review.isChecked() or not pane.provider.text().strip() or not pane.uri.text().strip() or
            pane.license.text().strip().casefold() in {"","unknown","unreviewed","n/a"}):
        window._error("Enter the animation's source/license and confirm local Blender preview rights");return
    executable=window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        selected,_=QFileDialog.getOpenFileName(window,"Choose installed Blender for private FBX preview","",
            "Blender executable (*.exe);;All files (*)" if os.name=="nt" else "All files (*)")
        if not selected:return
        executable=Path(selected)
        if executable.is_symlink() or not executable.is_file():window._error("Choose a regular Blender executable");return
        window._blender_executable=executable
    try:
        policy=LicensePolicy(pane.provider.text().strip(),pane.license.text().strip(),pane.uri.text().strip(),
                             reviewed=True,local_preview_allowed=True,no_ai=True)
        worker=bundled_worker_path()
    except (UCCError,ValueError) as error:
        window._error(str(error));return
    profile=Path(pane.native_body_profile.text()) if pane.native_body_profile.text().strip() else None
    store=window.controller.store
    cancel=Event()
    window._native_review=None
    pane.open_native_animation.setEnabled(False);pane.open_native_renders.setEnabled(False)
    window._submit("native_body",lambda:preview_native_body(store,source_fbx=source,mapping_profile=profile,
        blender_exe=executable,worker_script=worker,permission=policy,expected_project_id=snapshot.project_id,
        expected_revision=snapshot.revision,expected_master_blend=snapshot.master_blend,cancel=cancel),cancel=cancel)


def native_result_text(result):
    data=result.evidence
    anchor=(f"Hip movement matches the measured source through every frame; maximum error {data['hip_anchor']['max_residual_world']*1000:.4f} mm.\n"
            if data.get("root_motion_policy")=="SOURCE_HIP_MIDPOINT_V1" else "")
    return ("EXPERIMENTAL FBX MOTION MEASURED ON A PRIVATE CHARACTER COPY\n"
        f"Complete source timeline: {data['source_frame_count']} frames at {data['fps']:g} fps\n"
        f"Mapped body joints: {len(data['mapped_pairs'])}; unmapped source bones: {len(data['omitted_source_bones'])}\n"
        "Unmapped finger, face or other source motion was not applied.\n"
        f"Root travel from bind: {data['root_motion_metrics']['max_distance_from_bind_world']:.3f} m\n"
        f"{anchor}"
        "Two independent Blender workers agree on all measured target poses and skin frames.\n"
        "Original animation, saved character and project are unchanged.\n"
        "Use Open private animation to scrub/play in Blender, or Open sampled views for five-frame comparisons.\n"
        "In-UCC animated playback, visual acceptance, foot-contact quality and engine import remain unverified.")


def open_native_result(window, *, rendered=False):
    result=getattr(window,"_native_review",None)
    if result is None or result.worker_report is None:
        window._error("Complete a private FBX body preview first");return
    try:
        folder=Path(result.private_visual_review_blend).parent
        if rendered:
            record=result.worker_report["private_review_renders"]["index"]
            path=bound_file(folder/"review_frames",record,"index.html",64*1024)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):raise ValidationError("The local review index could not be opened")
        else:
            path=bound_file(folder,result.worker_report["visual_review_blend"],"review_motion.blend",512*1024*1024)
            executable=window._blender_executable
            if executable is None or executable.is_symlink() or not executable.is_file():raise ValidationError("Select Blender and run the preview again")
            subprocess.Popen([str(executable),"--disable-autoexec",str(path)],shell=False)
    except (UCCError,OSError,KeyError,ValueError) as error:
        window._error("Private animation review failed: "+str(error))
