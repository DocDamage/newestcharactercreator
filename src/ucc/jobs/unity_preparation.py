"""Guarded source-only Blender stage/reopen for a reviewed Unity request."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math,time
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.storage import ProjectStore
from ucc.export.unity_contract import UnityExportRequest
from ucc.export.unity_blender_recipe import POLICY,STAGE,VERIFY,FILES,recipe
from ucc.export.godot_candidate_contract import canonical_bytes
from .static_export_sources import static_export_sources
from .skin_material_preparation import _BudgetCancel
from .expression_verification import verify_saved_expression_master
from .expression_storage import safe_directory
from .godot_candidate_inputs import regular_file,identity,read_json
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class PreparedUnitySource:
    directory: Path
    files: tuple[tuple[str,str],...]
    verification_sha256: str
    stage_job_id: str
    verify_job_id: str
    request_sha256: str


def prepare_unity_source(store: ProjectStore,*,request: UnityExportRequest,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,cancel: Event | None=None,timeout_s: float=900) -> PreparedUnitySource:
    if (type(request) is not UnityExportRequest or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600):
        raise ValidationError('Unity source preparation needs a reviewed request and bounded deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Unity source preparation cancelled or deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load()
    review,sources,binding=static_export_sources(store,project_id=request.project_id,revision=request.revision,
        master_blend=initial.master_blend,cancel=budget,purpose='Unity export')
    if review.project_sha256!=request.project_sha256 or dict(request.source_bindings)!={s.asset_id:s.sha256 for s in review.sources}:
        raise ProjectConflict('Unity source review is stale')
    executable=regular_file(Path(blender_exe),Path(blender_exe).parent,512*1024*1024)
    worker=regular_file(Path(worker_script),Path(worker_script).parent,256*1024)
    protected={store.file,*sources.values(),executable,*worker_dependency_files(worker),*Path(__file__).resolve().parents[1].rglob('*.py')}
    hashes={path:_digest(path,budget) for path in protected};identities={path:identity(path) for path in protected}
    def guard():
        remaining()
        if store.load()!=initial:raise ProjectConflict('Saved character changed during Unity source export')
        for path,value in hashes.items():
            if path.is_symlink() or not path.is_file() or identity(path)!=identities[path] or _digest(path,budget)!=value:
                raise ProjectStorageError('Unity source, executable, contract or worker changed')
        current,_,_=static_export_sources(store,project_id=request.project_id,revision=request.revision,
            master_blend=initial.master_blend,cancel=budget,purpose='Unity export')
        if current!=review:raise ProjectConflict('Unity source closure changed during export')
    guard();root=safe_directory(store,'.ucc-jobs',create=True);work=root/('unity-source-'+request.job_id);work.mkdir(exist_ok=False)
    journal=work/'preparation.json'
    def status(state,**extra):
        temporary=work/'preparation.tmp'
        if temporary.exists() or temporary.is_symlink() or journal.is_symlink():raise ProjectStorageError('Unity preparation journal redirected')
        temporary.write_bytes(canonical_bytes({'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'state':state,**extra}));temporary.replace(journal)
    try:
        status('VERIFY_SAVED_EXPRESSION_MASTER')
        verify_saved_expression_master(store,blender_exe=executable,worker_script=worker,mpfb_data_dir=mpfb_data_dir,
            expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend,
            cancel=budget,timeout_s=remaining());guard()
        document=recipe(request,SkinMaterialSpec.from_dict(binding['spec']));recipe_path=work/'unity_source_recipe.json';recipe_path.write_bytes(canonical_bytes(document))
        options={'master_sha256':dict(request.source_bindings)['master'],'recipe_sha256':_digest(recipe_path,budget)}
        runner=BlenderJobRunner(executable,work/'workers',worker)
        status('BLENDER_UNITY_SOURCE_STAGE')
        stage_job=JobRequest.new(STAGE,input_project='candidate.blend',options=options)
        staged,folder=runner.run(stage_job,staged_inputs={'candidate.blend':sources['master'],'unity_source_recipe.json':recipe_path},cancel=budget,timeout_s=remaining());guard()
        files={name:regular_file(folder/name,folder,maximum) for name,maximum in FILES.items()}
        output_hashes={name:_digest(path,budget) for name,path in files.items()}
        if staged.details!={'policy':POLICY,'request_sha256':request.sha256,'files':output_hashes,'engine_import_verified':False}:
            raise ValidationError('Unity source stage reply differs from its actual outputs')
        status('BLENDER_UNITY_SOURCE_FRESH_REOPEN')
        verify_job=JobRequest.new(VERIFY,input_project='candidate.blend',options={**options,
            **{name.replace('.','_')+'_sha256':value for name,value in output_hashes.items()}})
        inputs={'candidate.blend':sources['master'],'unity_source_recipe.json':recipe_path,**files}
        verified,reopened=runner.run(verify_job,staged_inputs=inputs,cancel=budget,timeout_s=remaining());guard()
        path=regular_file(reopened/'unity_source_verification.json',reopened,64*1024);verification_sha=_digest(path,budget)
        if verified.details!={'policy':POLICY,'request_sha256':request.sha256,'verification_sha256':verification_sha,'files':output_hashes,'engine_import_verified':False}:
            raise ValidationError('Fresh Unity source verification differs from actual output bindings')
        expected={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'recipe_sha256':options['recipe_sha256'],
            'master_sha256':options['master_sha256'],'files':output_hashes,'original_state_preserved':True,
            'source_reference_recomputed':True,'exported_fbx_rebuilt':False,'engine_import_verified':False,'project_pointer_changed':False}
        if canonical_bytes(read_json(path,64*1024))!=canonical_bytes(expected):raise ValidationError('Unity source verification changed capabilities or source bindings')
        for name,path in inputs.items():
            if _digest(path,budget)!=_digest(reopened/name,budget):raise ProjectStorageError('Unity verification changed staged input/output bytes')
        guard();status('UNITY_SOURCE_VERIFIED_ENGINE_IMPORT_PENDING',files=output_hashes,verification_sha256=verification_sha,
            stage_job_id=stage_job.job_id,verify_job_id=verify_job.job_id)
        return PreparedUnitySource(reopened,tuple(sorted(output_hashes.items())),verification_sha,stage_job.job_id,verify_job.job_id,request.sha256)
    except BaseException as error:
        try:status('FAILED',error_type=type(error).__name__,error=str(error)[:1200])
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Unity journal failure: '+str(journal_error))
        raise
