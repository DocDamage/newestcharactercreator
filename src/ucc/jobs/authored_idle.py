"""Neutral inspection → original idle source → independent reopen, private only.

This API never attaches a clip or grants usable-action, sprite or engine rights.
The private review scene remains in the actual author worker workspace.
"""
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ucc.core.authored_idle import AuthoredIdleInspectionRequest, AuthoredIdleRequest
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from .authored_idle_evidence import (INSPECT, AUTHOR, VERIFY, PROFILE, OUTPUTS,
    QUALITY_EXECUTION, checked_summary, checked_inspection, checked_author,
    checked_verification, record, need)
from .authored_idle_io import private_bytes
from .authored_idle_policy import IdleSourcePolicyRecord
from .authored_idle_sources import prepare_idle_context, inspect_idle_authoring_sources
from .authored_idle_receipt import (AuthoredIdleCandidate, AdmittedIdleSource,
    load_authored_idle_candidate, check_worker_pair, check_staged_inputs,
    RETAINED, ROLES, POLICY, FLAGS, policy_names, pair_names)
from .authored_idle_transactions import IdlePublication, write_journal, inventory
from .export_destination import ExportDestination, plan_destination
from .master_preview import _digest
from .runner import BlenderJobRunner
from .protocol import JobRequest
from .target_action_context import operation_budget, protected
from .godot_candidate_inputs import identity


def _write(path, payload, parent_stamp):
    protected(path); protected(path.parent)
    need(identity(path.parent) == parent_stamp, 'Idle owned write directory changed')
    with path.open('xb') as stream: stream.write(payload)


def _copy_bound(source, target, expected, budget, parent_stamp):
    """Copy authenticated bytes exclusively; neither source nor destination wins a race."""
    protected(target); protected(target.parent)
    before = record(source, budget)
    need(before['sha256'] == expected, 'Idle retained producer bytes changed before copy')
    digest = sha256(); size = 0
    need(identity(protected(target.parent)) == parent_stamp, 'Idle copy destination directory changed')
    with source.open('rb') as incoming, target.open('xb') as outgoing:
        while True:
            budget.check(); block = incoming.read(min(1024*1024, before['bytes']-size+1))
            if not block: break
            size += len(block)
            need(size <= before['bytes'], 'Idle producer grew during destination copy')
            outgoing.write(block); digest.update(block)
    need(size == before['bytes'] and digest.hexdigest() == expected
        and record(source, budget) == before and record(target, budget)['sha256'] == expected,
        'Idle retained copy differs from independently verified bytes')


def author_original_idle(store, *, inspection_request: AuthoredIdleInspectionRequest,
        source_policy_records: tuple[IdleSourcePolicyRecord, ...], database_path: Path,
        destination: ExportDestination, blender_exe: Path, worker_script: Path,
        cancel=None, timeout_s=3600) -> AuthoredIdleCandidate:
    """Execute three guarded workers with one deadline and exclusive publication.

    Policies and per-use permissions are explicit caller inputs. Existing motion
    references remain in the saved snapshot, but no referenced clip is loaded,
    evaluated or staged. Catalog coordination uses byte guards without SQL.
    """
    if type(inspection_request) is not AuthoredIdleInspectionRequest or type(destination) is not ExportDestination:
        raise ValidationError('Idle authoring requires explicit typed inspection, permissions and a new destination')
    if plan_destination(destination.path, store.root) != destination:
        raise ValidationError('Idle destination parent no longer matches the selected authorization')
    with operation_budget(cancel, timeout_s) as budget:
        return _author(store, inspection_request, source_policy_records, Path(database_path),
            destination, Path(blender_exe), Path(worker_script), budget)


