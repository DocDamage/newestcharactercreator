"""Fresh source-bound interaction reference job; no cached research inputs."""
from dataclasses import dataclass
import math
from pathlib import Path
import struct
from threading import Event
import time
from uuid import UUID

from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import canonical_bytes,_hash
from ucc.export.godot_native_recipe import INPUTS,REFERENCES,validate_native_recipe,POLICY as SOURCE_POLICY
from ucc.export.godot_native_samples import POLICY,OPERATION,OUTPUTS,REFERENCE_BYTES,validate_sample_report
from ucc.export.godot_runtime_contract import NativeRuntimeRequest,FILES
from ucc.export.godot_runtime_data import validate_runtime_files
from .godot_candidate_inputs import regular_file,read_json,project_sources,identity,check_cancel
from .godot_native_producer import ProducedNativeRuntimeInputs,_report
from .godot_runtime_bundle import PrivateNativeRuntimeInputs
from .expression_storage import safe_directory
from .master_preview import _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner,WorkerFailure
from .worker_resources import worker_dependency_files


@dataclass(frozen=True,slots=True)
class NativeInteractionReferences:
    directory: Path
    job_id: str
    request_sha256: str
    report_sha256: str
    production_receipt_sha256: str


def validate_reference_stream(path: Path,*,normal: bool,check) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=REFERENCE_BYTES:
        raise ValidationError('Native reference stream is missing, redirected or incomplete')
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):
            check()
            if len(block)%16:raise ValidationError('Native reference stream has a partial record')
            for x,y,z,w in struct.iter_unpack('<4f',block):
                if (not all(math.isfinite(v) for v in (x,y,z,w)) or max(abs(x),abs(y),abs(z))>100
                        or w!=(0. if normal else 1.) or normal and abs(x*x+y*y+z*z-1.)>2e-5):
                    raise ValidationError('Native reference stream contains invalid positions/normals')


