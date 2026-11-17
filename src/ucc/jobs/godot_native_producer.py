"""Normal source-bound Blender/native runtime production and fresh reopening.

The result remains a private input bundle. Actual engine execution, materials,
visual approval and distribution require independent gates.
"""
from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event
import time
from uuid import uuid4

from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import EngineInputPermission,canonical_bytes,_hash
from ucc.export.godot_native_recipe import INPUTS,REFERENCES,POLICY
from ucc.export.godot_runtime_contract import NativeRuntimeRequest,FILES,CODE_FILES
from .expression_storage import safe_directory
from .godot_candidate_inputs import read_json,regular_file,check_cancel
from .godot_native_inputs import admit_native_production
from .godot_runtime_bundle import PrivateNativeRuntimeInputs,retain_private_native_runtime_inputs
from .master_preview import _digest
from .native_body import NativeBodyPreview
from .native_evidence import read_native_timeline
from .native_skin_evidence import validate_reopen_report
from .protocol import JobRequest
from .runner import BlenderJobRunner,WorkerFailure


@dataclass(frozen=True,slots=True)
class ProducedNativeRuntimeInputs:
    bundle: PrivateNativeRuntimeInputs
    production_receipt: Path
    stage_job_id: str
    reopen_job_id: str


def _report(folder: Path,filename: str,expected_sha: str,request_sha: str,status: str,check,
            *, expected_policy: str=POLICY) -> dict:
    from ucc.export.godot_registered_native_recipe import POLICY as REGISTERED_POLICY
    if expected_policy not in {POLICY, REGISTERED_POLICY}:
        raise ValidationError('Unsupported native production report policy')
    path=regular_file(folder/filename,folder,4*1024*1024)
    if not _hash(expected_sha) or _digest(path,None)!=expected_sha:raise ValidationError('Native producer report SHA differs')
    report=read_json(path,4*1024*1024)
    fields={'schema_version','policy','status','recipe_sha256','master_state_sha256','native_reopen','frames',
        'frame_count','morphs','blender_version','engine_import_verified','visual_quality_approved','distribution_license_review_complete',
        'raw_copy_weight_policy','max_serialized_weight_error'}
    fields|=({'source_names','fps','numpy_version','files','export_optimize_animation_size'} if filename=='native_stage.json'
        else {'native_stage_sha256','saved_output_rebuilt_or_repaired'})
    morphs=report.get('morphs')
    if (set(report)!=fields or type(report.get('schema_version')) is not int or report['schema_version']!=1 or report.get('policy')!=expected_policy or report.get('status')!=status
            or report.get('recipe_sha256')!=request_sha or report.get('frame_count')!=300
            or type(report.get('frame_count')) is not int or not _hash(report.get('master_state_sha256'))
            or report.get('raw_copy_weight_policy')!='EXACT_ORIGINAL_SOURCE_WEIGHTS_V1'
            or type(report.get('max_serialized_weight_error')) not in (int,float)
            or not math.isfinite(report['max_serialized_weight_error']) or not 0<=report['max_serialized_weight_error']<=1e-6
            or any(report.get(k) is not False for k in ('engine_import_verified','visual_quality_approved','distribution_license_review_complete'))
            or type(report.get('frames')) is not list or len(report['frames'])!=300
            or type(morphs) is not dict or set(morphs)!={'canonical_morphs_verified','maximum_morph_position_error_m'}
            or type(morphs['canonical_morphs_verified']) is not int or morphs['canonical_morphs_verified']!=12
            or type(morphs['maximum_morph_position_error_m']) not in (int,float)
            or not math.isfinite(morphs['maximum_morph_position_error_m']) or not 0<=morphs['maximum_morph_position_error_m']<=1e-6):
        raise ValidationError('Native production report lacks complete closed source coverage')
    expected_fields=({'frame','raw_error_m','reconstruction_error_m'} if filename=='native_stage.json' else
        {'frame','source_error_m','normal_vector_error','raw_error_m','reconstruction_error_m','bone_world_error'})
    for index,row in enumerate(report['frames'],1):
        check()
        if (type(row) is not dict or set(row)!=expected_fields or type(row['frame']) is not int or row['frame']!=index
                or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e-6 for k,v in row.items() if k!='frame')):
            raise ValidationError('Native producer frame errors exceed unchanged source limits')
    return report


