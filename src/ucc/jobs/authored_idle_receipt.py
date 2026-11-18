"""Candidate receipt and read-only current admission, not usable-action approval."""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ucc.animations.authored_idle_mapping import build_original_idle_profile
from ucc.core.authored_idle import AuthoredIdleInspectionRequest, AuthoredIdleRequest
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import canonical_bytes, checked_sha, checked_uuid, closed
from .authored_idle_evidence import (INSPECT, AUTHOR, VERIFY, OUTPUTS, PROFILE, QUALITY,
    QUALITY_EXECUTION, checked_summary, checked_inspection, checked_author, checked_verification,
    need, read_idle_json, record)
from .authored_idle_io import private_bytes
from .authored_idle_sources import prepare_idle_context
from .authored_idle_transactions import inventory
from .protocol import JobRequest, JobResult
from .master_preview import _digest
from .target_action_context import operation_budget, protected

POLICY = 'UCC_PRIVATE_ORIGINAL_IDLE_CANDIDATE_RECEIPT_V1'
ROLES = ('inspection', 'author', 'verification')
OPS = (INSPECT, AUTHOR, VERIFY)
RETAINED = {'idle_inspection_request.json', 'idle_authoring_request.json',
    'idle_anatomical_frame.json', 'idle_inspection_report.json', 'original_idle.fbx',
    'authored_idle_recipe.json', 'authored_idle_report.json', 'authored_idle_source_snapshot.json',
    'authored_idle_verification.json', *(role+'_job_'+kind+'.json' for role in ROLES for kind in ('request', 'result'))}
FLAGS = {'existing_motion_read': False, 'project_modified': False, 'catalog_modified': False,
    'registered_in_catalog': False, 'automatic_retarget_family_admission': False,
    'private_candidate_only': True, 'review_scene_private_workspace_only': True, **QUALITY}


@dataclass(frozen=True, slots=True)
class AuthoredIdleCandidate:
    directory: Path
    receipt_sha256: str
    source_sha256: str
    review_path: Path
    review_sha256: str
    recipe_sha256: str
    snapshot_sha256: str
    anatomical_frame_sha256: str
    skeleton_fingerprint: str
    target: TargetActionTarget
    inspection_job_id: str
    author_job_id: str
    verification_job_id: str
    workdir: Path


@dataclass(frozen=True, slots=True)
class AdmittedIdleSource:
    candidate: AuthoredIdleCandidate
    request: AuthoredIdleRequest
    anatomical_frame_json: bytes
    recipe_json: bytes
    source_snapshot_json: bytes
    verification_json: bytes
    verification_summary: dict
    verification_job_request_json: bytes
    verification_job_result_json: bytes
    receipt_json: bytes


@dataclass(frozen=True, slots=True)
class AuthoredIdleTargetMapping:
    candidate: AuthoredIdleCandidate
    mapping_json: bytes
    mapping_sha256: str


def policy_names(count):
    return tuple(f'source-policy-{index:02d}.json' for index in range(count))


def pair_names(role):
    return role+'_job_request.json', role+'_job_result.json'


def check_worker_pair(store, job, result, folder, budget):
    need(folder == store.root/'.ucc-jobs'/job.job_id and protected(folder).is_dir(),
         'Idle result lost its actual owned worker workspace')
    need(result.job_id == job.job_id and result.operation == job.operation and result.status == 'ok',
         'Idle worker reply identity/status differs from the actual request')
    need(private_bytes(read_idle_json(folder/'request.json', budget, canonical=False, maximum=256*1024)) == private_bytes(job.as_dict())
        and private_bytes(read_idle_json(folder/'result.json', budget, canonical=False, maximum=256*1024)) == private_bytes(result.as_dict()),
        'Idle actual request/result files changed')
    # The runner's envelopes are not canonical intent JSON; retain their raw SHA.
    return {'job_id': job.job_id, 'request_sha256': record(folder/'request.json', budget)['sha256'],
            'result_sha256': record(folder/'result.json', budget)['sha256']}


