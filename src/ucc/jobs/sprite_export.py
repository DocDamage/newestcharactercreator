"""Fresh source/render/reopen, exact atlas, and exclusive new-folder publication."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math,os,shutil,time
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore,_lock
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.sprite_render import POLICY,STAGE,VERIFY,SpriteRenderRequest,canonical
from ucc.sprites.plan import CameraProfile,build_plan
from ucc.sprites.atlas import pack_frames
from ucc.sprites.render_evidence import checked_sprite_evidence,checked_atlas
from .static_export_sources import static_export_sources
from .skin_material_preparation import prepare_skin_material_revision,_BudgetCancel
from .expression_storage import safe_directory
from .export_destination import ExportDestination,rename_new
from .godot_candidate_inputs import identity,regular_file,read_json
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .runner import BlenderJobRunner
from .protocol import JobRequest


@dataclass(frozen=True,slots=True)
class SpriteExport:
    destination: Path
    receipt_sha256: str
    frame_count: int
    workdir: Path
    stage_job_id: str
    reopen_job_id: str


def export_sprite_sample(store: ProjectStore,*,request: SpriteRenderRequest,destination: ExportDestination,
        blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,cancel: Event | None=None,timeout_s: float=1800) -> SpriteExport:
    if not isinstance(request,SpriteRenderRequest) or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Sprite export needs an explicit reviewed request and bounded total deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Sprite export cancelled or total deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load();destination.unchanged()
    review,sources,binding=static_export_sources(store,project_id=request.project_id,revision=request.revision,master_blend=initial.master_blend,cancel=budget,purpose='Sprite rendering')
    if review.project_sha256!=request.project_sha256 or dict(request.source_bindings)!={s.asset_id:s.sha256 for s in review.sources}:
        raise ProjectConflict('Sprite source review is stale; review the exact saved inputs again')
    worker_files=worker_dependency_files(Path(worker_script))
    protected={store.file,*sources.values(),Path(blender_exe).resolve(),*worker_files}
    protected.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    protected.update(safe_directory(store,'materials','proofs')/(binding[k]+'.json') for k in ('recipe_sha256','stage_sha256','verification_sha256'))
    protected.update(safe_directory(store,'master','versions')/(binding[k]+'.blend') for k in ('source_master_sha256','material_master_sha256','final_master_sha256'))
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def guard():
        remaining()
        if worker_dependency_files(Path(worker_script))!=worker_files:raise ProjectStorageError('Sprite worker resource set changed')
        if store.load()!=initial:raise ProjectConflict('Saved character changed during sprite rendering')
        for p,h in hashes.items():
            if p.is_symlink() or not p.is_file() or identity(p)!=identities[p] or _digest(p,budget)!=h:raise ProjectStorageError('Sprite source, proof or adapter changed')
        current,_,_=static_export_sources(store,project_id=request.project_id,revision=request.revision,master_blend=initial.master_blend,cancel=budget,purpose='Sprite rendering')
        if current!=review:raise ProjectConflict('Sprite review changed')
    work=safe_directory(store,'.ucc-jobs',create=True)/('sprite-export-'+request.job_id);work.mkdir(exist_ok=False)
    stage=None;published=False
    def journal(state: str,**extra):
        target=work/'job_status.json';temporary=work/'job_status.tmp'
        if target.is_symlink() or temporary.exists() or temporary.is_symlink():raise ProjectStorageError('Sprite journal changed or redirected')
        with temporary.open('xb') as f:
            f.write(canonical({'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'state':state,'destination':str(destination.path),**extra}));f.flush();os.fsync(f.fileno())
        os.replace(temporary,target)
    try:
        journal('SOURCE_AND_MATERIAL_VERIFICATION');spec=SkinMaterialSpec.from_dict(binding['spec'])
        prepared=prepare_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=worker_script,mpfb_data_dir=mpfb_data_dir,
            expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend,cancel=budget,timeout_s=remaining())
        if prepared.material_master_sha256!=prepared.source_master_sha256 or prepared.source_master_sha256!=Path(initial.master_blend).stem or read_json(prepared.directory/'material_stage.json',4*1024*1024).get('changed') is not False:
            raise ProjectStorageError('Sprite export cannot repair or replace the saved material/master')
        guard();recipe=work/'sprite_recipe.json';recipe.write_bytes(canonical({'schema_version':1,'policy':POLICY,'request':request.to_dict(),'material_spec':spec.to_dict()}))
        options={'master_sha256':prepared.source_master_sha256,'recipe_sha256':_digest(recipe,budget)}
        runner=BlenderJobRunner(Path(blender_exe),safe_directory(store,'.ucc-jobs'),Path(worker_script));journal('BLENDER_RENDER')
        result,rendered=runner.run(JobRequest.new(STAGE,input_project='candidate.blend',options=options),staged_inputs={'candidate.blend':store.root/initial.master_blend,'sprite_recipe.json':recipe},timeout_s=remaining(),cancel=budget)
        guard();options.update({k:result.details[k] for k in ('scene_sha256','stage_sha256')})
        if result.details!={'policy':POLICY,**{k:options[k] for k in ('scene_sha256','stage_sha256')}}:raise ValidationError('Incomplete sprite render stage')
        names=['candidate.blend','sprite_recipe.json','sprite_scene.blend','sprite_stage.json',*[f'sprite-{i:02d}.png' for i in range(request.settings.directions)]]
        inputs={name:regular_file(rendered/name,rendered,128*1024*1024) for name in names};input_hashes={n:_digest(p,budget) for n,p in inputs.items()}
        if input_hashes['sprite_scene.blend']!=options['scene_sha256'] or input_hashes['sprite_stage.json']!=options['stage_sha256']:raise ValidationError('Sprite outputs changed before reopening')
        journal('BLENDER_SAVED_SCENE_RERENDER')
        verified,reopened=runner.run(JobRequest.new(VERIFY,input_project='candidate.blend',options=options),staged_inputs=inputs,timeout_s=remaining(),cancel=budget)
        guard();report,proof=checked_sprite_evidence(reopened,request,options)
        if verified.details!=proof:raise ValidationError('Sprite verifier reply differs from its bound proof')
        if any(_digest(inputs[n],budget)!=h or _digest(reopened/n,budget)!=h for n,h in input_hashes.items()):raise ProjectStorageError('Sprite staged inputs changed during verification')
        frame_root=work/'atlas-inputs';atlas=work/'atlas'
        for i in range(request.settings.directions):
            path=frame_root/f'neutral/dir-{i:02d}/frame-0000.png';path.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(reopened/f'sprite-{i:02d}.png',path)
        settings=request.settings;camera=CameraProfile(yaw_deg=settings.yaw_deg,pitch_deg=settings.pitch_deg,orthographic_scale=next(v['camera']['ortho_scale'] for v in report['configuration']['objects'].values() if 'camera' in v),directions=settings.directions)
        plan=build_plan({'neutral':1},camera,width=settings.resolution,height=settings.resolution,fps=1)
        pack_frames(plan,frame_root,atlas,max_sheet_side=settings.resolution*settings.directions,pivot_x=report['pivot'][0],pivot_y=report['pivot'][1]);checked_atlas(atlas,reopened,request,report)
        guard();stage=destination.stage(request.job_id);journal('DESTINATION_STAGING',stage=str(stage))
        for name in ('sprite_stage.json','sprite_verification.json','sprite_recipe.json',*[f'sprite-{i:02d}.png' for i in range(settings.directions)]):shutil.copy2(reopened/name,stage/name)
        for name in ('sprite_sheet_000.png','sprite_atlas.json'):shutil.copy2(atlas/name,stage/name)
        (stage/'README.txt').write_text('Private neutral-pose sprite direction sample\n\nTransparent RGBA renders from the saved character, plus an exact atlas.\nDirection samples are not animation frames. No animation clips or editable Blender source are included.\nThe atlas packer does not certify geometry; sprite_receipt.json binds fresh source and saved-scene render verification.\nNoAI and original-source restrictions remain in sprite_recipe.json. Public distribution and artist/pixel-art quality require separate review.\n',encoding='utf-8')
        files={p.name:_digest(p,budget) for p in stage.iterdir()}
        receipt={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'source_render_verified':True,'saved_scene_rerender_verified':True,
            'blender_executable_sha256':hashes[Path(blender_exe).resolve()],'worker_script_sha256':_digest(Path(worker_script),budget),
            'worker_dependencies':{p.relative_to(Path(worker_script).parent.parent).as_posix():hashes[p] for p in worker_files},
            'blender_stage_job_id':result.job_id,'blender_reopen_job_id':verified.job_id,'material_stage_job_id':prepared.stage_job_id,'material_reopen_job_id':prepared.reopen_job_id,
            'bindings':options,'files':files,'project_metadata_changed':False,'animation_clips':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
        (stage/'sprite_receipt.json').write_bytes(canonical(receipt));receipt_sha=_digest(stage/'sprite_receipt.json',budget)
        stage_hashes={p.name:_digest(p,budget) for p in stage.iterdir()};stage_identity=identity(stage)
        with _lock(store.root/'.project.ucc.lock',timeout_s=min(3.,remaining())):
            guard();destination.unchanged()
            if identity(stage)!=stage_identity or {p.name for p in stage.iterdir()}!=set(stage_hashes) or any(p.is_symlink() or not p.is_file() or _digest(p,budget)!=stage_hashes.get(p.name) for p in stage.iterdir()):raise ProjectStorageError('Sprite publication staging changed')
            remaining();rename_new(stage,destination.path);published=True
        guard();journal('PRIVATE_SPRITES_PUBLISHED',receipt_sha256=receipt_sha);remaining()
        return SpriteExport(destination.path,receipt_sha,settings.directions,work,result.job_id,verified.job_id)
    except BaseException as error:
        if (published and stage is not None and not stage.exists() and destination.path.is_dir() and not destination.path.is_symlink()
                and destination.path.parent.resolve()==destination.path.parent and identity(destination.path.parent)==destination.parent_identity and identity(destination.path)==stage_identity):
            try:rename_new(destination.path,stage)
            except OSError as rollback:error.add_note('Sprite rollback failed; retained output: '+str(destination.path)+': '+str(rollback))
        try:journal('FAILED',error_type=type(error).__name__,error=str(error)[:1500],retained_stage=None if stage is None else str(stage))
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Sprite journal failure: '+str(journal_error))
        raise
