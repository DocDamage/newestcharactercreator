"""Existing desktop actions for independently verified material-bound edits."""
from pathlib import Path
from threading import Event
from ucc.core.errors import UCCError,ValidationError
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.core.storage import ProjectStore
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.skin_material_revision import revise_material_bound_master,SkinMaterialRevision,MaterialMasterNoOp
from ucc.jobs.skin_material_storage import registered_material_binding


def run_material_master(store: ProjectStore,*,operation: str,blender_exe: Path,project_id: str,revision: int,
        master_blend: str | None,cancel: Event) -> SkinMaterialRevision | MaterialMasterNoOp:
    snapshot=store.load()
    if (not supports_material_master_intent(snapshot) or snapshot.project_id!=project_id
            or snapshot.revision!=revision or snapshot.master_blend!=master_blend):
        raise ValidationError('Material-aware editing requires the exact saved prepared character')
    from .generation import bundled_worker_path
    script=bundled_worker_path()
    data=discover_face_data(store,blender_exe=blender_exe,worker_script=script,cancel=cancel)
    return revise_material_bound_master(store,operation=operation,blender_exe=blender_exe,worker_script=script,
        mpfb_data_dir=data,expected_project_id=project_id,expected_revision=revision,expected_master_blend=master_blend,
        cancel=cancel,timeout_s=1800)


def finish_material_master(window,result: SkinMaterialRevision | MaterialMasterNoOp) -> None:
    saved=result.project if isinstance(result,MaterialMasterNoOp) else result.revision.project
    try:
        if window.controller.store is None:raise ValidationError('Character closed while material-aware work was running')
        registered_material_binding(window.controller.store,saved)
        window.controller.accept_saved_material_master(saved)
        window._clear_preview();window.refresh_project()
    except (UCCError,OSError,ValueError) as error:
        window._error('Saved material-aware character could not be adopted: '+str(error));return
    action=('Saved settings already match; no new master revision.' if isinstance(result,MaterialMasterNoOp)
        else 'Saved character changes applied and independently reopened.')
    window.log.setPlainText(action+'\nChosen material, facial strengths and hand selection retained.\n'
        'Undo/redo restores the master, appearance and rebuilt hand together.\n'
        'Use View saved character to inspect the result. Visual quality and engine imports remain unapproved.')


def show_material_master_error(window,error: str) -> None:
    window._clear_preview()
    if window.jobs.cancel_requested:
        window.refresh_project()
        window.log.setPlainText('Character operation cancelled. No new result was adopted. Your saved character remains unchanged.')
        return
    window._error(error)
