"""Fresh material/animated render/reopen and reversible exclusive publication."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math,os,shutil,time
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore,_lock
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.expression_clip import build_expression_clip
from ucc.core.facial_sprites import FacialSpriteRequest,POLICY,STAGE,VERIFY,TARGET_BINDINGS
from ucc.core.sprite_render import canonical
from ucc.sprites.plan import CameraProfile,build_plan
from ucc.sprites.atlas import pack_frames
from ucc.sprites.facial_evidence import checked_facial_evidence,checked_facial_atlas
from .static_export_sources import static_export_sources
from .skin_material_preparation import prepare_skin_material_revision,_BudgetCancel
from .expression_keys import installed_expression_inputs
from .expression_storage import safe_directory
from .export_destination import ExportDestination,rename_new
from .godot_candidate_inputs import identity,regular_file,read_json
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .runner import BlenderJobRunner
from .protocol import JobRequest


@dataclass(frozen=True,slots=True)
class FacialSpriteExport:
    destination: Path
    receipt_sha256: str
    frame_count: int
    workdir: Path
    stage_job_id: str
    reopen_job_id: str


def export_facial_sprites(store: ProjectStore,*,request: FacialSpriteRequest,destination: ExportDestination,
        blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,cancel: Event | None=None,timeout_s: float=3600) -> FacialSpriteExport:
    if not isinstance(request,FacialSpriteRequest) or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Animated sprites need an explicit reviewed request and bounded total deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Animated sprite rendering cancelled or total deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load();destination.unchanged();r=request.review
    review,sources,binding=static_export_sources(store,project_id=r.project_id,revision=r.revision,master_blend=initial.master_blend,cancel=budget,purpose='Animated sprite rendering')
    if (review.project_sha256!=r.project_sha256 or dict(r.source_bindings)!={s.asset_id:s.sha256 for s in review.sources}
            or canonical(build_expression_clip(initial,dict(r.source_bindings)['master']))!=request.clip_json):
        raise ProjectConflict('Animated sprite source, strengths or clip review is stale')
    targets=installed_expression_inputs(mpfb_data_dir,budget);worker_files=worker_dependency_files(Path(worker_script))
    protected={store.file,*sources.values(),*targets.values(),Path(blender_exe).resolve(),*worker_files}
    protected.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    protected.update(safe_directory(store,'materials','proofs')/(binding[k]+'.json') for k in ('recipe_sha256','stage_sha256','verification_sha256'))
    protected.update(safe_directory(store,'master','versions')/(binding[k]+'.blend') for k in ('source_master_sha256','material_master_sha256','final_master_sha256'))
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def guard():
        remaining()
        if worker_dependency_files(Path(worker_script))!=worker_files:raise ProjectStorageError('Animated sprite worker resource set changed')
        if store.load()!=initial:raise ProjectConflict('Saved character changed during animated rendering')
        for p,h in hashes.items():
            if p.is_symlink() or not p.is_file() or identity(p)!=identities[p] or _digest(p,budget)!=h:raise ProjectStorageError('Animated sprite input, proof or adapter changed')
        current,_,_=static_export_sources(store,project_id=r.project_id,revision=r.revision,master_blend=initial.master_blend,cancel=budget,purpose='Animated sprite rendering')
        if current!=review or installed_expression_inputs(mpfb_data_dir,budget)!=targets:raise ProjectConflict('Animated sprite source/target review changed')
    work=safe_directory(store,'.ucc-jobs',create=True)/('facial-sprites-'+r.job_id);work.mkdir(exist_ok=False)
    stage=None;published=False
    def journal(state: str,**extra):
        path=work/'job_status.json';temporary=work/'job_status.tmp'
        if path.is_symlink() or temporary.exists() or temporary.is_symlink():raise ProjectStorageError('Animated sprite journal changed or redirected')
        with temporary.open('xb') as stream:
            stream.write(canonical({'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'state':state,'destination':str(destination.path),**extra}));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    try:
        journal('SOURCE_AND_MATERIAL_VERIFICATION');spec=SkinMaterialSpec.from_dict(binding['spec'])
        prepared=prepare_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=worker_script,mpfb_data_dir=mpfb_data_dir,
            expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend,cancel=budget,timeout_s=remaining())
        if (prepared.material_master_sha256!=prepared.source_master_sha256 or prepared.source_master_sha256!=Path(initial.master_blend).stem
                or read_json(prepared.directory/'material_stage.json',4*1024*1024).get('changed') is not False):raise ProjectStorageError('Animated sprites cannot repair or replace the saved master')
        guard();recipe=work/'facial_sprite_recipe.json';recipe.write_bytes(canonical({'schema_version':1,'policy':POLICY,'request':request.to_dict(),'material_spec':spec.to_dict()}))
        clip=work/'expression_clip.json';clip.write_bytes(request.clip_json)
        options={'master_sha256':prepared.source_master_sha256,'recipe_sha256':_digest(recipe,budget),'clip_sha256':_digest(clip,budget),**TARGET_BINDINGS}
        runner=BlenderJobRunner(Path(blender_exe),safe_directory(store,'.ucc-jobs'),Path(worker_script));journal('BLENDER_ANIMATED_RENDER')
        initial_inputs={'candidate.blend':store.root/initial.master_blend,'facial_sprite_recipe.json':recipe,'expression_clip.json':clip,**targets}
        result,rendered=runner.run(JobRequest.new(STAGE,input_project='candidate.blend',options=options),staged_inputs=initial_inputs,timeout_s=remaining(),cancel=budget)
        guard();options.update({k:result.details[k] for k in ('scene_sha256','stage_sha256')})
        if result.details!={'policy':POLICY,**{k:options[k] for k in ('scene_sha256','stage_sha256')}}:raise ValidationError('Incomplete animated sprite stage')
        settings=r.settings;names=[f'facial-{i:02d}-{f:02d}.png' for i in range(settings.directions) for f in range(1,26)]
        inputs={**{n:regular_file(rendered/n,rendered,128*1024*1024) for n in (*initial_inputs,'facial_sprite_scene.blend','facial_sprite_stage.json',*names)}}
        input_hashes={n:_digest(p,budget) for n,p in inputs.items()}
        if input_hashes['facial_sprite_scene.blend']!=options['scene_sha256'] or input_hashes['facial_sprite_stage.json']!=options['stage_sha256']:raise ValidationError('Animated stage changed before reopening')
        journal('BLENDER_ORIGINAL_SOURCE_AND_SAVED_RERENDER')
        verified,reopened=runner.run(JobRequest.new(VERIFY,input_project='candidate.blend',options=options),staged_inputs=inputs,timeout_s=remaining(),cancel=budget)
        guard();report,proof=checked_facial_evidence(reopened,request,options)
        if canonical(verified.details)!=canonical(proof):raise ValidationError('Animated sprite reply differs from its proof')
        if any(_digest(inputs[n],budget)!=h or _digest(reopened/n,budget)!=h for n,h in input_hashes.items()):raise ProjectStorageError('Animated staged input changed during verification')
        frame_root=work/'atlas-inputs';atlas=work/'atlas'
        for direction in range(settings.directions):
            path=frame_root/f'facial/dir-{direction:02d}';path.mkdir(parents=True,exist_ok=False)
            for i in range(25):shutil.copy2(reopened/f'facial-{direction:02d}-{i+1:02d}.png',path/f'frame-{i:04d}.png')
        scale=next(v['camera']['ortho_scale'] for v in report['configuration']['objects'].values() if 'camera' in v)
        camera=CameraProfile(yaw_deg=settings.yaw_deg,pitch_deg=settings.pitch_deg,orthographic_scale=scale,directions=settings.directions)
        plan=build_plan({'facial':25},camera,width=settings.resolution,height=settings.resolution,fps=24)
        pack_frames(plan,frame_root,atlas,max_sheet_side=settings.resolution*5,pivot_x=report['pivot'][0],pivot_y=report['pivot'][1])
        checked_facial_atlas(atlas,reopened,request,report);guard();stage=destination.stage(r.job_id);journal('DESTINATION_STAGING',stage=str(stage))
        for name in (*names,'facial_sprite_stage.json','facial_sprite_verification.json','facial_sprite_recipe.json','expression_clip.json'):shutil.copy2(reopened/name,stage/name)
        for name in ('sprite_atlas.json',*[f'sprite_sheet_{i:03d}.png' for i in range(settings.directions)]):shutil.copy2(atlas/name,stage/name)
        (stage/'README.txt').write_text('Private animated facial sprites\n\n25 frames per direction at 24 fps: neutral, saved expression strengths, neutral.\nEach 5x5 sheet is one direction in row-major timeline order. Endpoints are included.\nOriginal-source and saved-Action geometry, normals and pixels match every frame.\nNo editable source or body-animation clip is included. NoAI/source restrictions remain in the recipe.\nArtist/pixel-art quality and public distribution require separate review.\n',encoding='utf-8')
        files={p.name:_digest(p,budget) for p in stage.iterdir()}
        receipt={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'bindings':options,'files':files,
            'blender_executable_sha256':hashes[Path(blender_exe).resolve()],'worker_script_sha256':_digest(Path(worker_script),budget),
            'worker_dependencies':{p.relative_to(Path(worker_script).parent.parent).as_posix():hashes[p] for p in worker_files},
            'material_stage_job_id':prepared.stage_job_id,'material_reopen_job_id':prepared.reopen_job_id,'blender_stage_job_id':result.job_id,'blender_reopen_job_id':verified.job_id,
            'source_render_verified':True,'saved_scene_rerender_verified':True,'frame_count':25*settings.directions,'fps':24,'exact_neutral_endpoints':True,
            'animation_clips':True,'project_metadata_changed':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
        (stage/'facial_sprite_receipt.json').write_bytes(canonical(receipt));receipt_sha=_digest(stage/'facial_sprite_receipt.json',budget)
        stage_hashes={p.name:_digest(p,budget) for p in stage.iterdir()};stage_identity=identity(stage)
        with _lock(store.root/'.project.ucc.lock',timeout_s=min(3.,remaining())):
            guard();destination.unchanged()
            if identity(stage)!=stage_identity or {p.name for p in stage.iterdir()}!=set(stage_hashes) or any(p.is_symlink() or not p.is_file() or _digest(p,budget)!=stage_hashes.get(p.name) for p in stage.iterdir()):raise ProjectStorageError('Animated publication stage changed')
            remaining();rename_new(stage,destination.path);published=True
        guard();journal('PRIVATE_ANIMATED_SPRITES_PUBLISHED',receipt_sha256=receipt_sha);remaining()
        return FacialSpriteExport(destination.path,receipt_sha,25*settings.directions,work,result.job_id,verified.job_id)
    except BaseException as error:
        if (published and stage is not None and not stage.exists() and destination.path.is_dir() and not destination.path.is_symlink()
                and destination.path.parent.resolve()==destination.path.parent and identity(destination.path.parent)==destination.parent_identity and identity(destination.path)==stage_identity):
            try:rename_new(destination.path,stage)
            except OSError as rollback:error.add_note('Animated sprite rollback failed; retained output: '+str(destination.path)+': '+str(rollback))
        try:journal('FAILED',error_type=type(error).__name__,error=str(error)[:1500],retained_stage=None if stage is None else str(stage))
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Animated sprite journal failure: '+str(journal_error))
        raise
