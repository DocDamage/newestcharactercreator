"""Prepare and freshly reopen private Godot source from a saved target binding.

This API executes Blender only. Caller-selected runtime code is copied as data,
never executed or distributed. No engine project or candidate is published.
"""
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_native_recipe import REFERENCES
from ucc.export.godot_registered_native_recipe import POLICY
from ucc.export.godot_runtime_contract import FILES, NativeRuntimeRequest
from ucc.export.godot_runtime_data import validate_runtime_files
from .expression_storage import safe_directory
from .godot_candidate_inputs import regular_file, identity
from .godot_native_producer import _report
from .godot_registered_native_inputs import admit_registered_native_production
from .master_preview import _digest
from .native_evidence import read_native_timeline
from .native_skin_evidence import validate_reopen_report
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .target_action_evidence import _worker
from .target_action_context import protected, operation_budget

RECEIPT_POLICY = 'UCC_REGISTERED_NATIVE_SOURCE_PREPARATION_V1'
OUTPUTS = FILES | (REFERENCES - {'native_stage.json'})


@dataclass(frozen=True, slots=True)
class PreparedRegisteredNativeSource:
    workdir: Path
    directory: Path
    production_receipt: Path
    recipe_sha256: str
    runtime_request_sha256: str
    target_action_binding_sha256: str
    stage_job_id: str
    reopen_job_id: str


def _outputs(folder, records, check, cancel):
    if type(records) is not dict or set(records) != OUTPUTS:
        raise ValidationError('Registered native source output closure differs')
    for name, record in records.items():
        check()
        path = regular_file(folder/name, folder, 512*1024*1024)
        if (type(record) is not dict or set(record) != {'sha256', 'bytes'}
                or type(record['bytes']) is not int or record['bytes'] != path.stat().st_size
                or record['sha256'] != _digest(path, cancel)):
            raise ValidationError('Registered native source output bytes changed: '+name)


def _result_report(result, folder, recipe_sha, status, *, stage, check):
    field = 'native_stage_sha256' if stage else 'native_verification_sha256'
    details = result.details
    if type(details) is not dict or field not in details:
        raise ValidationError('Registered native source worker omitted its report')
    expected = {'policy': POLICY, 'status': status, field: details[field],
                'frame_count': 300, 'engine_import_verified': False}
    if canonical_bytes(details) != canonical_bytes(expected):
        raise ValidationError('Registered native worker result changed its closed profile')
    name = 'native_stage.json' if stage else 'native_verification.json'
    report = _report(folder, name, details[field], recipe_sha, status, check,
                     expected_policy=POLICY)
    if stage and (type(report['fps']) is not int or report['fps'] != 30
            or report['export_optimize_animation_size'] is not False):
        raise ValidationError('Registered native source changed the exact unoptimized clock')
    return report, details[field]


def _descriptor_stamp(stream):
    value = os.fstat(stream.fileno())
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _finish_owned_receipt(receipt, expected, finalize):
    """Invalidate only the held exact file when final admission fails.

    A same-name replacement is never reopened for mutation. Changed descriptor
    contents are preserved too; cancellation does not skip bounded cleanup.
    """
    with receipt.open('r+b') as stream:
        if (_descriptor_stamp(stream) != expected[0]
                or sha256(stream.read(2*1024*1024+1)).hexdigest() != expected[1]
                or _descriptor_stamp(stream) != expected[0]):
            raise ProjectStorageError('Registered native receipt changed before final admission')
        try:
            finalize()
        except BaseException as error:
            try:
                stream.seek(0)
                payload = stream.read(2*1024*1024+1)
                if _descriptor_stamp(stream) == expected[0] and sha256(payload).hexdigest() == expected[1]:
                    failed = canonical_bytes({'schema_version': 1, 'policy': RECEIPT_POLICY,
                        'status': 'PREPARATION_COMPLETION_FAILED',
                        'withdrawn_source_receipt_sha256': expected[1],
                        'error_type': type(error).__name__, 'error': str(error)[:1500],
                        'runtime_execution_verified': False, 'engine_import_verified': False,
                        'runtime_code_provenance_verified': False, 'visual_quality_approved': False,
                        'distribution_license_review_complete': False,
                        'source_redistribution_authorized': False,
                        'cloud_transmission_authorized': False, 'public_export_published': False})
                    stream.seek(0); stream.write(failed); stream.truncate()
                    stream.flush(); os.fsync(stream.fileno())
                else:
                    error.add_note('Private receipt changed externally; foreign bytes preserved')
            except (OSError, ValueError) as invalidation_error:
                error.add_note('Private receipt invalidation unavailable: '+str(invalidation_error))
            raise