def sample_native_runtime_interactions(store: ProjectStore,runner: BlenderJobRunner,*,
        produced: ProducedNativeRuntimeInputs,source_fbx: Path,authorized_source_root: Path,
        cancel: Event | None=None,timeout_s: float=1200) -> NativeInteractionReferences:
    if (not isinstance(produced,ProducedNativeRuntimeInputs) or not isinstance(produced.bundle,PrivateNativeRuntimeInputs)
            or not isinstance(produced.bundle.directory,Path) or not isinstance(produced.production_receipt,Path)
            or not _hash(produced.bundle.request_sha256) or not _hash(produced.bundle.validation_sha256)
            or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600):
        raise ValidationError('Native sampling needs a produced source and bounded total deadline')
    try:
        for value in (produced.stage_job_id,produced.reopen_job_id):
            if type(value) is not str or str(UUID(value))!=value:raise ValueError('Noncanonical source job')
    except (ValueError,TypeError,AttributeError) as error:raise ValidationError('Native sampling needs canonical source job identities') from error
    start=time.monotonic()
    def remaining() -> float:
        check_cancel(cancel);value=timeout_s-(time.monotonic()-start)
        if value<.05:raise WorkerFailure('Native interaction sampling exceeded its total deadline')
        return value
    def check() -> None:remaining()
    check();store._check_safety();project=store.load();project_sha=_digest(store.file,cancel)
    jobs=safe_directory(store,'.ucc-jobs',create=False)
    if Path(runner.jobs_root)!=jobs:raise ValidationError('Native sampling runner belongs to another project')
    bundle=produced.bundle.directory
    candidates=safe_directory(store,'.ucc-candidates','godot-runtime-inputs',create=False)
    if bundle.parent!=candidates or bundle.is_symlink() or bundle.resolve()!=bundle:raise ProjectStorageError('Native sampling bundle was redirected')
    request=NativeRuntimeRequest.from_bytes(regular_file(bundle/'request.json',bundle,256*1024).read_bytes())
    if (request.sha256!=produced.bundle.request_sha256 or project.project_id!=request.project_id or project.revision!=request.revision
            or project.master_blend!='master/versions/'+request.master_sha256+'.blend' or project_sha!=request.project_file_sha256):
        raise ProjectConflict('Native sample request differs from the saved character/bundle')
    validate_runtime_files(bundle,request,check)
    receipt_path=regular_file(produced.production_receipt,jobs,256*1024);production=read_json(receipt_path,256*1024);production_sha=_digest(receipt_path,cancel)
    expected_receipt={'schema_version','policy','status','request_sha256','recipe_sha256','stage_job_id','reopen_job_id',
        'native_stage_sha256','native_verification_sha256','frames_verified','runtime_execution_verified','engine_import_verified','visual_quality_approved','distribution_license_review_complete'}
    if (set(production)!=expected_receipt or type(production.get('schema_version')) is not int or production['schema_version']!=1
            or production.get('policy')!=SOURCE_POLICY or production.get('status')!='SOURCE_AND_FRESH_REOPEN_VERIFIED'
            or production.get('request_sha256')!=request.sha256 or production.get('stage_job_id')!=produced.stage_job_id
            or production.get('reopen_job_id')!=produced.reopen_job_id or type(production.get('frames_verified')) is not int or production['frames_verified']!=300
            or any(production.get(k) is not False for k in ('runtime_execution_verified','engine_import_verified','visual_quality_approved','distribution_license_review_complete'))):
        raise ValidationError('Native production receipt changed its closed source coverage')
    reopened=jobs/produced.reopen_job_id
    recipe_path=regular_file(reopened/'native_recipe.json',reopened,256*1024)
    recipe=validate_native_recipe(read_json(recipe_path,256*1024))
    if _digest(recipe_path,cancel)!=production['recipe_sha256'] or recipe['source_bindings']!=dict(request.source_bindings):
        raise ValidationError('Native source recipe belongs to another produced request')
    verified=_report(reopened,'native_verification.json',production['native_verification_sha256'],production['recipe_sha256'],
        'FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED',check)
    if verified['native_stage_sha256']!=production['native_stage_sha256']:raise ValidationError('Native verification lineage changed')
    sources=project_sources(store,project,cancel);motion=recipe['motion_asset_id']
    sources[motion]=regular_file(Path(source_fbx),Path(authorized_source_root),256*1024*1024)
    if {name:_digest(path,cancel) for name,path in sources.items()}!=dict(request.source_bindings):
        raise ValidationError('Current original sources differ from the produced bundle')
    for permission in request.permissions:permission.require_godot()
    staged={name:reopened/name for name in FILES|REFERENCES|set(INPUTS)|{'native_recipe.json','native_verification.json'}}
    staged['runtime_request.json']=bundle/'request.json';staged['native_production_receipt.json']=receipt_path
    expected={path:_digest(regular_file(path,reopened,512*1024*1024),cancel) for path in staged.values() if path.is_relative_to(reopened)}
    expected.update({path:_digest(path,cancel) for path in [store.file,*sources.values(),receipt_path,bundle/'request.json']})
    for name,sha in request.files:
        expected[bundle/name]=sha
        if _digest(reopened/name,cancel)!=sha:raise ValidationError('Produced source/bundle bytes diverged')
    dependencies={Path(runner.blender_exe),*worker_dependency_files(Path(runner.worker_script)),*Path(__file__).resolve().parents[1].rglob('*.py')}
    for path in dependencies:
        # Empty __init__.py files are valid application dependencies, not
        # empty model/reference inputs. Preserve their identity/hash watches.
        if (path.is_symlink() or not path.is_file() or path.resolve()!=path
                or path.parent.resolve()!=path.parent or path.stat().st_size>512*1024*1024):
            raise ProjectStorageError('Native sampler dependency is missing, redirected or oversized')
        expected[path]=_digest(path,cancel)
    identities={path:identity(path) for path in expected}
    def unchanged() -> None:
        check();current=store.load()
        if current.project_id!=request.project_id or current.revision!=request.revision or _digest(store.file,cancel)!=project_sha:
            raise ProjectConflict('Saved character changed during native interaction sampling')
        for path,sha in expected.items():
            check()
            if path.is_symlink() or not path.is_file() or identity(path)!=identities[path] or path.resolve()!=path or _digest(path,cancel)!=sha:
                raise ProjectStorageError('Native sample source/dependency changed')
    unchanged()
    options={key:_digest(staged[name],cancel) for name,key in INPUTS.items()}
    options.update(native_recipe_sha256=production['recipe_sha256'],native_stage_sha256=production['native_stage_sha256'],
        native_verification_sha256=production['native_verification_sha256'],runtime_request_sha256=request.sha256,production_receipt_sha256=production_sha)
    job=JobRequest.new(OPERATION,input_project='candidate.blend',options=options)
    result,folder=runner.run(job,staged_inputs=staged,timeout_s=remaining(),cancel=cancel);unchanged()
    report_path=regular_file(folder/'native_samples.json',folder,4*1024*1024)
    report_sha=_digest(report_path,cancel)
    if result.details!={'policy':POLICY,'status':'FRESH_NATIVE_INTERACTION_REFERENCES_MEASURED','native_samples_sha256':report_sha,
                       'sample_count':2697,'engine_import_verified':False}:raise ValidationError('Native sampler result differs from its bound references')
    report=validate_sample_report(read_json(report_path,4*1024*1024),request_sha256=request.sha256,production_sha256=production_sha,
        recipe_sha256=production['recipe_sha256'],verification_sha256=production['native_verification_sha256'])
    for name in OUTPUTS:
        path=regular_file(folder/name,folder,REFERENCE_BYTES)
        if _digest(path,cancel)!=report['files'][name]['sha256']:raise ValidationError('Native sampled reference hash differs')
        validate_reference_stream(path,normal=name=='expected_normals_vec4.f32',check=check)
    unchanged()
    (folder/'sample_acceptance.json').write_bytes(canonical_bytes({'schema_version':1,'policy':POLICY,
        'request_sha256':request.sha256,'report_sha256':report_sha,'production_receipt_sha256':production_sha,
        'samples':2697,'reference_streams_validated':True,'engine_import_verified':False,'visual_quality_approved':False}))
    return NativeInteractionReferences(folder,job.job_id,request.sha256,report_sha,production_sha)
