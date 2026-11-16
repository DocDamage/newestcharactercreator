"""Bounded normal target coordination for fresh native interaction references.

Success retains private diagnostic evidence, not a shipping/artist-approved
asset. Runtime implementation code remains an explicitly selected bundle input.
"""
from dataclasses import dataclass
import math,os,shutil,tempfile,time
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ValidationError,ProjectStorageError,ProjectConflict
from ucc.core.storage import ProjectStore,_lock
from ucc.export.godot_candidate_contract import canonical_bytes,_hash
from ucc.export.godot_native_samples import validate_sample_report,OUTPUTS,REFERENCE_BYTES,COUNT
from ucc.export.godot_runtime_contract import NativeRuntimeRequest,FILES
from ucc.export.godot_runtime_data import validate_runtime_files
from .godot_native_producer import ProducedNativeRuntimeInputs
from .godot_runtime_bundle import PrivateNativeRuntimeInputs
from .godot_native_sampling import NativeInteractionReferences
from .godot_native_target_evidence import verify_native_target_evidence
from .godot_candidate_inputs import regular_file,read_json,project_sources,identity,check_cancel
from .expression_storage import safe_directory
from .master_preview import _digest
from .runner import run_process,WorkerFailure
from .worker_resources import bundled_native_adapter_path

SCRIPTS=frozenset({'validate.gd','configure.gd','clay.gdshader','project.godot'})


@dataclass(frozen=True,slots=True)
class VerifiedPrivateNativeTarget:
    directory: Path
    request_sha256: str
    source_report_sha256: str
    verification_sha256: str

    @property
    def engine_import_verified(self) -> bool:return False


