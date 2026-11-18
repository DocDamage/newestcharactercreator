"""Normal desktop route; no silent rights grant, source mutation or executable scan."""
from pathlib import Path
from threading import Event
from PySide6.QtWidgets import QFileDialog,QDialog
from ucc.core.errors import UCCError,ValidationError,ProjectConflict
from ucc.core.material_master_intent import supports_material_master_intent
from ucc.export.static_godot_contract import POLICY
from ucc.jobs.static_export_sources import static_export_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.static_godot_export import export_static_godot,StaticGodotExport
from ucc.jobs.master_preview import _digest
from ucc.jobs.godot_candidate_inputs import read_json,regular_file
from .export_compatibility_report import ExportProfile, show_export_compatibility
from .godot_export_dialog import GodotExportDialog


def refresh_export(window):
    window.godot_export_action.setEnabled(not window.jobs.busy and window.controller.has_project and not window.controller.dirty
        and supports_material_master_intent(window.controller.require_project()))


def run_desktop_export(store,*,request,destination,blender_exe,godot_exe,cancel):
    from .generation import bundled_worker_path
    from ucc.jobs.face_discovery import discover_face_data
    worker=bundled_worker_path();data=discover_face_data(store,blender_exe=blender_exe,worker_script=worker,cancel=cancel)
    return export_static_godot(store,request=request,destination=destination,blender_exe=blender_exe,worker_script=worker,
        mpfb_data_dir=data,godot_exe=godot_exe,cancel=cancel)


def start_export(window):
    try:
        if window.jobs.busy:raise ValidationError('Another local task is still running')
        if not window.controller.has_project or window.controller.store is None:raise ValidationError('Open a saved character first')
        if window.controller.dirty:raise ValidationError('Save character settings before exporting')
        project=window.controller.require_project();store=window.controller.store
        review,_,_=static_export_sources(store,project_id=project.project_id,revision=project.revision,master_blend=project.master_blend)
        dialog=GodotExportDialog(review,window)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        request=dialog.request();destination=plan_destination(Path(dialog.destination.text().strip()),store.root)
        from .hand_workflow import _executable
        blender=_executable(window)
        if blender is None:return
        godot=getattr(window,'_godot_executable',None)
        if godot is None or godot.is_symlink() or not godot.is_file():
            selected,_=QFileDialog.getOpenFileName(window,'Choose installed Godot 4.7 executable','','Executable (*.exe);;All files (*)')
            if not selected:return
            godot=Path(selected)
            if godot.is_symlink() or not godot.is_file():raise ValidationError('Choose a real installed Godot executable')
            window._godot_executable=godot
        if store.load()!=project or window.controller.require_project()!=project or window.controller.dirty:raise ProjectConflict('Saved character changed during export review')
        cancel=Event();window._clear_preview()
        window._submit('godot_export',lambda:run_desktop_export(store,request=request,destination=destination,
            blender_exe=blender,godot_exe=godot,cancel=cancel),cancel=cancel)
    except (UCCError,OSError,ValueError,TypeError) as error:window._error(str(error))


def finish_export(window,result):
    try:
        if not isinstance(result,StaticGodotExport):raise ValidationError('Unexpected Godot export result')
        receipt=regular_file(result.destination/'export_receipt.json',result.destination,4*1024*1024)
        record=read_json(receipt,4*1024*1024,expected_sha256=result.receipt_sha256)
        if (type(record.get('schema_version')) is not int or record['schema_version']!=1
                or record.get('policy')!=POLICY or record.get('request_sha256')!=result.request_sha256
                or record.get('master_sha256')!=result.master_sha256
                or record.get('private_godot_import_verified') is not True
                or record.get('visual_quality_approved') is not False
                or record.get('distribution_license_review_complete') is not False
                or type(record.get('engine_observation')) is not dict
                or record['engine_observation']!=result.observed
                or type(record.get('files')) is not dict or not record['files']):
            raise ValidationError('Godot receipt differs from this verified static export')
        for name,sha in record['files'].items():
            path=regular_file(result.destination/name,result.destination,128*1024*1024)
            if _digest(path)!=sha:raise ValidationError('Export output changed after verification: '+name)
        window.log.setPlainText('Private Godot character package created:\n'+str(result.destination)+'\n'
            'Fresh Blender and Godot checks passed for the rig, facial shapes, UVs, saved skin material and reopened scene.\n'
            'Open project.godot for the preview, or use character.tscn in your Godot project.\n'
            'No animation clips are included. Editable character and history were not changed. Visual quality and public distribution remain unapproved.')
        show_export_compatibility(window, ExportProfile.GODOT, result.destination)
    except (UCCError,OSError,ValueError,KeyError) as error:window._error('Godot output could not be confirmed: '+str(error))


def export_error(window,error):
    if window.jobs.cancel_requested:
        window.log.setPlainText('Godot export cancelled. No existing destination was replaced; private staging/logs are retained.');return
    window._error(error)