def check_staged_inputs(folder, job, request, budget):
    inspect = job.operation == INSPECT
    name = 'idle_inspection_request.json' if inspect else 'idle_authoring_request.json'
    expected = {'candidate.blend': dict(request.to_dict()['consumed_sources'])['master_and_derived_rig'],
                name: request.sha256}
    if not inspect: expected['idle_anatomical_frame.json'] = request.anatomical_frame_sha256
    if job.operation == VERIFY:
        expected.update({'authored_idle_review.blend': job.options['review_sha256'],
            'original_idle.fbx': job.options['source_sha256'], 'authored_idle_recipe.json': job.options['recipe_sha256']})
    for name, pin in expected.items():
        need(record(folder/name, budget)['sha256'] == pin, 'Idle staged immutable input differs from its exact intent')


def _raw(path, expected, budget, maximum=64*1024*1024):
    row = record(path, budget, maximum)
    need(row['sha256'] == expected, 'Retained idle byte bundle changed')
    with path.open('rb') as stream: payload = stream.read(maximum+1)
    need(len(payload) <= maximum and sha256(payload).hexdigest() == expected, 'Retained idle bytes raced their hash check')
    return payload


def load_authored_idle_candidate(store, *, directory: Path, expected_receipt_sha256: str,
        source_policy_records: tuple, database_path: Path, blender_exe: Path,
        worker_script: Path, cancel=None, timeout_s=300) -> AdmittedIdleSource:
    """Recheck retained actual producers/current sources before a PURE mapper.

    Existing motion references remain in the snapshot but are never parsed as
    sources or staged into these workers. This loader performs no native work.
    """
    with _admitted_idle_candidate(store, directory, expected_receipt_sha256,
            source_policy_records, database_path, blender_exe, worker_script, cancel, timeout_s) as (admitted, _, _):
        return admitted


def load_authored_idle_target_mapping(store, *, directory: Path, expected_receipt_sha256: str,
        source_policy_records: tuple, database_path: Path, blender_exe: Path,
        worker_script: Path, cancel=None, timeout_s=300) -> AuthoredIdleTargetMapping:
    """Build a hash-bound target map from the current, independently reopened candidate.

    This performs read-only admission and returns bytes for explicit review.
    Source registration, target preparation and visual approval remain separate.
    """
    with _admitted_idle_candidate(store, directory, expected_receipt_sha256,
            source_policy_records, database_path, blender_exe, worker_script, cancel, timeout_s) as (admitted, verifier, budget):
        candidate = admitted.candidate
        profile = build_original_idle_profile(admitted.request,
            frame_json=admitted.anatomical_frame_json, recipe_json=admitted.recipe_json,
            snapshot_json=admitted.source_snapshot_json, verification_json=admitted.verification_json,
            worker_request_json=admitted.verification_job_request_json,
            worker_result_json=admitted.verification_job_result_json,
            source_sha256=candidate.source_sha256, review_sha256=candidate.review_sha256,
            recipe_sha256=candidate.recipe_sha256, snapshot_sha256=candidate.snapshot_sha256,
            worker_request_sha256=verifier['request_sha256'], worker_result_sha256=verifier['result_sha256'],
            inspection_job_id=candidate.inspection_job_id, verification_job_id=candidate.verification_job_id,
            cancel_check=budget.check)
        mapping = canonical_bytes(profile)
        return AuthoredIdleTargetMapping(candidate, mapping, sha256(mapping).hexdigest())


