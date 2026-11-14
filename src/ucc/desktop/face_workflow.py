"""Desktop initiation/publication for independently verified facial revisions."""
import os
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog

from ucc.core.errors import UCCError, ValidationError
from ucc.jobs.face_revision import FaceRevisionResult, apply_saved_face_revision
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.customized_humanoid import CustomizedHumanoidBuild


def edit_face(window, name, value):
    def edit():
        previous = window.controller.require_project()
        window.controller.set_face_parameter(name, value)
        if previous != window.controller.require_project():
            window._clear_preview()
    window._apply(edit)


def apply_face_from_desktop(store, *, blender_exe, project_id, revision, master_blend, cancel):
    from .generation import bundled_worker_path
    script = bundled_worker_path()
    data = discover_face_data(store, blender_exe=blender_exe, worker_script=script, cancel=cancel)
    return apply_saved_face_revision(
        store, blender_exe=blender_exe, worker_script=script, mpfb_data_dir=data,
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel)


def start_face(window):
    if window.jobs.busy:
        window._error('Another local task is still running'); return
    if not window.controller.has_project or window.controller.store is None:
        window._error('Open a character project before applying face shape'); return
    if window.controller.dirty:
        window._error('Save face and body settings before applying face shape'); return
    snapshot = window.controller.require_project()
    if not snapshot.master_blend or not snapshot.facial_parameters:
        window._error('Save a face setting and generate an MPFB master first'); return
    if snapshot.parts or snapshot.animations:
        window._error('Face shape with attached parts or animations is not validated'); return
    executable = window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        selected, _ = QFileDialog.getOpenFileName(
            window, 'Choose installed Blender for face shape', '',
            'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
        if not selected:
            return
        executable = Path(selected)
        if executable.is_symlink() or not executable.is_file():
            window._error('Choose an existing installed Blender executable'); return
        window._blender_executable = executable
    store = window.controller.store
    cancel = Event()
    window._clear_preview()
    window._submit('face_revision', lambda: apply_face_from_desktop(
        store, blender_exe=executable, project_id=snapshot.project_id, revision=snapshot.revision,
        master_blend=snapshot.master_blend, cancel=cancel), cancel=cancel)


def finish_face_build(window, result) -> bool:
    if not isinstance(result, (FaceRevisionResult, CustomizedHumanoidBuild)):
        return False
    saved = result.project if isinstance(result, FaceRevisionResult) else result.revision.project
    try:
        window.controller.accept_saved_master(saved)
        window._clear_preview()
        window.refresh_project()
    except (UCCError, OSError, ValueError) as exc:
        window._error('Saved master could not be adopted into this session: '+str(exc))
        return True
    if isinstance(result, FaceRevisionResult):
        action = 'Face shape applied and independently reopened.' if result.revision else 'Saved face shape already matches; no new master revision.'
        details = f'Nose width: {dict(saved.facial_parameters)["nose_width"]:.3f}'
    else:
        action = 'Body and face built, independently reopened, and saved in one master revision.'
        details = 'Saved body and facial settings retained.'
    window.log.setPlainText(f'{action}\n{details}\nSaved revision: {saved.revision}\n'
                            f'Master: {saved.master_blend}\n'
                            'Previous masters remain available through undo/redo. Geometry remains generated_unverified; visual quality and engine imports are unapproved.')
    return True