def produce_private_native_runtime_inputs(store: ProjectStore,runner: BlenderJobRunner,*,
        native_preview: NativeBodyPreview,source_fbx: Path,authorized_source_root: Path,
        authorized_native_root: Path,runtime_directory: Path,motion_asset_id: str,
        permissions: tuple[EngineInputPermission,...],requested_capability: str,
        cancel: Event | None=None,timeout_s: float=1800) -> ProducedNativeRuntimeInputs:
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Native producer requires a bounded total deadline')
    start=time.monotonic()
    def remaining() -> float:
        check_cancel(cancel);value=timeout_s-(time.monotonic()-start)
        if value<.05:raise WorkerFailure('Native runtime producer exceeded its total deadline')
        return value
    def check() -> None:remaining()
    jobs=safe_directory(store,'.ucc-jobs',create=True)
    if Path(runner.jobs_root)!=jobs:raise ValidationError('Native producer runner must use this project jobs directory')
    selected=admit_native_production(store,runner,native_preview,source_fbx=Path(source_fbx),
        authorized_source_root=Path(authorized_source_root),authorized_native_root=Path(authorized_native_root),
        runtime_directory=Path(runtime_directory),motion_asset_id=motion_asset_id,permissions=permissions,
        capability=requested_capability,cancel=cancel,check=check)
    unchanged=selected['unchanged'];project=selected['project'];bindings=selected['bindings'];evidence=selected['evidence_bindings']
    snapshots=[]
    for _ in range(2):
        unchanged();job=JobRequest.new('inspect_fbx_animation',options={'source_sha256':bindings[motion_asset_id]})
        result,folder=runner.run(job,staged_inputs={'source.fbx':selected['source']},timeout_s=remaining(),cancel=cancel)
        unchanged();source,snapshot=read_snapshot(folder,result.details,bindings[motion_asset_id],cancel_check=check)
        if result.details['snapshot']['sha256']!=evidence['source_snapshot'] or _digest(folder/'source.fbx',cancel)!=bindings[motion_asset_id]:
            raise ValidationError('Fresh real FBX intake differs from the bound native preview snapshot')
        snapshots.append((source,snapshot))
    if snapshots[0][0]!=snapshots[1][0]:raise ValidationError('Independent fresh FBX intakes disagree')
    source=snapshots[0][0]
    profile,mapping_sha=read_native_profile(selected['evidence']['native_mapping'],bindings[motion_asset_id],evidence['source_snapshot'],bindings['master'])
    if mapping_sha!=evidence['native_mapping']:raise ValidationError('Native mapping changed during intake')
    native_bindings={'master_sha256':bindings['master'],'source_sha256':bindings[motion_asset_id],
        'snapshot_sha256':evidence['source_snapshot'],'mapping_sha256':evidence['native_mapping']}
    data,_=read_native_timeline(selected['evidence']['native_timeline'].parent,native_preview.worker_report,source,profile,native_bindings,cancel_check=check)
    if canonical_bytes(data)!=canonical_bytes(native_preview.evidence):raise ValidationError('Native preview object differs from its independently checked timeline')
    reopen_bindings={**native_bindings,'review_sha256':evidence['native_review'],'timeline_sha256':evidence['native_timeline']}
    validate_reopen_report(native_preview.reopen_evidence,reopen_bindings,data)
    prepared=jobs/('native-runtime-producer-'+str(uuid4()));prepared.mkdir(exist_ok=False)
    recipe_path=prepared/'native_recipe.json';recipe_path.write_bytes(canonical_bytes(selected['recipe']))
    recipe_sha=_digest(recipe_path,cancel)
    staged={'candidate.blend':selected['sources']['master'],'source.fbx':selected['source'],
        'review_motion.blend':selected['evidence']['native_review'],'target_timeline.json':selected['evidence']['native_timeline'],
        'source_snapshot.json':snapshots[0][1],'native_mapping.json':selected['evidence']['native_mapping'],
        'native_recipe.json':recipe_path,**selected['implementation']}
    options={**reopen_bindings,'native_recipe_sha256':recipe_sha}
    unchanged();stage_job=JobRequest.new('stage_native_godot_runtime',input_project='candidate.blend',options=options)
    stage,folder=runner.run(stage_job,staged_inputs=staged,timeout_s=remaining(),cancel=cancel);unchanged()
    stage_sha=stage.details.get('native_stage_sha256')
    report=_report(folder,'native_stage.json',stage_sha,recipe_sha,'REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED',check)
    if set(report.get('files',{}))!=FILES | (REFERENCES-{'native_stage.json'}):raise ValidationError('Native stage output closure differs')
    validate_reopen_report(report['native_reopen'],reopen_bindings,data)
    for name,record in report['files'].items():
        check();regular_file(folder/name,folder,512*1024*1024)
        if type(record) is not dict or set(record)!={'sha256','bytes'} or type(record['bytes']) is not int or record['bytes']!=(folder/name).stat().st_size or record['sha256']!=_digest(folder/name,cancel):
            raise ValidationError('Native stage output binding changed')
    inputs={name:folder/name for name in set(staged)|set(report['files'])|{'native_stage.json'}}
    verify_job=JobRequest.new('verify_native_godot_runtime',input_project='candidate.blend',options={**options,'native_stage_sha256':stage_sha})
    verified,reopened=runner.run(verify_job,staged_inputs=inputs,timeout_s=remaining(),cancel=cancel);unchanged()
    verified_sha=verified.details.get('native_verification_sha256')
    fresh=_report(reopened,'native_verification.json',verified_sha,recipe_sha,'FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED',check)
    validate_reopen_report(fresh['native_reopen'],reopen_bindings,data)
    if fresh.get('native_stage_sha256')!=stage_sha or fresh.get('saved_output_rebuilt_or_repaired') is not False or fresh.get('master_state_sha256')!=report['master_state_sha256']:
        raise ValidationError('Native fresh reopening changed stage lineage or repaired saved output')
    for name,record in report['files'].items():
        check()
        if _digest(reopened/name,cancel)!=record['sha256']:raise ValidationError('Fresh native output bytes differ from staging')
    request=NativeRuntimeRequest(str(uuid4()),project.project_id,project.revision,selected['project_sha'],bindings['master'],
        tuple((name,_digest(reopened/name,cancel)) for name in sorted(FILES)),tuple(bindings.items()),
        (('native_review',evidence['native_review']),('native_timeline',evidence['native_timeline'])),permissions,requested_capability)
    (prepared/'runtime_request.json').write_bytes(canonical_bytes(request.to_dict()));unchanged()
    receipt=prepared/'native_production_receipt.json'
    receipt.write_bytes(canonical_bytes({'schema_version':1,'policy':POLICY,'status':'SOURCE_AND_FRESH_REOPEN_VERIFIED',
        'request_sha256':request.sha256,
        'recipe_sha256':recipe_sha,'stage_job_id':stage_job.job_id,'reopen_job_id':verify_job.job_id,
        'native_stage_sha256':stage_sha,'native_verification_sha256':verified_sha,'frames_verified':300,
        'runtime_execution_verified':False,'engine_import_verified':False,
        'visual_quality_approved':False,'distribution_license_review_complete':False}))
    bundle=retain_private_native_runtime_inputs(store,request,candidate_folder=reopened,
        motion_sources={motion_asset_id:reopened/'source.fbx'},native_evidence={'native_review':reopened/'review_motion.blend','native_timeline':reopened/'target_timeline.json'},
        cancel=cancel,timeout_s=remaining(),source_guard=unchanged)
    return ProducedNativeRuntimeInputs(bundle,receipt,stage_job.job_id,verify_job.job_id)