def _author(store, inspection, policies, database, destination, blender, worker, budget):
    context = prepare_idle_context(store, inspection, policies, database, blender, worker, destination, budget)
    context.guard(); destination.unchanged()
    jobs = store.root/'.ucc-jobs'; work = jobs/('authored-idle-'+inspection.job_id)
    protected(work); work.mkdir(exist_ok=False); publication = None; stage = None
    work_stamp = identity(protected(work))
    def journal(state, **extra):
        need(identity(protected(work)) == work_stamp, 'Idle journal workspace changed')
        write_journal(work, inspection.sha256, state, **extra)
    runner = BlenderJobRunner(blender, jobs, worker)
    retained = {}; producers = {}; frozen = {}

    def guard():
        context.guard()
        need(identity(protected(work)) == work_stamp, 'Idle owned workspace changed')
        for path, row in frozen.items():
            need(record(path, budget) == row, 'An admitted idle phase changed before completion')

    def execute(role, job, intent, inputs):
        guard(); journal(role.upper()+'_STARTED')
        result, folder = runner.run(job, staged_inputs=inputs, timeout_s=budget.remaining(), cancel=budget.cancel)
        guard(); producers[role] = check_worker_pair(store, job, result, folder, budget)
        check_staged_inputs(folder, job, intent, budget)
        checked_summary(result.details, job.operation, intent, folder, budget)
        for name in (*inputs, 'request.json', 'result.json', *OUTPUTS[job.operation]):
            path = folder/name; frozen[path] = record(path, budget)
        for name, source in inputs.items():
            need(record(folder/name, budget)['sha256'] == record(source, budget)['sha256'],
                'Idle worker input differs from its guarded producer')
        for kind, name in zip(('request', 'result'), pair_names(role)):
            retained[name] = folder/(kind+'.json')
        for name in OUTPUTS[job.operation]:
            if name != 'authored_idle_review.blend': retained[name] = folder/name
        return result.details, folder

    try:
        inspection_path = work/'idle_inspection_request.json'
        _write(inspection_path, canonical_bytes(inspection.to_dict()), work_stamp)
        frozen[inspection_path] = record(inspection_path, budget); retained[inspection_path.name] = inspection_path
        summary, measured = execute('inspection', JobRequest(inspection.job_id, INSPECT, 'candidate.blend',
            {'request_sha256': inspection.sha256}), inspection,
            {'candidate.blend': context.master, inspection_path.name: inspection_path})
        target, frame = checked_inspection(measured, inspection, summary, budget)
        author = AuthoredIdleRequest(str(uuid4()), inspection.project_snapshot_json, target,
            summary['anatomical_frame_sha256'], inspection.permissions, inspection.purpose,
            inspection.original_procedural_recipe_declared, inspection.private_authored_output_preview_confirmed,
            profile=inspection.profile)
        author_path = work/'idle_authoring_request.json'
        _write(author_path, canonical_bytes(author.to_dict()), work_stamp)
        frozen[author_path] = record(author_path, budget); retained[author_path.name] = author_path
        inputs = {'candidate.blend': context.master, author_path.name: author_path,
            'idle_anatomical_frame.json': measured/'idle_anatomical_frame.json'}
        authored, authored_folder = execute('author', JobRequest(author.job_id, AUTHOR, 'candidate.blend',
            {'request_sha256': author.sha256}), author, inputs)
        checked_author(authored_folder, author, authored, frame, budget)
        bindings = {name: frozen[authored_folder/name]['sha256'] for name in OUTPUTS[AUTHOR][:3]}
        verify_options = {'request_sha256': author.sha256, 'review_sha256': bindings['authored_idle_review.blend'],
            'source_sha256': bindings['original_idle.fbx'], 'recipe_sha256': bindings['authored_idle_recipe.json']}
        verify_inputs = {**inputs, **{name: authored_folder/name for name in bindings}}
        verified, verified_folder = execute('verification', JobRequest.new(VERIFY, input_project='candidate.blend',
            options=verify_options), author, verify_inputs)
        checked_verification(verified_folder, author, verified, frame, budget, verify_options['source_sha256'])
        guard(); stage = destination.stage(inspection.job_id); stage_stamp = identity(protected(stage))
        for selected, name in zip(policies, policy_names(len(policies))): retained[name] = selected.path
        names = RETAINED|set(policy_names(len(policies)))
        need(set(retained) == names, 'Idle publication omitted an independently checked producer')
        for name, source in retained.items():
            need(identity(protected(stage)) == stage_stamp, 'Idle destination staging directory changed')
            expected = (next(row.sha256 for row in policies if row.path == source) if name.startswith('source-policy-')
                else frozen[source]['sha256'])
            _copy_bound(source, stage/name, expected, budget, stage_stamp)
        files = inventory(stage, names, budget)
        receipt = {'schema_version': 1, 'policy': POLICY, 'source_profile': PROFILE,
            'inspection_request_sha256': inspection.sha256, 'authoring_request_sha256': author.sha256,
            'project_file_sha256': context.project_file_sha256, 'project_snapshot_sha256': author.to_dict()['project_snapshot_sha256'],
            'target': target.to_dict(), 'anatomical_frame_sha256': author.anatomical_frame_sha256,
            'skeleton_fingerprint': verified['skeleton_fingerprint'], 'source_sha256': verify_options['source_sha256'],
            'review_sha256': verify_options['review_sha256'], 'recipe_sha256': verify_options['recipe_sha256'],
            'snapshot_sha256': frozen[verified_folder/'authored_idle_source_snapshot.json']['sha256'],
            'files': files, 'workers': producers, 'source_policy_records': [
                {'asset_id': source.asset_id, 'source_sha256': source.sha256, 'provenance_sha256': source.provenance_sha256,
                 'record_sha256': selected.sha256, 'record_file': name}
                for source, selected, name in zip(context.sources, policies, policy_names(len(policies)))],
            'worker_dependencies': {str(path): _digest(path, budget.cancel) for path in context.worker_files},
            'blender_executable_sha256': context.executable_sha256,
            'required_quality_execution': dict(QUALITY_EXECUTION), **FLAGS}
        need(identity(protected(stage)) == stage_stamp, 'Idle destination staging directory changed')
        receipt_path = stage/'authored_idle_receipt.json'; _write(receipt_path, private_bytes(receipt), stage_stamp)
        receipt_sha = record(receipt_path, budget)['sha256']
        publication = IdlePublication(store, destination, stage, names|{receipt_path.name}, budget)
        guard(); journal('DESTINATION_STAGED'); publication.commit(guard, budget)
        # Reopen the actual published closure through the same public admission used
        # by a later mapper. This does not launch a worker or register anything.
        admitted = load_authored_idle_candidate(store, directory=destination.path,
            expected_receipt_sha256=receipt_sha, source_policy_records=policies, database_path=database,
            blender_exe=blender, worker_script=worker, cancel=budget.cancel, timeout_s=budget.remaining())
        guard(); journal('PRIVATE_CANDIDATE_PUBLISHED', receipt_sha256=receipt_sha); budget.check()
        return admitted.candidate
    except BaseException as error:
        if publication is not None: publication.withdraw(error)
        try: journal('FAILED', error_type=type(error).__name__, retained_stage=None if stage is None else str(stage))
        except (OSError, ProjectStorageError) as failure:
            error.add_note('Idle failure journal could not be written: '+str(failure))
        raise
