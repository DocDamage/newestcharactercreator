"""Private rig/morph/material export with fresh Blender/Godot and new-folder commit."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math,os,shutil,time
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.storage import ProjectStore,_lock
from ucc.export.static_godot_contract import StaticGodotRequest,POLICY
from ucc.export.static_morph_reference import write_morph_reference
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_skin_plan import build_skin_plan
from ucc.export.skin_material_evidence import verify_material_glb
from .static_export_sources import static_export_sources
from .export_destination import ExportDestination,rename_new
from .skin_material_preparation import prepare_skin_material_revision,_BudgetCancel
from .expression_storage import safe_directory
from .godot_candidate_inputs import regular_file,identity,read_json
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .static_godot_engine import scripts,run_engine,reopen_copy,PAYLOAD,OUTPUTS


@dataclass(frozen=True,slots=True)
class StaticGodotExport:
    destination: Path
    request_sha256: str
    receipt_sha256: str
    master_sha256: str
    observed: dict
    workdir: Path


def export_static_godot(store: ProjectStore,*,request: StaticGodotRequest,destination: ExportDestination,
        blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,godot_exe: Path,
        cancel: Event | None=None,timeout_s: float=1800) -> StaticGodotExport:
    if not isinstance(request,StaticGodotRequest) or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Static export needs an explicit reviewed request and bounded total deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Godot export cancelled or total deadline exceeded; no existing destination replaced')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load();destination.unchanged()
    review,sources,binding=static_export_sources(store,project_id=request.project_id,revision=request.revision,master_blend=initial.master_blend,cancel=budget)
    if review.project_sha256!=request.project_sha256 or dict(request.source_bindings)!={s.asset_id:s.sha256 for s in review.sources}:
        raise ProjectConflict('Godot export review is stale; review the exact saved inputs again')
    installed=scripts();executable=regular_file(Path(godot_exe),Path(godot_exe).parent,512*1024*1024)
    protected={store.file,*sources.values(),*installed.values(),executable,Path(blender_exe).resolve(),*worker_dependency_files(Path(worker_script))}
    protected.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    protected.update(safe_directory(store,'materials','proofs')/(binding[k]+'.json') for k in ('recipe_sha256','stage_sha256','verification_sha256'))
    protected.update(safe_directory(store,'master','versions')/(binding[k]+'.blend') for k in ('source_master_sha256','material_master_sha256','final_master_sha256'))
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def guard():
        remaining()
        if store.load()!=initial:raise ProjectConflict('Saved character changed during Godot export')
        for p,h in hashes.items():
            if p.is_symlink() or not p.is_file() or identity(p)!=identities[p] or _digest(p,budget)!=h:
                raise ProjectStorageError('Godot export source, proof, executable or adapter changed')
        current,_,_=static_export_sources(store,project_id=request.project_id,revision=request.revision,master_blend=initial.master_blend,cancel=budget)
        if current!=review:raise ProjectConflict('Godot export source review changed')
    jobs=safe_directory(store,'.ucc-jobs',create=True);work=jobs/('static-export-'+request.job_id);work.mkdir(exist_ok=False)
    commands=[];stage=None;published=False
    def journal(state: str,**extra):
        path=work/'job_status.json'
        if path.is_symlink():raise ProjectStorageError('Export journal redirected')
        temporary=work/'job_status.tmp'
        if temporary.exists() or temporary.is_symlink():raise ProjectStorageError('Export journal temporary path already exists')
        with temporary.open('xb') as stream:
            stream.write(canonical_bytes({'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'state':state,
                'destination':str(destination.path),'commands':commands,**extra}));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    try:
        journal('BLENDER_SOURCE_AND_MATERIAL_VERIFICATION')
        spec=SkinMaterialSpec.from_dict(binding['spec'])
        prepared=prepare_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=worker_script,mpfb_data_dir=mpfb_data_dir,
            expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend,cancel=budget,timeout_s=remaining())
        if (prepared.source_master_sha256!=prepared.material_master_sha256 or prepared.material_master_sha256!=Path(initial.master_blend).stem
                or read_json(prepared.directory/'material_stage.json',4*1024*1024).get('changed') is not False):
            raise ProjectStorageError('Export cannot repair or replace the saved character/material')
        guard();engine=work/'engine-build';engine.mkdir()
        shutil.copy2(prepared.directory/'character.glb',engine/'character.glb');verify_material_glb(engine/'character.glb',spec)
        plan=build_skin_plan(engine/'character.glb');(engine/'skin_plan.json').write_bytes(canonical_bytes(plan.to_dict()))
        write_morph_reference(engine/'character.glb',engine)
        for name,path in installed.items():shutil.copy2(path,engine/name)
        (engine/'project.godot').write_text('config_version=5\n[application]\nconfig/name="UCC private character export"\nrun/main_scene="res://character_preview.tscn"\n[rendering]\nrenderer/rendering_method="mobile"\n',encoding='utf-8')
        engine_files={p.name:_digest(p,budget) for p in engine.iterdir() if p.is_file()}
        engine_request={'schema_version':1,'policy':POLICY,'export_request':request.to_dict(),'material_spec':spec.to_dict(),'files':engine_files}
        (engine/'request.json').write_bytes(canonical_bytes(engine_request));engine_request_sha=_digest(engine/'request.json',budget)
        journal('GODOT_BUILD')
        built=run_engine(engine,work/'build-logs',executable,engine_request_sha,mode='build',remaining=remaining,cancel=budget,guard=guard,commands=commands)
        reopened=work/'engine-reopen';reopen_copy(engine,reopened);journal('GODOT_SAVED_SCENE_REOPEN')
        observed=run_engine(reopened,work/'reopen-logs',executable,engine_request_sha,mode='verify',remaining=remaining,cancel=budget,guard=guard,commands=commands)
        if (observed['saved_scene_sha256']!=built['saved_scene_sha256'] or observed['preview_scene_sha256']!=built['preview_scene_sha256']):
            raise ProjectStorageError('Godot saved scene changed between separate processes')
        guard();destination.unchanged();stage=destination.stage(request.job_id);journal('DESTINATION_STAGING',stage=str(stage))
        for name in (*PAYLOAD,*OUTPUTS):shutil.copy2(regular_file(reopened/name,reopened,128*1024*1024),stage/name)
        (stage/'README.txt').write_text('Private Godot character export\n\nOpen project.godot to inspect character_preview.tscn.\nUse character.tscn in your game; its skin encoding was verified.\ncharacter.glb is the intermediate reference asset.\n163 bones, 12 facial shapes, original UVs, saved color and roughness.\nNo animation clips or body-animation corrective runtime.\nAnimation quality and public distribution rights need separate review.\nRetain NoAI and original-source restrictions in request.json.\nNo original Blender or purchased animation source is included.\n',encoding='utf-8')
        files={p.name:_digest(p,budget) for p in stage.iterdir() if p.is_file()}
        receipt={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'engine_request_sha256':engine_request_sha,
            'master_sha256':prepared.source_master_sha256,'files':files,'godot_executable_sha256':hashes[executable],
            'blender_stage_job_id':prepared.stage_job_id,'blender_reopen_job_id':prepared.reopen_job_id,
            'engine_observation':observed,'commands':commands,'private_godot_import_verified':True,
            'project_metadata_changed':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
        (stage/'export_receipt.json').write_bytes(canonical_bytes(receipt));receipt_sha=_digest(stage/'export_receipt.json',budget)
        stage_hashes={p.name:_digest(p,budget) for p in stage.iterdir()};stage_identity=identity(stage)
        with _lock(store.root/'.project.ucc.lock',timeout_s=min(3.,remaining())):
            guard();destination.unchanged()
            if identity(stage)!=stage_identity or {p.name for p in stage.iterdir()}!=set(stage_hashes) or any(p.is_symlink() or not p.is_file() or _digest(p,budget)!=stage_hashes.get(p.name) for p in stage.iterdir()):
                raise ProjectStorageError('Export staging changed before publication')
            remaining();rename_new(stage,destination.path);published=True
        guard();journal('PRIVATE_GODOT_EXPORT_PUBLISHED',receipt_sha256=receipt_sha);remaining()
        return StaticGodotExport(destination.path,request.sha256,receipt_sha,prepared.source_master_sha256,observed,work)
    except BaseException as error:
        if (published and stage is not None and not stage.exists() and destination.path.is_dir() and not destination.path.is_symlink()
                and destination.path.parent.resolve()==destination.path.parent and identity(destination.path.parent)==destination.parent_identity
                and identity(destination.path)==stage_identity):
            try:rename_new(destination.path,stage)
            except OSError as rollback:error.add_note('Export rollback failed; retained output: '+str(destination.path)+': '+str(rollback))
        try:journal('FAILED',error_type=type(error).__name__,error=str(error)[:1500],retained_stage=None if stage is None else str(stage))
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Export journal failure: '+str(journal_error))
        raise