def prepare_registered_native_source(store, *, binding_sha256, database_path,
        expected_project_id, expected_revision, expected_master_blend, expected_project_sha256,
        expected_clip_id, expected_source_binding_sha256, expected_catalog_record_sha256,
        runtime_directory, runtime_code_provenance, motion_asset_id, permissions,
        requested_capability, blender_exe, worker_script, cancel: Event | None=None,
        timeout_s: float=1800, progress=None) -> PreparedRegisteredNativeSource:
    """Load the actual retained proof, then run only fresh source stage/reopen.

    All attached animation IDs and catalog policies remain unchanged. Per-source
    engine permissions are distinct from local-preview and code-provenance facts.
    Returned files stay private under .ucc-jobs; they establish no engine result.
    """
    with operation_budget(cancel, timeout_s) as budget:
        return _prepare(store, binding_sha256=binding_sha256, database_path=database_path,
            expected_project_id=expected_project_id, expected_revision=expected_revision,
            expected_master_blend=expected_master_blend, expected_project_sha256=expected_project_sha256,
            expected_clip_id=expected_clip_id, expected_source_binding_sha256=expected_source_binding_sha256,
            expected_catalog_record_sha256=expected_catalog_record_sha256,
            runtime_directory=runtime_directory, runtime_code_provenance=runtime_code_provenance,
            motion_asset_id=motion_asset_id, permissions=permissions,
            requested_capability=requested_capability, blender_exe=blender_exe,
            worker_script=worker_script, cancel=budget.cancel, budget=budget, progress=progress)


