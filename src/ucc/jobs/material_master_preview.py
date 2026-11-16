"""Fresh source/hand/shader admission before a read-only complete PBR preview."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import math,time
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.core.storage import ProjectStore
from .master_preview import MasterPreview,preview_saved_master,_digest
from .skin_material_storage import registered_material_binding
from .skin_material_preparation import prepare_skin_material_revision,_BudgetCancel
from .godot_candidate_inputs import project_sources


def preview_material_master(store: ProjectStore,*,blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,
        expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None=None,timeout_s: float=900) -> MasterPreview:
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Material preview needs a bounded total deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Material preview cancelled or total deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();project=store.load()
    if (project.project_id!=expected_project_id or project.revision!=expected_revision or project.master_blend!=expected_master_blend):
        raise ProjectConflict('Saved character changed before material preview')
    binding=registered_material_binding(store,project,budget)
    if binding is None:raise ValidationError('Material preview requires a registered saved material')
    spec=SkinMaterialSpec.from_dict(binding['spec']);sources=project_sources(store,project,budget)
    from .expression_storage import safe_directory
    material_files={safe_directory(store,'materials','manifests')/(dict(project.appearance)[APPEARANCE_KEY]+'.json')}
    material_files.update(safe_directory(store,'materials','proofs')/(binding[k]+'.json') for k in ('recipe_sha256','stage_sha256','verification_sha256'))
    material_files.update(safe_directory(store,'master','versions')/(binding[k]+'.blend') for k in ('source_master_sha256','material_master_sha256','final_master_sha256'))
    hashes={p:_digest(p,budget) for p in {store.file,*sources.values(),*material_files}}
    def unchanged():
        remaining()
        if store.load()!=project or project_sources(store,project,budget)!=sources:raise ProjectConflict('Saved preview source closure changed')
        for p,h in hashes.items():
            if p.is_symlink() or not p.is_file() or _digest(p,budget)!=h:raise ProjectStorageError('Saved material preview authority changed')
        if registered_material_binding(store,project,budget)!=binding:raise ProjectStorageError('Saved preview material proof changed')
    expected=dict(expected_project_id=expected_project_id,expected_revision=expected_revision,expected_master_blend=expected_master_blend)
    prepared=prepare_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=worker_script,
        mpfb_data_dir=mpfb_data_dir,cancel=budget,timeout_s=remaining(),**expected)
    if prepared.source_master_sha256!=prepared.material_master_sha256 or prepared.source_master_sha256!=Path(project.master_blend).stem:
        raise ProjectStorageError('Material preview cannot repair or replace the saved owned shader')
    unchanged()
    result=preview_saved_master(store,blender_exe=blender_exe,worker_script=worker_script,
        cancel=budget,timeout_s=remaining(),full_surface=True,material_spec=spec,**expected)
    unchanged()
    return replace(result,watched_inputs=tuple(sorted((str(p),h) for p,h in hashes.items())))
