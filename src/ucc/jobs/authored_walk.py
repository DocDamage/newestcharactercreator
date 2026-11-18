"""Author and independently verify a private original walk on the saved MPFB rig."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ucc.core.authored_idle import PROFILE, AuthoredIdleInspectionRequest
from ucc.core.authored_walk_job import AUTHOR, VERIFY, INTENT, INPUT_BINDINGS, REOPEN_BINDINGS, walk_intent
from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import canonical_bytes
from .authored_idle import _copy_bound, _write
from .authored_idle_evidence import INSPECT, OUTPUTS, checked_inspection, checked_summary, need, read_idle_json, record
from .authored_idle_io import private_bytes
from .authored_idle_policy import IdleSourcePolicyRecord
from .authored_idle_receipt import check_worker_pair, pair_names, policy_names
from .authored_idle_sources import prepare_idle_context
from .authored_idle_transactions import IdlePublication, inventory
from .export_destination import ExportDestination, plan_destination
from .godot_candidate_inputs import identity
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .target_action_context import operation_budget, protected


INSPECTION = 'idle_inspection_request.json'
ANATOMY = 'idle_anatomical_frame.json'
AUTHOR_REPORT = 'walk_author_report.json'
VERIFY_REPORT = 'walk_verification.json'
SNAPSHOT = 'authored_walk_source_snapshot.json'
RECEIPT = 'authored_walk_receipt.json'
AUTHOR_STATUS = 'ORIGINAL_WALK_BAKED'
VERIFY_STATUS = 'ORIGINAL_WALK_TECHNICALLY_VERIFIED'
CONTACT_CHECKS = {
    'compensated_stance_anchor', 'compensated_stance_drift', 'stance_height_vs_neutral',
    'weighted_foot_floor', 'whole_visible_floor', 'weighted_peak_swing_clearance',
    'knee_bends_toward_neutral_pole', 'knee_flex', 'no_large_adjacent_knee_angle_step',
}
UNAPPROVED = (
    'owner_visual_review_performed', 'visual_quality_approved', 'usable_action_approved',
    'target_registered', 'engine_imported', 'source_redistribution_authorized',
)


@dataclass(frozen=True, slots=True)
class AuthoredWalkCandidate:
    directory: Path
    receipt_sha256: str
    fbx_path: Path
    review_path: Path
    snapshot_sha256: str


def _summary(details: object, status: str, outputs: dict[str, dict]) -> None:
    expected = {name: {key: row[key] for key in ('bytes', 'sha256')} for name, row in outputs.items()}
    need(private_bytes(details) == private_bytes({'status': status, 'outputs': expected}),
         'Original walk worker summary differs from the measured output files')


def _read_report(path: Path, row: dict, budget) -> dict:
    report = read_idle_json(path, budget, row['sha256'], canonical=False)
    need(sha256(private_bytes(report)).hexdigest() == row['sha256'],
         'Original walk requires canonical private evidence')
    return report


def _check_verification(report: dict, pins: dict[str, str], target: dict, snapshot: dict) -> None:
    gates = report.get('technical_contact_checks')
    need(report.get('schema_version') == 1 and report.get('policy') == 'UCC_ORIGINAL_WALK_VERIFICATION_V1'
         and report.get('status') == VERIFY_STATUS and report.get('request_sha256') == pins[INSPECTION]
         and report.get('walk_request_sha256') == pins[INTENT] and report.get('input_sha256') == pins
         and report.get('target') == target and report.get('source_snapshot') == snapshot
         and report.get('staged_inputs_preserved') is True
         and all(report.get(flag) is False for flag in UNAPPROVED),
         'Original walk verification lost a source, target, snapshot or private review binding')
    need(type(gates) is dict and set(gates) == CONTACT_CHECKS and all(value is True for value in gates.values()),
         'Original walk verification requires all nine contact and knee checks')
    saved, imported = report.get('saved_bake'), report.get('fbx_reimport')
    need(type(saved) is dict and saved.get('frames') == 300 and saved.get('evaluated_visible_vertices') == 13380
         and saved.get('stored_clock') == [1, 300, 30] and saved.get('virtual_frame_stored') is False
         and type(imported) is dict and imported.get('import_clock') == [2, 301, 30]
         and imported.get('exact_full_timeline_compared') is True and imported.get('virtual_frame_stored') is False
         and report.get('root_motion') == 'IN_PLACE' and report.get('armature_root_offset_m') == [0., 0., -.045],
         'Original walk verification requires the full saved and FBX loop and exact root placement')


def author_original_walk(store: ProjectStore, *, inspection_request: AuthoredIdleInspectionRequest,
        source_policy_records: tuple[IdleSourcePolicyRecord, ...], database_path: Path,
        destination: ExportDestination, blender_exe: Path, worker_script: Path,
        cancel=None, timeout_s=3600) -> AuthoredWalkCandidate:
    """Measure neutral anatomy, author the walk, verify in fresh Blender, and publish."""
    if (type(inspection_request) is not AuthoredIdleInspectionRequest or inspection_request.profile != PROFILE
            or inspection_request.project.parts):
        raise ValidationError('Original walk requires the saved part-free MPFB character and explicit source review')
    if type(destination) is not ExportDestination or plan_destination(destination.path, store.root) != destination:
        raise ValidationError('Original walk requires the selected new private destination')
    with operation_budget(cancel, timeout_s) as budget:
        return _author(store, inspection_request, source_policy_records, Path(database_path),
                       destination, Path(blender_exe), Path(worker_script), budget)


def _author(store, inspection, policies, database, destination, blender, worker, budget):
    context = prepare_idle_context(store, inspection, policies, database, blender, worker, destination, budget)
    jobs = store.root / '.ucc-jobs'
    work = protected(jobs / ('authored-walk-' + inspection.job_id))
    destination.unchanged()
    work.mkdir(exist_ok=False)
    work_stamp = identity(protected(work))
    runner = BlenderJobRunner(blender, jobs, worker)
    frozen, retained, producers = {}, {}, {}

    def freeze(path: Path) -> dict:
        row = record(path, budget)
        need(path not in frozen or frozen[path] == row, 'Original walk input changed during authoring')
        frozen[path] = row
        return row

    def write_input(name: str, payload: bytes) -> Path:
        path = work / name
        _write(path, payload, work_stamp)
        need(freeze(path)['sha256'] == sha256(payload).hexdigest(), 'Original walk intent changed during staging')
        retained[name] = path
        return path

    def guard() -> None:
        context.guard()
        need(identity(protected(work)) == work_stamp, 'Original walk workspace changed during authoring')
        for path, row in frozen.items():
            need(record(path, budget) == row, 'Original walk evidence changed during authoring')

    def execute(role, job, inputs, pins, outputs):
        guard()
        need(set(inputs) == set(pins), 'Original walk worker inputs differ from their closed phase')
        for name, path in inputs.items():
            need(record(path, budget)['sha256'] == pins[name], 'Original walk producer input differs from its pin')
        result, folder = runner.run(job, staged_inputs=inputs, timeout_s=budget.remaining(), cancel=budget.cancel)
        guard()
        producers[role] = check_worker_pair(store, job, result, folder, budget)
        for name, pin in pins.items():
            need(freeze(folder / name)['sha256'] == pin, 'Original walk staged worker input differs from its pin')
        for kind, name in zip(('request', 'result'), pair_names(role), strict=True):
            path = folder / (kind + '.json')
            need(freeze(path)['sha256'] == producers[role][kind + '_sha256'],
                 'Original walk worker record changed after admission')
            retained[name] = path
        rows = {}
        for name in outputs:
            path = folder / name
            rows[name] = freeze(path)
            retained[name] = path
        return folder, result.details, rows

    request = write_input(INSPECTION, canonical_bytes(inspection.to_dict()))
    master_pin = inspection.to_dict()['consumed_sources']['master_and_derived_rig']
    measured, measured_summary, _ = execute('inspection',
        JobRequest(inspection.job_id, INSPECT, 'candidate.blend', {'request_sha256': inspection.sha256}),
        {'candidate.blend': context.master, INSPECTION: request},
        {'candidate.blend': master_pin, INSPECTION: inspection.sha256}, OUTPUTS[INSPECT])
    checked_summary(measured_summary, INSPECT, inspection, measured, budget)
    target, _ = checked_inspection(measured, inspection, measured_summary, budget)
    anatomy = measured_summary['anatomical_frame_sha256']
    project = write_input('project.ucc.json', inspection.project_snapshot_json)
    intent = write_input(INTENT, canonical_bytes(walk_intent(inspection, anatomy)))
    pins = {'candidate.blend': master_pin, INSPECTION: inspection.sha256, ANATOMY: anatomy,
            project.name: frozen[project]['sha256'], INTENT: frozen[intent]['sha256']}
    inputs = {'candidate.blend': context.master, INSPECTION: request, ANATOMY: measured / ANATOMY,
              project.name: project, INTENT: intent}
    options = {key: pins[name] for name, key in INPUT_BINDINGS.items()}
    authored, author_summary, authored_rows = execute('author',
        JobRequest.new(AUTHOR, input_project='candidate.blend', options=options), inputs, pins,
        (*REOPEN_BINDINGS, AUTHOR_REPORT))
    _summary(author_summary, AUTHOR_STATUS, authored_rows)
    author_report = _read_report(authored / AUTHOR_REPORT, authored_rows[AUTHOR_REPORT], budget)
    named_author_rows = {name: {key: authored_rows[name][key] for key in ('bytes', 'sha256')}
                         for name in REOPEN_BINDINGS}
    staged_inputs = {name: {key: frozen[authored / name][key] for key in ('bytes', 'sha256')} for name in pins}
    need(author_report.get('policy') == 'UCC_PRIVATE_ORIGINAL_WALK_BAKE_V1'
         and author_report.get('status') == 'ORIGINAL_WALK_BAKED_PENDING_INDEPENDENT_REOPEN'
         and author_report.get('input_pins') == staged_inputs and author_report.get('files') == named_author_rows
         and author_report.get('neutral_rest_sha256') == target.rest_sha256
         and author_report.get('stored_action_samples') == 300
         and all(author_report.get(flag) is False for flag in ('usable_action_approved', 'visual_quality_approved',
             'contact_quality_approved', 'engine_import_verified')),
         'Original walk bake report differs from the measured neutral rig or full candidate scope')

    verify_inputs = inputs | {name: authored / name for name in REOPEN_BINDINGS}
    verify_pins = pins | {name: authored_rows[name]['sha256'] for name in REOPEN_BINDINGS}
    verify_options = options | {key: verify_pins[name] for name, key in REOPEN_BINDINGS.items()}
    verified, verify_summary, verified_rows = execute('verification',
        JobRequest.new(VERIFY, input_project='candidate.blend', options=verify_options),
        verify_inputs, verify_pins, (VERIFY_REPORT, SNAPSHOT))
    _summary(verify_summary, VERIFY_STATUS, verified_rows)
    verified_report = _read_report(verified / VERIFY_REPORT, verified_rows[VERIFY_REPORT], budget)
    _check_verification(verified_report, verify_pins, target.to_dict(), verified_rows[SNAPSHOT])

    guard()
    stage = destination.stage(inspection.job_id)
    stage_stamp = identity(protected(stage))
    files = {}
    for name, path in retained.items():
        row = frozen[path]
        files[name] = {key: row[key] for key in ('bytes', 'sha256')}
        _copy_bound(path, stage / name, row['sha256'], budget, stage_stamp)
    source_records = []
    for source, selected, name in zip(context.sources, policies, policy_names(len(policies)), strict=True):
        row = record(selected.path, budget)
        need(row['sha256'] == selected.sha256, 'Original walk source policy changed before publication')
        files[name] = {key: row[key] for key in ('bytes', 'sha256')}
        _copy_bound(selected.path, stage / name, selected.sha256, budget, stage_stamp)
        source_records.append({'asset_id': source.asset_id, 'source_sha256': source.sha256,
            'provenance_sha256': source.provenance_sha256, 'record_sha256': selected.sha256, 'record_file': name})
    names = set(files)
    need(inventory(stage, names, budget) == files, 'Original walk staged files differ from their producers')
    receipt = private_bytes({'schema_version': 1, 'policy': 'UCC_PRIVATE_ORIGINAL_WALK_RECEIPT_V1',
        'status': VERIFY_STATUS, 'target': target.to_dict(), 'input_sha256': verify_pins, 'files': files,
        'workers': producers, 'source_policy_records': source_records, 'project_file_sha256': context.project_file_sha256,
        'blender_executable_sha256': context.executable_sha256, **dict.fromkeys(UNAPPROVED, False)})
    _write(stage / RECEIPT, receipt, stage_stamp)
    receipt_sha = sha256(receipt).hexdigest()
    expected = {**files, RECEIPT: {'bytes': len(receipt), 'sha256': receipt_sha}}
    publication = IdlePublication(store, destination, stage, names | {RECEIPT}, budget)
    need(publication.files == expected, 'Original walk files changed before exclusive publication')
    try:
        publication.commit(guard, budget)
        guard()
        need(inventory(destination.path, names | {RECEIPT}, budget) == expected,
             'Published original walk files differ from the independent verification')
        return AuthoredWalkCandidate(destination.path, receipt_sha, destination.path / 'original_walk.fbx',
                                     destination.path / 'original_walk.blend', verified_rows[SNAPSHOT]['sha256'])
    except BaseException as error:
        publication.withdraw(error)
        raise
