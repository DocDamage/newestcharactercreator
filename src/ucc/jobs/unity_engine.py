"""Private Unity native-import preparation; no publication or runtime approval."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
import math,shutil,time
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_contract import UnityExportRequest
from ucc.export.unity_blender_recipe import FILES
from ucc.export.unity_bind_evidence import validate_bind_observation,compare_saved_bind
from .unity_preparation import PreparedUnitySource
from .skin_material_preparation import _BudgetCancel
from .worker_resources import bundled_unity_adapter_paths
from .godot_candidate_inputs import regular_file,identity,read_json
from .master_preview import _digest
from .runner import run_process,WorkerFailure


@dataclass(frozen=True,slots=True)
class PreparedUnityEngine:
    directory: Path
    request_sha256: str
    native_mesh_sha256: str
    topology_sha256: str
    bind_evidence: dict
    receipt_sha256: str


def tree_hashes(root: Path,cancel=None) -> dict[str,str]:
    """Seal the publishable project inputs; exclude engine caches by construction."""
    result={}
    for name in ('Assets','Packages','ProjectSettings'):
        directory=root/name
        if directory.is_symlink() or not directory.is_dir() or directory.resolve()!=directory:
            raise ProjectStorageError('Unity project input directory was redirected')
        for path in directory.rglob('*'):
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or path.resolve()!=path:
                raise ProjectStorageError('Unity project contains a redirected input')
            if path.is_file():
                regular_file(path,root,512*1024*1024);result[path.relative_to(root).as_posix()]=_digest(path,cancel)
    if len(result)>512:raise ProjectStorageError('Unity project input file count exceeds the admitted profile')
    return result


def prepare_unity_engine(prepared: PreparedUnitySource,*,request: UnityExportRequest,spec: SkinMaterialSpec,
        unity_exe: Path,work: Path,guard: Callable[[],None],cancel: Event | None=None,timeout_s: float=900) -> PreparedUnityEngine:
    """Stage/attach/freshly observe native bind data. Runtime admission is separate.

    The enclosing application transaction must guard the saved project, rights
    and proof closure through publication. This layer never publishes an export.
    """
    if (type(prepared) is not PreparedUnitySource or type(request) is not UnityExportRequest or type(spec) is not SkinMaterialSpec
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600
            or prepared.request_sha256!=request.sha256 or set(dict(prepared.files))!=set(FILES)):
        raise ValidationError('Unity import preparation requires exact source/request/material contracts and a bounded deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Unity native import cancelled or deadline exceeded; no export published')
        return max(.05,deadline-time.monotonic())
    remaining();guard()
    executable=regular_file(Path(unity_exe),Path(unity_exe).parent,512*1024*1024)
    if _digest(executable,budget)!=request.unity_executable_sha256:raise ValidationError('Selected Unity executable differs from the reviewed executable')
    scripts=bundled_unity_adapter_paths()
    inputs={name:regular_file(prepared.directory/name,prepared.directory,maximum) for name,maximum in FILES.items()}
    for name,path in inputs.items():
        if _digest(path,budget)!=dict(prepared.files)[name]:raise ProjectStorageError('Prepared Unity source output changed')
    verification=regular_file(prepared.directory/'unity_source_verification.json',prepared.directory,64*1024)
    if _digest(verification,budget)!=prepared.verification_sha256:raise ProjectStorageError('Prepared Unity source verification changed')
    protected={executable,*scripts.values(),*inputs.values(),verification}
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def unchanged():
        remaining();guard()
        for path,value in hashes.items():
            if path.is_symlink() or not path.is_file() or identity(path)!=identities[path] or _digest(path,budget)!=value:
                raise ProjectStorageError('Unity executable, source or adapter changed during import')
    reference=read_json(inputs['source_reference.json'],64*1024*1024)
    if reference.get('material_spec')!=spec.to_dict():raise ValidationError('Reviewed material differs from the prepared source reference')
    work=Path(work)
    if not work.is_absolute() or work.exists() or work.is_symlink() or work.parent.resolve()!=work.parent:
        raise ProjectStorageError('Unity import needs an exclusive canonical private working folder')
    work.mkdir();stage=work/'stage';assets=stage/'Assets/UCC';assets.mkdir(parents=True)
    for name in ('character.fbx','source_weights.json','source_reference.json'):shutil.copy2(inputs[name],assets/name)
    for name,path in scripts.items():
        target=assets/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    for name in ('Packages','ProjectSettings'):(stage/name).mkdir()
    (stage/'Packages/manifest.json').write_bytes(canonical_bytes({'dependencies':{}}))
    (stage/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.4.5f1\n',encoding='utf-8')
    (stage/'request.json').write_bytes(canonical_bytes(request.to_dict()))
    recipe={'schema_version':1,'policy':'UCC_UNITY_EDITOR_JOB_V1','request_sha256':request.sha256,
        'master_sha256':dict(request.source_bindings)['master'],'weights_sha256':dict(prepared.files)['source_weights.json'],
        'fbx_sha256':dict(prepared.files)['character.fbx'],'source_reference_sha256':dict(prepared.files)['source_reference.json'],
        'native_mesh_sha256':'','topology_sha256':'','color_srgb':dict(zip('rgba',(*spec.base_color_srgb,1.))),'roughness':spec.roughness}
    (stage/'engine_recipe.json').write_bytes(canonical_bytes(recipe))
    commands=[]
    def run(folder: Path,method: str,label: str):
        unchanged()
        immutable={p:_digest(p,budget) for p in [folder/'request.json',folder/'engine_recipe.json',
            *(folder/'Assets/UCC'/name for name in ('character.fbx','source_weights.json','source_reference.json',*scripts))]}
        command=[str(executable),'-batchmode','-nographics','-quit','-noUpm','-disableManagedDebugger','-projectPath',str(folder),
            '-executeMethod','Ucc.UnityAdapter.Editor.UccUnityExportJobs.'+method,'-logFile',str(work/(label+'-Editor.log'))]
        outcome=run_process(command,work/label,timeout_s=remaining(),cancel=budget)
        user_cancelled=cancel is not None and cancel.is_set()
        total_deadline_exceeded=time.monotonic()>=deadline
        commands.append({'phase':label,'command':command,'return_code':outcome.return_code,'cancelled':user_cancelled,
            'timed_out':outcome.timed_out or total_deadline_exceeded,'elapsed_seconds':outcome.elapsed_seconds,
            'process_cancelled':outcome.cancelled,'process_timed_out':outcome.timed_out,'total_deadline_exceeded':total_deadline_exceeded})
        (work/'commands.json').write_bytes(canonical_bytes({'commands':commands}))
        if outcome.return_code!=0 or outcome.cancelled or outcome.timed_out or total_deadline_exceeded:
            reason='cancelled by caller' if user_cancelled else 'total deadline exceeded' if total_deadline_exceeded else 'process timed out' if outcome.timed_out else 'process failed'
            raise WorkerFailure('Unity '+label+' '+reason+'; logs: '+str(work))
        unchanged()
        if any(p.is_symlink() or not p.is_file() or _digest(p,budget)!=value for p,value in immutable.items()):
            raise ProjectStorageError('Unity modified a protected source, request or first-party script')
    try:
        run(stage,'Stage','native-import')
        stage_observation=read_json(stage/'native-stage.json',64*1024*1024)
        topology,evidence=validate_bind_observation(reference,stage_observation,request_sha256=request.sha256,
            master_sha256=recipe['master_sha256'],mode='stage')
        if stage_observation['runtime_component_present']:raise ValidationError('Initial imported model unexpectedly contains a runtime component')
        (assets/'source_quads.json').write_bytes(canonical_bytes(topology.to_dict()))
        recipe.update(native_mesh_sha256=topology.native_mesh_sha256,topology_sha256=topology.sha256)
        (stage/'engine_recipe.json').write_bytes(canonical_bytes(recipe))
        run(stage,'Attach','attach-source-topology')
        attached=read_json(stage/'native-attached.json',64*1024*1024)
        validate_bind_observation(reference,attached,request_sha256=request.sha256,master_sha256=recipe['master_sha256'],mode='stage')
        compare_saved_bind(stage_observation,attached)
        sealed=tree_hashes(stage,budget);(work/'saved-inputs.json').write_bytes(canonical_bytes(sealed))
        reopened=work/'reopen';reopened.mkdir()
        for name in ('Assets','Packages','ProjectSettings'):shutil.copytree(stage/name,reopened/name)
        for name in ('request.json','engine_recipe.json'):shutil.copy2(stage/name,reopened/name)
        if tree_hashes(reopened,budget)!=sealed:raise ProjectStorageError('Fresh Unity input copy differs from the saved stage')
        run(reopened,'Reopen','fresh-saved-reopen')
        if tree_hashes(reopened,budget)!=sealed or tree_hashes(stage,budget)!=sealed:
            raise ProjectStorageError('Unity fresh reopen changed saved source, scene, adapter or settings')
        observed=read_json(reopened/'native-reopen.json',64*1024*1024)
        checked,reopen_evidence=validate_bind_observation(reference,observed,request_sha256=request.sha256,
            master_sha256=recipe['master_sha256'],mode='reopen')
        compare_saved_bind(stage_observation,observed)
        if checked.sha256!=topology.sha256:raise ValidationError('Fresh Unity topology/native mesh bindings differ')
        unchanged()
        receipt={'schema_version':1,'policy':'UCC_UNITY_NATIVE_IMPORT_PREPARATION_V1','request_sha256':request.sha256,
            'source_verification_sha256':prepared.verification_sha256,'unity_executable_sha256':hashes[executable],
            'saved_files':sealed,'stage_bind_evidence':evidence,'reopen_bind_evidence':reopen_evidence,
            'native_observations':{n:_digest(folder/n,budget) for folder,n in [(stage,'native-stage.json'),(stage,'native-attached.json'),(reopened,'native-reopen.json')]},
            'commands':commands,'saved_scene_reopened_without_repair':True,'runtime_verified':False,'export_published':False,
            'visual_quality_approved':False,'distribution_license_review_complete':False}
        receipt_path=work/'native-import-receipt.json';receipt_path.write_bytes(canonical_bytes(receipt))
        return PreparedUnityEngine(reopened,request.sha256,topology.native_mesh_sha256,topology.sha256,reopen_evidence,_digest(receipt_path,budget))
    except BaseException as error:
        (work/'failure.json').write_bytes(canonical_bytes({'schema_version':1,'export_published':False,'error_type':type(error).__name__,'error':str(error)[:1500]}))
        raise