def verify_sampled_native_runtime(store: ProjectStore,*,produced: ProducedNativeRuntimeInputs,
        references: NativeInteractionReferences,source_fbx: Path,authorized_source_root: Path,
        godot_exe: Path,adapter_directory: Path | None=None,cancel: Event | None=None,timeout_s: float=1800) -> VerifiedPrivateNativeTarget:
    if (not isinstance(produced,ProducedNativeRuntimeInputs) or not isinstance(produced.bundle,PrivateNativeRuntimeInputs)
            or not isinstance(produced.bundle.directory,Path) or not isinstance(produced.production_receipt,Path)
            or not isinstance(references,NativeInteractionReferences) or not isinstance(references.directory,Path)
            or any(not _hash(value) for value in (produced.bundle.request_sha256,references.request_sha256,references.report_sha256,references.production_receipt_sha256))
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600):
        raise ValidationError('Native target coordination needs produced inputs, fresh references and a total deadline')
    started=time.monotonic()
    def remaining() -> float:
        check_cancel(cancel);value=timeout_s-(time.monotonic()-started)
        if value<.05:raise WorkerFailure('Native target coordination exceeded its total deadline')
        return value
    def check() -> None:remaining()
    check();store._check_safety();project=store.load();project_sha=_digest(store.file,cancel)
    jobs=safe_directory(store,'.ucc-jobs',create=False);candidates=safe_directory(store,'.ucc-candidates','godot-runtime-inputs',create=False)
    bundle=produced.bundle.directory;source=references.directory
    if (bundle.parent!=candidates or bundle.resolve()!=bundle or bundle.is_symlink()
            or source.parent!=jobs or source.name!=references.job_id or source.is_symlink() or source.resolve()!=source):
        raise ProjectStorageError('Native target inputs are outside their canonical private project directories')
    request_path=regular_file(bundle/'request.json',bundle,256*1024);request=NativeRuntimeRequest.from_bytes(request_path.read_bytes())
    if (request.sha256!=produced.bundle.request_sha256 or request.sha256!=references.request_sha256
            or request.project_id!=project.project_id or request.revision!=project.revision or request.project_file_sha256!=project_sha
            or project.master_blend!='master/versions/'+request.master_sha256+'.blend'):
        raise ProjectConflict('Native target input differs from the saved character/source request')
    validate_runtime_files(bundle,request,check)
    production_path=regular_file(produced.production_receipt,jobs,256*1024);production=read_json(production_path,256*1024)
    if (_digest(production_path,cancel)!=references.production_receipt_sha256 or production.get('request_sha256')!=request.sha256
            or production.get('status')!='SOURCE_AND_FRESH_REOPEN_VERIFIED' or production.get('stage_job_id')!=produced.stage_job_id
            or production.get('reopen_job_id')!=produced.reopen_job_id or production.get('frames_verified')!=300
            or any(name not in production for name in ('recipe_sha256','native_verification_sha256'))):
        raise ValidationError('Native target production receipt changed')
    report_path=regular_file(source/'native_samples.json',source,4*1024*1024)
    if _digest(report_path,cancel)!=references.report_sha256:raise ValidationError('Fresh native sample report changed')
    report=validate_sample_report(read_json(report_path,4*1024*1024),request_sha256=request.sha256,
        production_sha256=references.production_receipt_sha256,recipe_sha256=production['recipe_sha256'],verification_sha256=production['native_verification_sha256'])
    accepted=read_json(regular_file(source/'sample_acceptance.json',source,256*1024),256*1024)
    expected_acceptance={'schema_version':1,'policy':report['policy'],'request_sha256':request.sha256,'report_sha256':references.report_sha256,
        'production_receipt_sha256':references.production_receipt_sha256,'samples':COUNT,'reference_streams_validated':True,
        'engine_import_verified':False,'visual_quality_approved':False}
    if canonical_bytes(accepted)!=canonical_bytes(expected_acceptance):raise ValidationError('Fresh reference acceptance differs from its complete source report')
    sources=dict(project_sources(store,project,cancel));motion=[name for name,_ in request.source_bindings if name.startswith('motion:')]
    sources[motion[0]]=regular_file(Path(source_fbx),Path(authorized_source_root),256*1024*1024)
    if {name:_digest(path,cancel) for name,path in sources.items()}!=dict(request.source_bindings):
        raise ValidationError('Native target original source closure changed')
    for permission in request.permissions:permission.require_godot()
    exe=regular_file(Path(godot_exe),Path(godot_exe).parent,512*1024*1024)
    adapters=bundled_native_adapter_path() if adapter_directory is None else Path(adapter_directory)
    scripts={name:regular_file(adapters/name,adapters,256*1024) for name in SCRIPTS}
    inputs={name:bundle/name for name in FILES};inputs['request.json']=request_path
    inputs['native_samples.json']=report_path;inputs['native_production_receipt.json']=production_path
    for name in OUTPUTS:
        path=regular_file(source/name,source,REFERENCE_BYTES)
        if path.stat().st_size!=REFERENCE_BYTES or _digest(path,cancel)!=report['files'][name]['sha256']:
            raise ValidationError('Fresh native reference input changed')
        inputs[name]=path
    watched={store.file,*sources.values(),*inputs.values(),*scripts.values(),exe}
    watched.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    hashes={path:_digest(path,cancel) for path in watched};identities={path:identity(path) for path in watched}
    def unchanged() -> None:
        check();current=store.load()
        if current.project_id!=request.project_id or current.revision!=request.revision or _digest(store.file,cancel)!=project_sha:
            raise ProjectConflict('Saved character changed during native target verification')
        if dict(project_sources(store,current,cancel))!={name:path for name,path in sources.items() if name!=motion[0]}:
            raise ProjectStorageError('Registered native target source selection changed')
        for path,sha in hashes.items():
            check()
            if path.is_symlink() or not path.is_file() or path.resolve()!=path or identity(path)!=identities[path] or _digest(path,cancel)!=sha:
                raise ProjectStorageError('Native target source, executable or adapter changed')
    unchanged();job_id=str(uuid4());work=jobs/('native-target-'+job_id)
    work.mkdir(exist_ok=False);engine=work/'engine';engine.mkdir();destination=None;commands=[]
    def journal(state: str,**details) -> None:
        target=work/'job_status.json'
        if target.is_symlink():raise ProjectStorageError('Native target journal redirected')
        fd,name=tempfile.mkstemp(prefix='status-',suffix='.tmp',dir=work);temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(canonical_bytes({'schema_version':1,'state':state,'job_id':job_id,'request_sha256':request.sha256,
                    'source_report_sha256':references.report_sha256,'commands':commands,'engine_import_verified':False,**details}))
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    def run(label: str,args: list[str]) -> None:
        unchanged();command=[str(exe),'--path',str(engine),*args]
        outcome=run_process(command,work/label,timeout_s=remaining(),cancel=cancel)
        commands.append({'phase':label,'command':command,'return_code':outcome.return_code,'cancelled':outcome.cancelled,
            'timed_out':outcome.timed_out,'elapsed_seconds':outcome.elapsed_seconds})
        journal('RUNNING')
        if outcome.return_code!=0 or outcome.cancelled or outcome.timed_out:raise WorkerFailure('Native Godot '+label+' failed; logs: '+str(work/label))
        unchanged()
        for name,path in {**inputs,**scripts}.items():
            if _digest(engine/name,cancel)!=hashes[path]:raise ProjectStorageError('Native target staged input changed')
    try:
        journal('STAGING')
        for name,path in {**inputs,**scripts}.items():
            check();shutil.copy2(path,engine/name)
            if _digest(engine/name,cancel)!=hashes[path]:raise ProjectStorageError('Native target input changed during copy')
        spec={'vertices':13380,'corners':53512,'cases':report['cases'],'views':report['views'],'race_mix':report['race_mix'],
            'roles':report['roles'],'plan_sha256':dict(request.files)['skin_plan.json'],'bundle_request_sha256':request.sha256,
            'source_report_sha256':references.report_sha256,'files':{name:hashes[path] for name,path in {**inputs,**scripts}.items()}}
        (engine/'spec.json').write_bytes(canonical_bytes(spec));spec_sha=_digest(engine/'spec.json',cancel)
        vulkan=['--rendering-method','mobile','--rendering-driver','vulkan','--position','-32000,-32000']
        run('initial-import',vulkan+['--editor','--import'])
        run('configure-import',['--headless','--script','res://configure.gd'])
        run('configured-import',vulkan+['--editor','--import'])
        run('actual-verification',vulkan+['--script','res://validate.gd'])
        settings=(engine/'character.glb.import').read_text()
        if 'animation/fps=30.0' not in settings or '"optimizer/enabled": false' not in settings or '"compression/enabled": false' not in settings:
            raise ValidationError('Native target import changed required clock/optimization settings')
        observed=verify_native_target_evidence(engine,report,check=check)
        if _digest(engine/'spec.json',cancel)!=spec_sha:raise ProjectStorageError('Native target specification changed')
        (engine/'independent_verification.json').write_bytes(canonical_bytes(observed));verified_sha=_digest(engine/'independent_verification.json',cancel)
        unchanged();root=safe_directory(store,'.ucc-candidates','godot-native-verification',create=True);destination=root/job_id
        with _lock(store.root/'.project.ucc.lock',timeout_s=min(3.,remaining())):
            unchanged();check()
            if destination.exists() or destination.is_symlink():raise ProjectStorageError('Native target candidate identity already exists')
            os.rename(engine,destination)
        check();journal('PRIVATE_NATIVE_TARGET_VERIFIED',candidate=str(destination),verification_sha256=verified_sha)
        return VerifiedPrivateNativeTarget(destination,request.sha256,references.report_sha256,verified_sha)
    except BaseException as error:
        if destination is not None and not engine.exists() and destination.is_dir() and not destination.is_symlink():
            try:os.rename(destination,engine)
            except OSError as rollback_error:error.add_note('Native target rollback failed: '+str(rollback_error))
        try:journal('FAILED',error_type=type(error).__name__,error=str(error)[:1500])
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Native target journal failed: '+str(journal_error))
        raise
