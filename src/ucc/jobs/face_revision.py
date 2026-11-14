"""Apply saved facial intent through two isolated workers and one atomic promotion."""
from dataclasses import dataclass
import json
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.facial import build_face_recipe, NOSE_TARGETS, FACE_BASE_SHA256, FACE_RIG_SHA256, POLICY
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .geometry_evidence import EvidenceError
from .master_preview import _digest, _master_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class FaceRevisionResult:
    project: CharacterProject
    revision: MasterRevision | None
    observed: dict
    stage_job_id: str
    reopen_job_id: str


def _cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Facial revision cancelled; old master remains authoritative')


def bundled_face_assets(data_dir: Path, cancel: Event | None = None) -> dict[str, tuple[Path, str]]:
    """Inspect only the explicit already-installed MPFB data directory; no discovery/download."""
    root = Path(data_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValidationError('Select the existing installed MPFB data directory')
    resolved = root.resolve(strict=True)
    paths = {'base': (root/'3dobjs/base.obj', FACE_BASE_SHA256),
             'rig': (root/'rigs/standard/rig.default.json', FACE_RIG_SHA256),
             **{t.role: (root/'targets/nose'/t.filename, t.sha256) for t in NOSE_TARGETS}}
    for name, (path, expected) in paths.items():
        _cancel(cancel)
        if (path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(resolved)
                or _digest(path, cancel) != expected):
            raise ValidationError('Installed MPFB facial asset is missing, redirected or changed: '+name)
    return paths


def apply_saved_face_revision(
    store: ProjectStore, *, blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
    expected_project_id: str, expected_revision: int, expected_master_blend: str,
    cancel: Event | None = None, timeout_s: float = 300,
) -> FaceRevisionResult:
    """Preserve the original until independently reproduced geometry passes.

    An already-applied recipe returns revision=None after real verification;
    it never advances the project just because Blender resaved identical skin.
    """
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id or initial.revision != expected_revision
            or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed while preparing facial revision')
    if initial.expression is not None:
        from .expression_mutation import preserve_expressions
        return preserve_expressions(store, operation='face_revision', blender_exe=blender_exe,
            worker_script=worker_script, mpfb_data_dir=mpfb_data_dir,
            expected_project_id=expected_project_id, expected_revision=expected_revision,
            expected_master_blend=expected_master_blend, cancel=cancel, timeout_s=timeout_s)
    if initial.family != 'humanoid.v1' or initial.base_provider != 'mpfb' or initial.parts or initial.animations:
        raise ValidationError('Facial revision supports only an unattached saved MPFB humanoid')
    if not initial.facial_parameters:
        raise ValidationError('Save explicit facial intent before applying a facial revision')
    if initial.master_blend is None:
        raise ValidationError('Generate an existing MPFB master before applying a facial revision')
    if type(timeout_s) not in (int, float) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Facial timeout_s outside supported range')
    executable, script = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file() or script.is_symlink() or not script.is_file():
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    _cancel(cancel)
    source, source_sha = _master_file(store, expected_master_blend)
    if _digest(source, cancel) != source_sha:
        raise ProjectStorageError('Existing facial source master does not match its immutable filename')
    assets = bundled_face_assets(Path(mpfb_data_dir), cancel)
    jobs = store.root/'.ucc-jobs'
    if jobs.is_symlink() or not jobs.resolve(strict=False).is_relative_to(store.root):
        raise ProjectStorageError('Facial jobs directory is redirected')
    inputs = jobs/('face-inputs-'+str(uuid4())); inputs.mkdir(parents=True, exist_ok=False)
    recipe_file = inputs/'face_recipe.json'
    with recipe_file.open('x', encoding='utf-8') as stream:
        json.dump(build_face_recipe(source_sha, dict(initial.facial_parameters)), stream, indent=2, allow_nan=False)
    options = {'master_sha256': source_sha, 'recipe_sha256': _digest(recipe_file, cancel),
               **{t.role+'_target_sha256': t.sha256 for t in NOSE_TARGETS}}
    staged = {'candidate.blend': source, 'face_recipe.json': recipe_file,
              **{t.filename: assets[t.role][0] for t in NOSE_TARGETS}}
    runner = BlenderJobRunner(executable, jobs, script)
    request = JobRequest.new('stage_mpfb_face', input_project='candidate.blend', options=options)
    staged_result, workdir = runner.run(request, staged_inputs=staged, timeout_s=timeout_s, cancel=cancel)
    output, report = workdir/'faced_human.blend', workdir/'face_report.json'
    if output.is_symlink() or not output.is_file() or output.stat().st_size < 1024 or report.is_symlink() or not report.is_file():
        raise EvidenceError('Facial worker produced no saved scene/report')
    face_sha, report_sha = _digest(output, cancel), _digest(report, cancel)
    info = staged_result.details
    if (type(info.get('schema_version')) is not int or info.get('schema_version') != 1 or info.get('policy') != POLICY
            or info.get('recipe_sha256') != options['recipe_sha256']
            or info.get('source_master_sha256') != source_sha or info.get('scene_sha256') != face_sha
            or type(info.get('metrics')) is not dict or type(info['metrics'].get('geometry_changed')) is not bool
            or type(info['metrics'].get('target_values_changed')) is not bool
            or info.get('visual_quality_approved') is not False or info.get('engine_import_verified') is not False):
        raise EvidenceError('Facial stage lacks bound geometry evidence')
    _cancel(cancel)
    verify_options = dict(options, face_sha256=face_sha, report_sha256=report_sha)
    verification = JobRequest.new('verify_mpfb_face', input_project='candidate.blend', options=verify_options)
    verified, verify_dir = runner.run(verification, staged_inputs={
        **staged, 'faced_human.blend': output, 'face_report.json': report}, timeout_s=timeout_s, cancel=cancel)
    proof = verified.details
    expected_proof = {'schema_version': 1, 'policy': POLICY, 'verified_reopen': True,
                      'source_master_sha256': source_sha, 'scene_sha256': face_sha,
                      'recipe_sha256': options['recipe_sha256'],
                      'geometry_changed': info['metrics']['geometry_changed'],
                      'target_values_changed': info['metrics']['target_values_changed'],
                      'visual_quality_approved': False, 'engine_import_verified': False}
    if (proof != expected_proof or type(proof.get('schema_version')) is not int
            or any(type(proof.get(k)) is not bool for k in ('verified_reopen', 'geometry_changed', 'target_values_changed'))):
        raise EvidenceError('Independent facial worker did not verify the exact saved scene')
    for name, original in {**staged, 'faced_human.blend': output, 'face_report.json': report}.items():
        expected = {'candidate.blend': source_sha, 'face_recipe.json': options['recipe_sha256'],
                    'faced_human.blend': face_sha, 'face_report.json': report_sha,
                    **{t.filename: t.sha256 for t in NOSE_TARGETS}}[name]
        for path in (original, verify_dir/name, workdir/name):
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != expected:
                raise ProjectStorageError('Facial input/output changed before master promotion: '+name)
    bundled_face_assets(Path(mpfb_data_dir), cancel)
    if store.load() != initial:
        raise ProjectConflict('Project changed during facial revision; old master remains authoritative')
    _cancel(cancel)
    revision = None
    if proof['geometry_changed'] or proof['target_values_changed']:
        revision = stage_unverified_master(
            store, output, authorized_source_root=workdir, expected_project_id=expected_project_id,
            expected_revision=expected_revision, expected_sha256=face_sha, cancel=cancel)
    return FaceRevisionResult(revision.project if revision else initial, revision,
                              {**proof, 'original_master_preserved': True,
                               'authoritative_master_sha256': face_sha if revision else source_sha},
                              request.job_id, verification.job_id)
