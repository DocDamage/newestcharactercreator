"""Explicit material selection, proof-aware first assignment and saved history."""
from threading import Event
from pathlib import Path
from ucc.core.storage import ProjectStore
from ucc.core.errors import UCCError,ValidationError,CompatibilityError
from ucc.core.material_master_intent import supports_skin_material_input
from ucc.core.skin_material import SkinMaterialSpec
from ucc.jobs.skin_material_storage import material_binding_metadata,registered_material_binding
from ucc.jobs.skin_material_revision import apply_skin_material_revision,SkinMaterialRevision,MaterialMasterNoOp
from ucc.jobs.face_discovery import discover_face_data


def refresh_skin_material(window):
    project=window.controller.require_project();store=window.controller.store
    try:
        if supports_skin_material_input(project) and project.parts:
            from ucc.jobs.hand_storage import read_hand_manifest
            from ucc.core.hand_parts import ensure_source_intent
            manifest,_=read_hand_manifest(store,project.parts[0].part_asset_id.split('-')[3])
            ensure_source_intent(project,manifest['recipe'])
        binding=material_binding_metadata(store,project)
        spec=None if binding is None else SkinMaterialSpec.from_dict(binding['spec'])
        window.character.material.display(project.project_id,spec,eligible=supports_skin_material_input(project),clean=not window.controller.dirty)
    except CompatibilityError:
        window.character.material.display(project.project_id,None,eligible=False,clean=False,
            error='Apply saved body and face changes before assigning a skin material.')
    except (UCCError,OSError,ValueError):
        window.character.material.display(project.project_id,None,eligible=False,clean=False,
            error='Saved skin material is unavailable. Restore its project files before editing.')


def apply_skin_from_desktop(store: ProjectStore,*,spec: SkinMaterialSpec,blender_exe: Path,project_id: str,revision: int,master_blend: str,
        cancel: Event) -> SkinMaterialRevision | MaterialMasterNoOp:
    current=store.load()
    if (not isinstance(spec,SkinMaterialSpec) or not supports_skin_material_input(current) or current.project_id!=project_id
            or current.revision!=revision or current.master_blend!=master_blend):
        raise ValidationError('Skin material requires the exact saved prepared character and explicit color')
    from .generation import bundled_worker_path
    script=bundled_worker_path();data=discover_face_data(store,blender_exe=blender_exe,worker_script=script,cancel=cancel)
    return apply_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=script,mpfb_data_dir=data,
        expected_project_id=project_id,expected_revision=revision,expected_master_blend=master_blend,cancel=cancel,timeout_s=1800)


def start_skin_material(window,spec: SkinMaterialSpec):
    if window.jobs.busy:window._error('Another local task is still running');return
    if not window.controller.has_project or window.controller.store is None:window._error('Open a saved character first');return
    project=window.controller.require_project()
    if window.controller.dirty:window._error('Save other character settings before applying skin color');return
    if not supports_skin_material_input(project) or not isinstance(spec,SkinMaterialSpec):window._error('Prepare a compatible saved character and choose a color first');return
    from .hand_workflow import _executable
    try:executable=_executable(window)
    except (UCCError,OSError,ValueError) as error:window._error(str(error));return
    if executable is None:return
    window._blender_executable=executable;store=window.controller.store;cancel=Event();window._clear_preview()
    window._submit('skin_material',lambda:apply_skin_from_desktop(store,spec=spec,blender_exe=executable,
        project_id=project.project_id,revision=project.revision,master_blend=project.master_blend,cancel=cancel),cancel=cancel)


def finish_skin_material(window,result):
    saved=result.project if isinstance(result,MaterialMasterNoOp) else result.revision.project
    try:
        if window.controller.store is None:raise ValidationError('Character closed while material work was running')
        registered_material_binding(window.controller.store,saved)
        window.controller.accept_saved_skin_material(saved);window._clear_preview();window.refresh_project()
    except (UCCError,OSError,ValueError) as error:window._error('Saved skin material could not be adopted: '+str(error));return
    action=('Saved material independently verified; no new revision.' if isinstance(result,MaterialMasterNoOp)
        else 'Skin color and roughness saved and independently reopened.')
    window.log.setPlainText(action+'\nBody shape, hand selection and facial strengths retained. Undo/redo restores the whole material revision.\n'
        'Use View → Preview current saved Blender master to inspect the saved material. Visual quality remains unapproved.')