def _prepare(store, *, binding_sha256, database_path, expected_project_id,
        expected_revision, expected_master_blend, expected_project_sha256,
        expected_clip_id, expected_source_binding_sha256, expected_catalog_record_sha256,
        runtime_directory, runtime_code_provenance, motion_asset_id, permissions,
        requested_capability, blender_exe, worker_script, cancel, budget, progress):
    check, remaining = budget.check, budget.remaining
    def phase(name):
        check()
        if progress:
            progress(name)
        check()
    check()
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    runner = BlenderJobRunner(Path(blender_exe), jobs, Path(worker_script))
    selected = admit_registered_native_production(store, runner,
        binding_sha256=binding_sha256, database_path=database_path,
        expected_project_id=expected_project_id, expected_revision=expected_revision,
        expected_master_blend=expected_master_blend, expected_project_sha256=expected_project_sha256,
        expected_clip_id=expected_clip_id, expected_source_binding_sha256=expected_source_binding_sha256,
        expected_catalog_record_sha256=expected_catalog_record_sha256,
        runtime_directory=runtime_directory, runtime_code_provenance=Path(runtime_code_provenance),
        motion_asset_id=motion_asset_id, permissions=permissions, capability=requested_capability,
        cancel=cancel, check=check, remaining=remaining, progress=progress)
    unchanged = selected['unchanged']
    project = selected['project']; binding = selected['binding']
    directory = selected['prepared_target'].directory
    bindings = selected['bindings']; evidence = selected['evidence_bindings']
    source_details = _worker(directory, 'source_intake_first',
        binding.producer.source_intake_worker_job_ids[0], 'inspect_fbx_animation',
        {'source_sha256': binding.source.source_sha256}, binding, check, input_project=None)
    source, snapshot = read_snapshot(directory, source_details,
        binding.source.source_sha256, cancel_check=check)
    profile, mapping_sha = read_native_profile(selected['evidence']['native_mapping'],
        binding.source.source_sha256, binding.source.snapshot_sha256, binding.target.master_sha256)
    if mapping_sha != evidence['native_mapping']:
        raise ValidationError('Selected registered native mapping changed')
    native_bindings = {'master_sha256': bindings['master'], 'source_sha256': binding.source.source_sha256,
        'snapshot_sha256': evidence['source_snapshot'], 'mapping_sha256': mapping_sha}
    body_details = _worker(directory, 'body_first', binding.producer.body_worker_job_ids[0],
        'verify_native_fbx_body', {**native_bindings, 'render_private_frames': True}, binding, check)
    timeline, _ = read_native_timeline(directory/'body_first', body_details, source, profile,
        native_bindings, cancel_check=check)
    reopen_bindings = {**native_bindings, 'review_sha256': evidence['native_review'],
                       'timeline_sha256': evidence['native_timeline']}
    unchanged()
    work = jobs/('registered-native-source-'+str(uuid4()))
    work.mkdir(exist_ok=False)
    job_identity, work_identity = identity(jobs), identity(work)
    metadata = {}
    def work_guard():
        check()
        if identity(protected(jobs)) != job_identity or identity(protected(work)) != work_identity:
            raise ProjectStorageError('Registered native preparation directory was replaced')
        names = set()
        with os.scandir(work) as entries:
            for count, entry in enumerate(entries, 1):
                check()
                if count > 5 or entry.name in names or entry.name not in metadata:
                    raise ProjectStorageError('Registered native preparation metadata inventory changed')
                names.add(entry.name)
        if names != set(metadata):
            raise ProjectStorageError('Registered native preparation metadata inventory changed')
        for name, (stamp, digest) in metadata.items():
            path = regular_file(work/name, work, 2*1024*1024)
            if identity(path) != stamp or _digest(path, cancel) != digest:
                raise ProjectStorageError('Registered native preparation metadata changed')
    def write_metadata(name, data):
        work_guard()
        if not 0 < len(data) <= 2*1024*1024:
            raise ValidationError('Registered native metadata exceeds its byte bound')
        path = work/name
        with path.open('xb') as stream:
            stream.write(data)
        regular_file(path, work, 2*1024*1024)
        metadata[name] = (identity(path), _digest(path, cancel))
        work_guard()
    recipe_path = work/'native_recipe.json'
    write_metadata(recipe_path.name, canonical_bytes(selected['recipe']))
    recipe_sha = _digest(recipe_path, cancel)
    with Path(runtime_code_provenance).open('rb') as stream:
        provenance = stream.read(256*1024+1)
    if len(provenance) > 256*1024:
        raise ValidationError('Selected private code provenance metadata grew beyond its bound')
    write_metadata('runtime_code_provenance.json', provenance)
    if _digest(work/'runtime_code_provenance.json', cancel) != selected['recipe']['runtime_code_provenance_sha256']:
        raise ValidationError('Selected private code provenance metadata changed')
    staged = {'candidate.blend': selected['sources']['master'], 'source.fbx': selected['source'],
        'review_motion.blend': selected['evidence']['native_review'],
        'target_timeline.json': selected['evidence']['native_timeline'],
        'source_snapshot.json': snapshot, 'native_mapping.json': selected['evidence']['native_mapping'],
        'native_recipe.json': recipe_path, **selected['implementation']}
    options = {**reopen_bindings, 'native_recipe_sha256': recipe_sha,
               'target_action_binding_sha256': binding_sha256}
    phase('STAGE_REGISTERED_NATIVE_SOURCE'); unchanged(); work_guard()
    stage_job = JobRequest.new('stage_registered_native_godot_runtime',
        input_project='candidate.blend', options=options)
    staged_result, folder = runner.run(stage_job, staged_inputs=staged,
        cancel=cancel, timeout_s=remaining())
    unchanged(); work_guard()
    stage, stage_sha = _result_report(staged_result, folder, recipe_sha,
        'REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED', stage=True, check=check)
    validate_reopen_report(stage['native_reopen'], reopen_bindings, timeline)
    _outputs(folder, stage['files'], check, cancel)
    inputs = {name: folder/name for name in set(staged)|OUTPUTS|{'native_stage.json'}}
    phase('REOPEN_REGISTERED_NATIVE_SOURCE'); unchanged(); work_guard()
    reopen_job = JobRequest.new('verify_registered_native_godot_runtime',
        input_project='candidate.blend', options={**options, 'native_stage_sha256': stage_sha})
    fresh_result, reopened = runner.run(reopen_job, staged_inputs=inputs,
        cancel=cancel, timeout_s=remaining())
    unchanged(); work_guard()
    fresh, fresh_sha = _result_report(fresh_result, reopened, recipe_sha,
        'FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED', stage=False, check=check)
    validate_reopen_report(fresh['native_reopen'], reopen_bindings, timeline)
    if (fresh['native_stage_sha256'] != stage_sha or fresh['saved_output_rebuilt_or_repaired'] is not False
            or fresh['master_state_sha256'] != stage['master_state_sha256']):
        raise ValidationError('Registered native fresh reopening changed source lineage or repaired output')
    _outputs(reopened, stage['files'], check, cancel)
    request = NativeRuntimeRequest(str(uuid4()), project.project_id, project.revision,
        selected['project_sha'], bindings['master'],
        tuple((name, stage['files'][name]['sha256']) for name in sorted(FILES)), tuple(bindings.items()),
        (('native_review', evidence['native_review']), ('native_timeline', evidence['native_timeline'])),
        permissions, requested_capability)
    phase('VALIDATE_PRIVATE_REGISTERED_NATIVE_BYTES'); unchanged()
    validation = validate_runtime_files(reopened, request, check)
    write_metadata('runtime_request.json', canonical_bytes(request.to_dict()))
    write_metadata('byte_validation.json', canonical_bytes(validation))
    phase('FINALIZE_REGISTERED_NATIVE_SOURCE'); unchanged(); work_guard()
    receipt = work/'native_production_receipt.json'
    write_metadata(receipt.name, canonical_bytes({'schema_version': 1, 'policy': RECEIPT_POLICY,
        'status': 'REGISTERED_SOURCE_AND_FRESH_REOPEN_VERIFIED_NOT_EXECUTED',
        'recipe_sha256': recipe_sha, 'request_sha256': request.sha256,
        'target_action_binding_sha256': binding_sha256,
        'stage_job_id': stage_job.job_id, 'reopen_job_id': reopen_job.job_id,
        'native_stage_sha256': stage_sha, 'native_verification_sha256': fresh_sha,
        'byte_validation_sha256': _digest(work/'byte_validation.json', cancel),
        'frames_verified': 300, 'runtime_code_provenance_verified': False,
        'runtime_execution_verified': False, 'engine_import_verified': False,
        'visual_quality_approved': False, 'distribution_license_review_complete': False,
        'public_export_published': False, 'source_redistribution_authorized': False,
        'cloud_transmission_authorized': False}))
    def finalize():
        unchanged(); work_guard()
        _outputs(reopened, stage['files'], check, cancel)
        unchanged(); work_guard()
        check()
    _finish_owned_receipt(receipt, metadata[receipt.name], finalize)
    return PreparedRegisteredNativeSource(work, reopened, receipt, recipe_sha,
        request.sha256, binding_sha256, stage_job.job_id, reopen_job.job_id)
