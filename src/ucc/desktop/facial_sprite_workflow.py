"""Normal animated-sprite menu/background route; immutable saved character."""
from pathlib import Path
from threading import Event
from PySide6.QtWidgets import QDialog
from ucc.core.errors import UCCError,ValidationError,ProjectConflict
from ucc.core.expression_clip import build_expression_clip
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.jobs.static_export_sources import static_export_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.facial_sprite_export import export_facial_sprites,FacialSpriteExport
from ucc.jobs.godot_candidate_inputs import regular_file,read_json
from ucc.jobs.master_preview import _digest
from .facial_sprite_dialog import FacialSpriteDialog


def refresh_facial_sprite(window):
    project=window.controller.require_project() if window.controller.has_project else None
    window.facial_sprite_action.setEnabled(not window.jobs.busy and project is not None and not window.controller.dirty
        and supports_material_master_intent(project) and project.expression is not None and any(v>0 for _,v in project.expression.parameters))


def run_facial_sprite_job(store,*,request,destination,blender_exe,cancel):
    from .generation import bundled_worker_path
    from ucc.jobs.face_discovery import discover_face_data
    worker=bundled_worker_path();data=discover_face_data(store,blender_exe=blender_exe,worker_script=worker,cancel=cancel)
    return export_facial_sprites(store,request=request,destination=destination,blender_exe=blender_exe,worker_script=worker,mpfb_data_dir=data,cancel=cancel)


def start_facial_sprite(window):
    try:
        if window.jobs.busy:raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:raise ValidationError('Open a saved prepared character first')
        if window.controller.dirty:raise ValidationError('Save character and expression settings before rendering')
        project=window.controller.require_project();store=window.controller.store
        review,_,_=static_export_sources(store,project_id=project.project_id,revision=project.revision,master_blend=project.master_blend,purpose='Animated sprite rendering')
        clip=build_expression_clip(project,Path(project.master_blend).stem)
        if not any(v>0 for v in clip['parameters'].values()):raise ValidationError('Save at least one nonzero expression strength before rendering animation')
        dialog=FacialSpriteDialog(review,clip,window)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        request=dialog.request();destination=plan_destination(Path(dialog.destination.text().strip()),store.root)
        from .hand_workflow import _executable
        blender=_executable(window)
        if blender is None:return
        if store.load()!=project or window.controller.require_project()!=project or window.controller.dirty:raise ProjectConflict('Saved facial sprite inputs changed during review')
        cancel=Event();window._clear_preview()
        window._submit('facial_sprite_export',lambda:run_facial_sprite_job(store,request=request,destination=destination,blender_exe=blender,cancel=cancel),cancel=cancel)
    except (UCCError,OSError,ValueError,TypeError) as error:window._error(str(error))


def finish_facial_sprite(window,result):
    try:
        if not isinstance(result,FacialSpriteExport):raise ValidationError('Unexpected animated sprite result')
        path=regular_file(result.destination/'facial_sprite_receipt.json',result.destination,4*1024*1024)
        if _digest(path)!=result.receipt_sha256:raise ValidationError('Animated sprite receipt changed after verification')
        receipt=read_json(path,4*1024*1024)
        for name,h in receipt['files'].items():
            if _digest(regular_file(result.destination/name,result.destination,16*1024*1024))!=h:raise ValidationError('Animated sprite output changed: '+name)
        window.log.setPlainText('Private animated facial sprites created:\n'+str(result.destination)+'\n'
            +str(result.frame_count)+' transparent frames; 25 frames per direction at 24 fps, in 5 × 5 sheets with sprite_atlas.json.\n'
            'Every frame matches independent original-source and saved-Action geometry, normals and rendered pixels.\n'
            'Editable character and history were not changed. Artist/pixel-art quality and public distribution remain unapproved.')
    except (UCCError,OSError,ValueError,KeyError) as error:window._error('Animated sprite output could not be confirmed: '+str(error))


def facial_sprite_error(window,error):
    if window.jobs.cancel_requested:
        window.log.setPlainText('Animated sprite rendering cancelled. No existing destination was replaced; private staging/logs are retained.');return
    window._error(error)
