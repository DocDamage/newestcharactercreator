"""Desktop hand library, provisional selection and atomic part/master adoption."""
import os
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog

from ucc.core.errors import UCCError,ValidationError
from ucc.core.hand_parts import ensure_source_intent,hand_selection,is_sha256
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.hand_library import HandLibraryBuild,build_hand_library
from ucc.jobs.hand_revision import HandRevisionResult,apply_hand_revision
from ucc.jobs.hand_storage import safe_directory,read_hand_manifest
from ucc.jobs.hand_preview import HandPreview,preview_hand


def refresh_hands(window):
    controls=window.character.hands
    project=window.controller.require_project();store=window.controller.store
    clean=not window.controller.dirty and project.master_blend is not None and not project.animations
    identity=None;current='neutral';message='Build compatible hands for this saved character.'
    candidates=[];invalid=0
    try:
        directory=safe_directory(store,'parts','manifests')
        for path in directory.glob('*.json'):
            if not is_sha256(path.stem):continue
            try:
                manifest,_=read_hand_manifest(store,path.stem)
                ensure_source_intent(project,manifest['recipe'])
                selected=hand_selection(project,path.stem)
                original=manifest['recipe']['bindings']['master_sha256']
                if selected=='neutral' and project.master_blend!='master/versions/'+original+'.blend':continue
                candidates.append((path.stat().st_mtime_ns,path.stem,selected))
            except (UCCError,OSError,ValueError):invalid+=1
        if candidates:
            _,identity,current=max(candidates)
            message='Compatible hand assets ready. Applying checks the saved result over 20 poses.'
        elif project.parts:
            message='This saved attachment has no compatible hand library. Restore a known character revision before rebuilding.'
        elif not clean:
            message='Save settings and generate a character before building compatible hands.'
        if invalid and not candidates:message+=' Some earlier hand libraries no longer match this character.'
    except (UCCError,OSError,ValueError) as error:
        message=str(error)
    controls.display_context(key=(str(store.root),project.project_id,project.revision,window.controller.dirty),
        identity=identity,current=current,can_build=clean and not project.parts,
        can_apply=clean and identity is not None,can_preview=clean,message=message)


def _executable(window):
    executable=window._blender_executable
    if executable is None or executable.is_symlink() or not executable.is_file():
        name,_=QFileDialog.getOpenFileName(window,'Choose installed Blender for compatible hands','',
                     'Blender executable (*.exe);;All files (*)' if os.name=='nt' else 'All files (*)')
        if not name:return None
        executable=Path(name)
        if executable.is_symlink() or not executable.is_file():raise ValidationError('Choose an existing installed Blender executable')
        window._blender_executable=executable
    return executable


def _run(store,snapshot,executable,cancel,identity=None,selection=None):
    from .generation import bundled_worker_path
    worker=bundled_worker_path()
    data=discover_face_data(store,blender_exe=executable,worker_script=worker,cancel=cancel)
    kwargs={'blender_exe':executable,'worker_script':worker,'mpfb_data_dir':data,
            'expected_project_id':snapshot.project_id,'expected_revision':snapshot.revision,
            'expected_master_blend':snapshot.master_blend,'cancel':cancel}
    if identity is None:return build_hand_library(store,**kwargs)
    return apply_hand_revision(store,manifest_sha256=identity,selection=selection,**kwargs)


def start_hands(window,*,build=False):
    def start():
        if window.jobs.busy:raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:raise ValidationError('Open a saved character first')
        if window.controller.dirty:raise ValidationError('Save all settings before building or applying hands')
        snapshot=window.controller.require_project()
        if snapshot.master_blend is None or snapshot.animations:raise ValidationError('Hand parts require a saved unanimated MPFB character')
        controls=window.character.hands
        if build and snapshot.parts:raise ValidationError('Restore the original hand before rebuilding compatible assets')
        identity=None if build else controls.manifest_sha256
        if not build and identity is None:raise ValidationError('Build compatible hand assets for this saved character first')
        executable=_executable(window)
        if executable is None:return
        store=window.controller.store;cancel=Event();selection=controls.choice.currentData()
        if not build:window._clear_preview()
        window._submit('hand_library' if build else 'hand_revision',
            lambda:_run(store,snapshot,executable,cancel,identity,selection),cancel=cancel)
    window._apply(start)


def finish_hands(window,result):
    if isinstance(result,HandPreview):
        previous_kind=window._work_kind
        try:
            window._work_kind='saved_master_preview';window._job_success(result.preview)
        finally:window._work_kind=previous_kind
        if window.mesh_viewer.gpu_canvas is not None:
            window.mesh_viewer.focus_bounds(result.bounds)
            window.log.append('\nFocused on the actual saved left hand. Drag to orbit; wheel to zoom. This is a complete static surface.')
        return True
    if isinstance(result,HandLibraryBuild):
        window.refresh_project()
        window.log.setPlainText('Two compatible hand assets built and independently reopened.\n40 real skin-pose checks passed. Choose a hand and Apply.\nThe saved character and its revision are unchanged.')
        return True
    if not isinstance(result,HandRevisionResult):return False
    try:
        window.controller.accept_saved_part_master(result.project,manifest_sha256=result.manifest_sha256)
        window._clear_preview();window.refresh_project()
    except (UCCError,OSError,ValueError) as error:
        window._error('Saved hand result could not be adopted; reopen the current saved project. '+str(error));return True
    action='Hand applied and independently reopened.' if result.revision else 'The saved hand already matches; no new revision.'
    if result.revision and result.observed['selection']=='neutral':action='Original hand and exact original master restored.'
    window.log.setPlainText(action+'\nBody and face settings retained. Undo/redo restores the hand and master together.\n'
        f"40 skin/shading pose checks passed; {result.observed['potential_overlap_poses']} poses have potential overlap observations.\n"
        'Use View saved character to review the actual geometry. Human visual quality and engine imports remain unapproved.')
    return True


def start_hand_preview(window):
    def start():
        if window.jobs.busy:raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:raise ValidationError('Open a saved character first')
        if window.controller.dirty:raise ValidationError('Save settings before viewing the saved hand')
        snapshot=window.controller.require_project()
        if snapshot.master_blend is None:raise ValidationError('Generate a character before viewing hands')
        executable=_executable(window)
        if executable is None:return
        store=window.controller.store;cancel=Event()
        def run():
            from .generation import bundled_worker_path
            worker=bundled_worker_path()
            data=discover_face_data(store,blender_exe=executable,worker_script=worker,cancel=cancel)
            return preview_hand(store,blender_exe=executable,worker_script=worker,mpfb_data_dir=data,
                expected_project_id=snapshot.project_id,expected_revision=snapshot.revision,
                expected_master_blend=snapshot.master_blend,cancel=cancel)
        window._clear_preview();window._submit('hand_preview',run,cancel=cancel)
    window._apply(start)


def show_hand_error(window,error):
    if window.jobs.cancel_requested:
        window._clear_preview();window.refresh_project()
        window.log.setPlainText('Hand operation cancelled. No new character result was adopted.')
        window.statusBar().showMessage('Hand operation cancelled');return
    if 'ProjectConflict' in error and window.controller.store is not None and not window.controller.dirty:
        try:
            window.controller.open(window.controller.store.root)
            window._clear_preview();window.refresh_project()
            window.log.setPlainText(error+'\nExternal saved changes were preserved and reloaded.')
            window.statusBar().showMessage('Project changed; current saved character reloaded');return
        except (UCCError,OSError,ValueError):pass
    window._error(error)