@contextmanager
def _admitted_idle_candidate(store, directory, expected_receipt_sha256, source_policy_records,
        database_path, blender_exe, worker_script, cancel, timeout_s):
    checked_sha(expected_receipt_sha256)
    with operation_budget(cancel, timeout_s) as budget:
        directory = protected(Path(directory))
        receipt = read_idle_json(directory/'authored_idle_receipt.json', budget, expected_receipt_sha256)
        closed(receipt, {'schema_version', 'policy', 'source_profile', 'inspection_request_sha256',
            'authoring_request_sha256', 'project_file_sha256', 'project_snapshot_sha256', 'target',
            'anatomical_frame_sha256', 'skeleton_fingerprint', 'source_sha256', 'review_sha256',
            'recipe_sha256', 'snapshot_sha256', 'files', 'workers', 'source_policy_records',
            'worker_dependencies', 'blender_executable_sha256', 'required_quality_execution', *FLAGS})
        need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1
            and receipt['policy'] == POLICY and receipt['source_profile'] == PROFILE
            and private_bytes(receipt['required_quality_execution']) == private_bytes(QUALITY_EXECUTION)
            and all(receipt[key] is expected for key, expected in FLAGS.items()), 'Private idle receipt scope changed')
        for key in ('inspection_request_sha256', 'authoring_request_sha256', 'project_file_sha256',
                    'project_snapshot_sha256', 'anatomical_frame_sha256', 'skeleton_fingerprint',
                    'source_sha256', 'review_sha256', 'recipe_sha256', 'snapshot_sha256'):
            checked_sha(receipt[key])
        names = RETAINED|set(policy_names(len(source_policy_records)))
        need(type(receipt['files']) is dict and set(receipt['files']) == names, 'Idle receipt file closure is incomplete or unrequested')
        for row in receipt['files'].values():
            closed(row, {'sha256', 'bytes'}); checked_sha(row['sha256'])
            need(type(row['bytes']) is int and row['bytes'] > 0, 'Idle receipt file size is invalid')
        frozen = inventory(directory, names|{'authored_idle_receipt.json'}, budget)
        need(frozen == {**receipt['files'], 'authored_idle_receipt.json': {
            'sha256': expected_receipt_sha256, 'bytes': record(directory/'authored_idle_receipt.json', budget)['bytes']}},
            'Idle delivered byte closure changed')
        inspection = AuthoredIdleInspectionRequest.from_bytes(_raw(directory/'idle_inspection_request.json', receipt['inspection_request_sha256'], budget, 256*1024))
        author = AuthoredIdleRequest.from_bytes(_raw(directory/'idle_authoring_request.json', receipt['authoring_request_sha256'], budget, 256*1024))
        need(author.project_snapshot_json == inspection.project_snapshot_json and author.permissions == inspection.permissions
            and author.purpose == inspection.purpose and author.target.to_dict() == receipt['target']
            and author.anatomical_frame_sha256 == receipt['anatomical_frame_sha256'], 'Idle author intent differs from its admitted inspection')
        context = prepare_idle_context(store, inspection, source_policy_records, Path(database_path),
            Path(blender_exe), Path(worker_script), None, budget, create_jobs=False)
        need(context.project_file_sha256 == receipt['project_file_sha256']
            and author.to_dict()['project_snapshot_sha256'] == receipt['project_snapshot_sha256']
            and context.executable_sha256 == receipt['blender_executable_sha256'], 'Current idle source/project/executable selection differs')
        current_dependencies = {str(path): _digest(path, budget.cancel) for path in context.worker_files}
        need(receipt['worker_dependencies'] == current_dependencies, 'Idle worker execution closure differs from its retained producer')
        policies = [{'asset_id': source.asset_id, 'source_sha256': source.sha256, 'provenance_sha256': source.provenance_sha256,
            'record_sha256': selected.sha256, 'record_file': name}
            for source, selected, name in zip(context.sources, source_policy_records, policy_names(len(context.sources)))]
        need(receipt['source_policy_records'] == policies, 'Idle per-source policy/provenance lineage differs')
        for selected, name in zip(source_policy_records, policy_names(len(context.sources))):
            need(receipt['files'][name]['sha256'] == selected.sha256, 'Idle retained policy bytes differ from the explicit current review')
        workers = closed(receipt['workers'], set(ROLES)); pairs = []; summaries = []
        ids = []
        for role in ROLES:
            row = closed(workers[role], {'job_id', 'request_sha256', 'result_sha256'})
            checked_uuid(row['job_id']); checked_sha(row['request_sha256']); checked_sha(row['result_sha256']); ids.append(row['job_id'])
        need(len(set(ids)) == 3 and ids[0] == inspection.job_id and ids[1] == author.job_id,
             'Idle producer identities are not three distinct actual phase jobs')
        options = [{'request_sha256': inspection.sha256}, {'request_sha256': author.sha256},
            {'request_sha256': author.sha256, 'review_sha256': receipt['review_sha256'],
             'source_sha256': receipt['source_sha256'], 'recipe_sha256': receipt['recipe_sha256']}]
        for index, role in enumerate(ROLES):
            row = workers[role]; folder = store.root/'.ucc-jobs'/row['job_id']
            job = JobRequest(row['job_id'], OPS[index], 'candidate.blend', options[index])
            request_name, result_name = pair_names(role)
            need(_raw(directory/request_name, row['request_sha256'], budget) == _raw(folder/'request.json', row['request_sha256'], budget), 'Idle retained/actual request bytes differ')
            need(_raw(directory/result_name, row['result_sha256'], budget) == _raw(folder/'result.json', row['result_sha256'], budget), 'Idle retained/actual result bytes differ')
            result = JobResult.from_dict(read_idle_json(folder/'result.json', budget, canonical=False, maximum=256*1024))
            need(check_worker_pair(store, job, result, folder, budget) == row, 'Idle current actual worker pair differs')
            check_staged_inputs(folder, job, inspection if index == 0 else author, budget)
            summary = result.details
            checked_summary(summary, OPS[index], inspection if index == 0 else author, folder, budget)
            pairs.append(folder); summaries.append(summary)
        target, frame = checked_inspection(pairs[0], inspection, summaries[0], budget)
        need(target == author.target and summaries[0]['anatomical_frame_sha256'] == author.anatomical_frame_sha256,
             'Idle author was not derived from actual retained neutral inspection')
        checked_author(pairs[1], author, summaries[1], frame, budget)
        checked_verification(pairs[2], author, summaries[2], frame, budget, receipt['source_sha256'])
        for role, summary, folder in zip(ROLES, summaries, pairs):
            for row in summary['outputs']:
                if row['name'] == 'authored_idle_review.blend': continue
                need(record(directory/row['name'], budget) == row, 'Idle delivered files differ from actual independently admitted workers')
        review = pairs[1]/'authored_idle_review.blend'
        need(record(review, budget)['sha256'] == receipt['review_sha256'], 'Private idle review scene changed')
        need(receipt['files']['original_idle.fbx']['sha256'] == receipt['source_sha256']
            and receipt['files']['authored_idle_recipe.json']['sha256'] == receipt['recipe_sha256']
            and receipt['files']['authored_idle_source_snapshot.json']['sha256'] == receipt['snapshot_sha256']
            and summaries[2]['skeleton_fingerprint'] == receipt['skeleton_fingerprint'], 'Idle source/recipe/snapshot/family bindings differ')
        candidate = AuthoredIdleCandidate(directory, expected_receipt_sha256, receipt['source_sha256'], review,
            receipt['review_sha256'], receipt['recipe_sha256'], receipt['snapshot_sha256'], receipt['anatomical_frame_sha256'],
            receipt['skeleton_fingerprint'], author.target, *ids, store.root/'.ucc-jobs'/('authored-idle-'+inspection.job_id))
        admitted = AdmittedIdleSource(candidate, author,
            _raw(directory/'idle_anatomical_frame.json', receipt['anatomical_frame_sha256'], budget),
            _raw(directory/'authored_idle_recipe.json', receipt['recipe_sha256'], budget),
            _raw(directory/'authored_idle_source_snapshot.json', receipt['snapshot_sha256'], budget),
            _raw(directory/'authored_idle_verification.json', receipt['files']['authored_idle_verification.json']['sha256'], budget),
            summaries[2], _raw(directory/pair_names('verification')[0], workers['verification']['request_sha256'], budget),
            _raw(directory/pair_names('verification')[1], workers['verification']['result_sha256'], budget),
            _raw(directory/'authored_idle_receipt.json', expected_receipt_sha256, budget))
        yield admitted, workers['verification'], budget
        for role, folder, summary in zip(ROLES, pairs, summaries):
            for kind in ('request', 'result'):
                need(record(folder/(kind+'.json'), budget)['sha256'] == workers[role][kind+'_sha256'],
                     'Idle actual request/result bytes changed during current admission')
            for row in summary['outputs']:
                need(record(folder/row['name'], budget) == row,
                     'Idle actual output bytes changed during current admission')
        context.guard()
        need(inventory(directory, names|{'authored_idle_receipt.json'}, budget) == frozen, 'Idle candidate changed during current admission')
