"""Actual automatic Unity frames admitted against fresh original-source vectors."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
import math,shutil,time
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_contract import UnityExportRequest
from ucc.export.unity_topology import UnityQuadSource
from ucc.export.unity_runtime_source import FILES,CASES,VECTOR_BYTES
from ucc.export.unity_runtime_evidence import checked_plan,verify_source_binary,compare_gpu_record,NATIVE_BINARY_BYTES,RECORD_BYTES
from .unity_engine import PreparedUnityEngine,tree_hashes
from .unity_runtime_preparation import PreparedUnityRuntimeSource
from .worker_resources import bundled_unity_adapter_paths
from .skin_material_preparation import _BudgetCancel
from .godot_candidate_inputs import regular_file,read_json,identity
from .master_preview import _digest
from .runner import run_process,WorkerFailure
from .private_render_evidence import png_measurements


@dataclass(frozen=True,slots=True)
class VerifiedUnityRuntime:
    directory: Path
    request_sha256: str
    receipt_sha256: str
    maximum_source_position_error_m: float
    maximum_normal_angle_deg: float


def verify_unity_runtime(engine: PreparedUnityEngine,source: PreparedUnityRuntimeSource,*,request: UnityExportRequest,
        unity_exe: Path,work: Path,guard: Callable[[],None],cancel: Event | None=None,timeout_s: float=900) -> VerifiedUnityRuntime:
    if (type(engine) is not PreparedUnityEngine or type(source) is not PreparedUnityRuntimeSource or type(request) is not UnityExportRequest
            or engine.request_sha256!=request.sha256 or source.request_sha256!=request.sha256
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600):
        raise ValidationError('Unity runtime admission needs exact engine/source/request identities and bounded deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Unity runtime verification cancelled or total deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();guard()
    exe=regular_file(Path(unity_exe),Path(unity_exe).parent,512*1024*1024)
    if _digest(exe,budget)!=request.unity_executable_sha256:raise ValidationError('Unity runtime executable differs from the reviewed executable')
    receipt=regular_file(engine.directory.parent/'native-import-receipt.json',engine.directory.parent,2*1024*1024)
    if _digest(receipt,budget)!=engine.receipt_sha256:raise ProjectStorageError('Unity native import receipt changed')
    saved=read_json(receipt,2*1024*1024)['saved_files']
    if tree_hashes(engine.directory,budget)!=saved:raise ProjectStorageError('Unity saved native inputs changed before runtime admission')
    scripts=bundled_unity_adapter_paths();files={n:regular_file(source.directory/n,source.directory,maximum) for n,maximum in FILES.items()}
    if any(_digest(path,budget)!=dict(source.files).get(name) for name,path in files.items()):raise ProjectStorageError('Original runtime source data changed')
    proof=regular_file(source.directory/'unity_runtime_verification.json',source.directory,64*1024)
    if _digest(proof,budget)!=source.verification_sha256:raise ProjectStorageError('Original runtime source proof changed')
    topology_path=regular_file(engine.directory/'Assets/UCC/source_quads.json',engine.directory,8*1024*1024)
    topology=UnityQuadSource.from_dict(read_json(topology_path,8*1024*1024))
    if topology.sha256!=engine.topology_sha256 or topology.native_mesh_sha256!=engine.native_mesh_sha256:
        raise ValidationError('Unity runtime native/topology bindings differ from the prepared import')
    manifest=read_json(files['unity_runtime_source.json'],2*1024*1024)
    plan=checked_plan(manifest,request_sha256=request.sha256,master_sha256=dict(request.source_bindings)['master'],
        bind_reference_sha256=source.bind_reference_sha256,native_mesh_sha256=engine.native_mesh_sha256,
        topology_sha256=engine.topology_sha256,bone_names=topology.bone_names,shape_names=topology.shape_names)
    plan['source_manifest_sha256']=dict(source.files)['unity_runtime_source.json']
    source_data=files['unity_runtime_source.bin'].read_bytes();verify_source_binary(source_data,manifest)
    protected={exe,receipt,proof,*files.values(),*scripts.values()}
    hashes={p:_digest(p,budget) for p in protected};identities={p:identity(p) for p in protected}
    def unchanged():
        remaining();guard()
        if tree_hashes(engine.directory,budget)!=saved:raise ProjectStorageError('Unity native saved project changed during runtime verification')
        for path,value in hashes.items():
            if path.is_symlink() or not path.is_file() or identity(path)!=identities[path] or _digest(path,budget)!=value:
                raise ProjectStorageError('Unity runtime source, proof, adapter or executable changed')
    work=Path(work)
    if not work.is_absolute() or work.exists() or work.is_symlink() or work.parent.resolve()!=work.parent:
        raise ProjectStorageError('Unity runtime verifier requires an exclusive canonical private work folder')
    work.mkdir();project=work/'project';project.mkdir()
    for name in ('Assets','Packages','ProjectSettings'):shutil.copytree(engine.directory/name,project/name)
    for name in ('request.json','engine_recipe.json'):shutil.copy2(engine.directory/name,project/name)
    for name,path in scripts.items():
        target=project/'Assets/UCC'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and _digest(target,budget)!=hashes[path]:raise ProjectStorageError('Prepared Unity project contains a different first-party adapter')
        if not target.exists():shutil.copy2(path,target)
    plan_file=project/'runtime-plan.json';plan_file.write_bytes(canonical_bytes(plan))
    (project/'runtime-inputs.json').write_bytes(canonical_bytes({'plan_sha256':_digest(plan_file,budget),'request_sha256':request.sha256,
        'native_mesh_sha256':engine.native_mesh_sha256,'topology_sha256':engine.topology_sha256}))
    sealed=tree_hashes(project,budget);inputs={p:_digest(p,budget) for p in [project/'request.json',project/'engine_recipe.json',plan_file,project/'runtime-inputs.json']}
    (work/'saved-inputs.json').write_bytes(canonical_bytes(sealed))
    command=[str(exe),'-batchmode','-force-d3d11','-noUpm','-disableManagedDebugger','-projectPath',str(project),
        '-executeMethod','Ucc.UnityAdapter.Editor.UccUnityRuntimeJob.Run','-logFile',str(work/'Editor.log')]
    (work/'command.json').write_bytes(canonical_bytes({'command':command}))
    result=run_process(command,work/'process',cancel=budget,timeout_s=remaining())
    (work/'process-result.json').write_bytes(canonical_bytes({'return_code':result.return_code,'process_cancelled':result.cancelled,
        'process_timed_out':result.timed_out,'total_deadline_exceeded':time.monotonic()>=deadline,'elapsed_seconds':result.elapsed_seconds}))
    if result.return_code!=0 or result.cancelled or result.timed_out:raise WorkerFailure('Actual graphical Unity runtime verification failed/cancelled/timed out; logs: '+str(work))
    unchanged()
    if tree_hashes(project,budget)!=sealed or any(_digest(p,budget)!=value for p,value in inputs.items()):
        raise ProjectStorageError('Graphical Unity verification changed a saved source, request, adapter, scene or setting')
    observed=read_json(project/'runtime-observation.json',2*1024*1024)
    expected_keys={'schema_version','policy','request_sha256','source_manifest_sha256','native_mesh_sha256','topology_sha256','unity','graphics','color_space','skin_weights','rows','cleanup_restored','runtime_verified','visual_quality_approved'}
    if (set(observed)!=expected_keys or type(observed['schema_version']) is not int or observed['schema_version']!=1
            or observed['policy']!='UCC_UNITY_GPU_OBSERVATION_V1' or observed['request_sha256']!=request.sha256
            or observed['source_manifest_sha256']!=plan['source_manifest_sha256'] or observed['native_mesh_sha256']!=engine.native_mesh_sha256
            or observed['topology_sha256']!=engine.topology_sha256 or observed['unity']!='6000.4.5f1' or observed['graphics']!='Direct3D11'
            or observed['color_space']!='Linear' or observed['skin_weights']!='Unlimited' or observed['cleanup_restored'] is not True
            or observed['runtime_verified'] is not False or observed['visual_quality_approved'] is not False
            or type(observed['rows']) is not list or len(observed['rows'])!=CASES*2):
        raise ValidationError('Actual Unity runtime observation lacks complete bound native evidence')
    binary=regular_file(project/'runtime-native.bin',project,NATIVE_BINARY_BYTES)
    if binary.stat().st_size!=NATIVE_BINARY_BYTES:raise ValidationError('Actual native GPU binary is incomplete or has trailing frames')
    rows=[];frames=[None,None];images=[[],[]]
    with binary.open('rb') as stream:
        for i,row in enumerate(observed['rows']):
            remaining();case=manifest['cases'][i//2];view=i%2
            if (type(row) is not dict or set(row)!={'name','image','camera_index','engine_frame','vertices','offset','root_world'}
                    or row['name']!=case['name'] or type(row['camera_index']) is not int or row['camera_index']!=view
                    or type(row['vertices']) is not int or row['vertices']!=14517 or type(row['offset']) is not int or row['offset']!=i*RECORD_BYTES
                    or type(row['engine_frame']) is not int or (frames[view] is not None and row['engine_frame']!=frames[view]+1)
                    or row['image']!='runtime-renders/'+str(i).zfill(3)+'.png'):
                raise ValidationError('Runtime case/camera/frame coverage or binary offsets differ')
            frames[view]=row['engine_frame']
            positions=source_data[case['positions_offset']:case['positions_offset']+VECTOR_BYTES]
            normals=source_data[case['normals_offset']:case['normals_offset']+VECTOR_BYTES]
            evidence=compare_gpu_record(stream.read(RECORD_BYTES),positions,normals,topology.native_source,row['root_world'])
            image=regular_file(project/row['image'],project,2*1024*1024)
            pixels=png_measurements(image.read_bytes(),include_pixel_hash=True,expected_size=(512,512));images[view].append(pixels['rgba_sha256'])
            rows.append({'name':case['name'],'camera_index':view,'engine_frame':row['engine_frame'],'image_sha256':_digest(image,budget),**evidence})
    if any(values[0]!=values[-1] or len(set(values))<2 for values in images) or images[0][0]==images[1][0]:
        raise ValidationError('Actual renders did not return to neutral, change with deformation, or distinguish cameras')
    unchanged()
    if tree_hashes(project,budget)!=sealed:raise ProjectStorageError('Saved Unity project changed during graphical readback validation')
    maximum_position=max(v['maximum_source_position_error_m'] for v in rows);maximum_angle=max(v['maximum_normal_angle_deg'] for v in rows)
    receipt_data={'schema_version':1,'policy':'UCC_UNITY_RUNTIME_ADMISSION_V1','request_sha256':request.sha256,
        'source_verification_sha256':source.verification_sha256,'native_import_receipt_sha256':engine.receipt_sha256,
        'source_manifest_sha256':plan['source_manifest_sha256'],'native_observation_sha256':_digest(project/'runtime-observation.json',budget),
        'native_binary_sha256':_digest(binary,budget),'saved_files':sealed,'rows':rows,'case_count':CASES,'cameras':2,
        'maximum_source_position_error_m':maximum_position,'maximum_normal_angle_deg':maximum_angle,'native_position_bytes_exact':True,
        'source_runtime_vectors_supplied_to_unity':False,'private_runtime_diagnostics_verified':True,'animation_clips_verified':False,
        'export_published':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    path=work/'runtime-admission.json';path.write_bytes(canonical_bytes(receipt_data))
    return VerifiedUnityRuntime(project,request.sha256,_digest(path,budget),maximum_position,maximum_angle)
