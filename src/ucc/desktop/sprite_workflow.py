"""Normal desktop sprite route; no implicit source rights or metadata adoption."""
from pathlib import Path
from threading import Event
from PySide6.QtWidgets import QDialog
from ucc.core.errors import UCCError,ValidationError,ProjectConflict
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.jobs.static_export_sources import static_export_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.sprite_export import export_sprite_sample,SpriteExport
from ucc.jobs.godot_candidate_inputs import regular_file,read_json
from ucc.jobs.master_preview import _digest
from .sprite_dialog import SpriteRenderDialog


def refresh_sprite(window):
    window.sprite_export_action.setEnabled(not window.jobs.busy and window.controller.has_project and not window.controller.dirty
        and supports_material_master_intent(window.controller.require_project()))


def run_sprite_job(store,*,request,destination,blender_exe,cancel):
    from .generation import bundled_worker_path
    from ucc.jobs.face_discovery import discover_face_data
    worker=bundled_worker_path();data=discover_face_data(store,blender_exe=blender_exe,worker_script=worker,cancel=cancel)
    return export_sprite_sample(store,request=request,destination=destination,blender_exe=blender_exe,worker_script=worker,mpfb_data_dir=data,cancel=cancel)


def start_sprite(window):
    try:
        if window.jobs.busy:raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:raise ValidationError('Open a saved character first')
        if window.controller.dirty:raise ValidationError('Save character settings before rendering')
        project=window.controller.require_project();store=window.controller.store
        review,_,_=static_export_sources(store,project_id=project.project_id,revision=project.revision,master_blend=project.master_blend,purpose='Sprite rendering')
        dialog=SpriteRenderDialog(review,window)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        request=dialog.request();destination=plan_destination(Path(dialog.destination.text().strip()),store.root)
        from .hand_workflow import _executable
        blender=_executable(window)
        if blender is None:return
        if store.load()!=project or window.controller.require_project()!=project or window.controller.dirty:raise ProjectConflict('Saved character changed during sprite review')
        cancel=Event();window._clear_preview()
        window._submit('sprite_export',lambda:run_sprite_job(store,request=request,destination=destination,blender_exe=blender,cancel=cancel),cancel=cancel)
    except (UCCError,OSError,ValueError,TypeError) as error:window._error(str(error))


def finish_sprite(window,result):
    try:
        if not isinstance(result,SpriteExport):raise ValidationError('Unexpected sprite render result')
        receipt=regular_file(result.destination/'sprite_receipt.json',result.destination,4*1024*1024)
        if _digest(receipt)!=result.receipt_sha256:raise ValidationError('Sprite receipt changed after verification')
        record=read_json(receipt,4*1024*1024)
        for name,sha in record['files'].items():
            if _digest(regular_file(result.destination/name,result.destination,16*1024*1024))!=sha:raise ValidationError('Sprite output changed after verification: '+name)
        window.log.setPlainText('Private character sprite sample created:\n'+str(result.destination)+'\n'
            +str(result.frame_count)+' transparent neutral-pose directions and sprite_sheet_000.png with sprite_atlas.json.\n'
            'Fresh Blender source and saved-scene re-renders passed; atlas pixels match the rendered frames.\n'
            'Editable character and history were not changed. No animation clips are included. Artist/pixel-art quality and public distribution remain unapproved.')
    except (UCCError,OSError,ValueError,KeyError) as error:window._error('Sprite output could not be confirmed: '+str(error))


def sprite_error(window,error):
    if window.jobs.cancel_requested:
        window.log.setPlainText('Sprite rendering cancelled. No existing destination was replaced; private staging/logs are retained.');return
    window._error(error)
