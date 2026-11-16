"""Guarded actual-source runtime sampling, independent original-master reopen."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math,time
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.storage import ProjectStore
from ucc.export.unity_contract import UnityExportRequest
from ucc.export.unity_runtime_source import POLICY,STAGE,VERIFY,FILES,CASES,recipe
from ucc.export.godot_candidate_contract import canonical_bytes
from .unity_preparation import PreparedUnitySource
from .static_export_sources import static_export_sources
from .skin_material_preparation import _BudgetCancel
from .expression_storage import safe_directory
from .godot_candidate_inputs import regular_file,read_json,identity
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .runner import BlenderJobRunner
from .protocol import JobRequest


@dataclass(frozen=True,slots=True)
class PreparedUnityRuntimeSource:
    directory: Path
    files: tuple[tuple[str,str],...]
    verification_sha256: str
    request_sha256: str
    bind_reference_sha256: str
    stage_job_id: str
    verify_job_id: str


def prepare_unity_runtime_source(store: ProjectStore,prepared: PreparedUnitySource,*,request: UnityExportRequest,
        blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,cancel: Event | None=None,timeout_s: float=900) -> PreparedUnityRuntimeSource:
    if (type(prepared) is not PreparedUnitySource or type(request) is not UnityExportRequest or prepared.request_sha256!=request.sha256
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600):
        raise ValidationError('Unity runtime sampling requires exact reviewed source and bounded deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Unity runtime source sampling cancelled or deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load()
    review,sources,binding=static_export_sources(store,project_id=request.project_id,revision=request.revision,
        master_blend=initial.master_blend,cancel=budget,purpose='Unity runtime source verification')
    if (review.project_sha256!=request.project_sha256 or dict(request.source_bindings)!={s.asset_id:s.sha256 for s in review.sources}
            or initial.expression is None):raise ProjectConflict('Unity runtime source review is stale or expression controls are absent')
    bind=regular_file(prepared.directory/'source_reference.json',prepared.directory,64*1024*1024)
    bind_sha=dict(prepared.files).get('source_reference.json')
    if _digest(bind,budget)!=bind_sha:raise ProjectStorageError('Prepared Unity bind reference changed')
    source_verify=regular_file(prepared.directory/'unity_source_verification.json',prepared.directory,64*1024)
    if _digest(source_verify,budget)!=prepared.verification_sha256:raise ProjectStorageError('Prepared Unity source verification changed')
    executable=regular_file(Path(blender_exe),Path(blender_exe).parent,512*1024*1024)
    worker=regular_file(Path(worker_script),Path(worker_script).parent,256*1024)
    protected={store.file,*sources.values(),bind,source_verify,executable,*worker_dependency_files(worker),*Path(__file__).resolve().parents[1].rglob('*.py')}
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def guard():
        remaining()
        if store.load()!=initial:raise ProjectConflict('Saved character changed during Unity runtime source sampling')
        for p,value in hashes.items():
            if p.is_symlink() or not p.is_file() or identity(p)!=identities[p] or _digest(p,budget)!=value:
                raise ProjectStorageError('Unity runtime source, worker or executable changed')
        current,_,_=static_export_sources(store,project_id=request.project_id,revision=request.revision,
            master_blend=initial.master_blend,cancel=budget,purpose='Unity runtime source verification')
        if current!=review:raise ProjectConflict('Unity runtime source proof closure changed')
    guard();work=safe_directory(store,'.ucc-jobs',create=True)/('unity-runtime-source-'+request.job_id);work.mkdir(exist_ok=False)
    document=recipe(request,SkinMaterialSpec.from_dict(binding['spec']),dict(initial.expression.parameters),bind_sha)
    recipe_file=work/'unity_runtime_recipe.json';recipe_file.write_bytes(canonical_bytes(document))
    options={'master_sha256':dict(request.source_bindings)['master'],'recipe_sha256':_digest(recipe_file,budget),'bind_reference_sha256':bind_sha}
    runner=BlenderJobRunner(executable,work/'workers',worker)
    try:
        staged=JobRequest.new(STAGE,input_project='candidate.blend',options=options)
        base={'candidate.blend':sources['master'],'unity_runtime_recipe.json':recipe_file,'source_reference.json':bind}
        result,folder=runner.run(staged,staged_inputs=base,cancel=budget,timeout_s=remaining());guard()
        files={name:regular_file(folder/name,folder,maximum) for name,maximum in FILES.items()}
        output_hashes={name:_digest(p,budget) for name,p in files.items()}
        if result.details!={'policy':POLICY,'request_sha256':request.sha256,'files':output_hashes,'runtime_verified':False}:
            raise ValidationError('Runtime source stage reply differs from its actual output bindings')
        verified=JobRequest.new(VERIFY,input_project='candidate.blend',options={**options,
            **{n.replace('.','_')+'_sha256':v for n,v in output_hashes.items()}})
        result,reopened=runner.run(verified,staged_inputs={**base,**files},cancel=budget,timeout_s=remaining());guard()
        path=regular_file(reopened/'unity_runtime_verification.json',reopened,64*1024);verification_sha=_digest(path,budget)
        if result.details!={'policy':POLICY,'request_sha256':request.sha256,'files':output_hashes,'verification_sha256':verification_sha,'runtime_verified':False}:
            raise ValidationError('Runtime source reopen reply differs from actual verification bytes')
        expected={'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'master_sha256':options['master_sha256'],
            'recipe_sha256':options['recipe_sha256'],'bind_reference_sha256':bind_sha,'files':output_hashes,'case_count':CASES,
            'source_recomputed_without_rewriting_outputs':True,'original_state_preserved':True,'runtime_verified':False}
        if canonical_bytes(read_json(path,64*1024))!=canonical_bytes(expected):raise ValidationError('Runtime source verification changed scope or source bindings')
        for name,p in {**base,**files}.items():
            if _digest(p,budget)!=_digest(reopened/name,budget):raise ProjectStorageError('Fresh runtime source verification modified staged input/output bytes')
        guard();(work/'preparation.json').write_bytes(canonical_bytes(expected))
        return PreparedUnityRuntimeSource(reopened,tuple(sorted(output_hashes.items())),verification_sha,request.sha256,bind_sha,staged.job_id,verified.job_id)
    except BaseException as error:
        (work/'failure.json').write_bytes(canonical_bytes({'schema_version':1,'runtime_verified':False,'error_type':type(error).__name__,'error':str(error)[:1500]}))
        raise
