"""Run and independently verify neutral keys without publishing a project."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.expressions import POLICY, TARGETS
from ucc.core.facial import FACE_BASE_SHA256, FACE_RIG_SHA256
from ucc.core.storage import ProjectStore
from .expression_storage import check_cancel, safe_directory, _read_json
from .geometry_evidence import EvidenceError
from .master_preview import _digest, _master_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


def installed_expression_inputs(data_dir: Path, cancel: Event | None = None) -> dict[str, Path]:
    root = Path(data_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValidationError('Select the existing installed MPFB data directory')
    resolved = root.resolve(strict=True)
    entries = {'base.obj': (root/'3dobjs/base.obj', FACE_BASE_SHA256),
               'rig.default.json': (root/'rigs/standard/rig.default.json', FACE_RIG_SHA256),
               **{t.staged_name: (root/t.source_relative, t.sha256) for t in TARGETS}}
    for name, (path, expected) in entries.items():
        check_cancel(cancel)
        if (path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(resolved)
                or _digest(path, cancel) != expected):
            raise ValidationError('Installed MPFB expression data is missing, redirected or changed: '+name)
    return {name: path for name, (path, _) in entries.items()}


@dataclass(frozen=True, slots=True)
class PreparedExpressionKeys:
    source_sha256: str
    scene: Path
    sha256: str
    report: Path
    report_sha256: str
    recipe: dict
    observation_sha256: str
    observed: dict
    stage_job_id: str
    reopen_job_id: str


def stage_expression_keys(store: ProjectStore, *, source_master_blend: str, blender_exe: Path,
                          worker_script: Path, mpfb_data_dir: Path,
                          cancel: Event | None = None, timeout_s: float = 300) -> PreparedExpressionKeys:
    if type(timeout_s) not in (float, int) or not .05 <= timeout_s <= 3600 or not math.isfinite(timeout_s):
        raise ValidationError('Expression timeout_s is outside the supported range')
    executable, script = Path(blender_exe), Path(worker_script)
    if any(p.is_symlink() or not p.is_file() for p in (executable, script)):
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    check_cancel(cancel)
    source, source_sha = _master_file(store, source_master_blend)
    if _digest(source, cancel) != source_sha:
        raise ProjectStorageError('Expression source master differs from its immutable identity')
    assets = installed_expression_inputs(mpfb_data_dir, cancel)
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    inputs = jobs/('expression-inputs-'+str(uuid4())); inputs.mkdir(exist_ok=False)
    recipe = build_expression_recipe(source_sha); recipe_file = inputs/'expression_recipe.json'
    with recipe_file.open('x', encoding='utf-8') as stream:
        json.dump(recipe, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    options = {'master_sha256': source_sha, 'recipe_sha256': _digest(recipe_file, cancel),
               **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
    staged = {'candidate.blend': source, 'expression_recipe.json': recipe_file,
              **{t.staged_name: assets[t.staged_name] for t in TARGETS}}
    hashes = {'candidate.blend': source_sha, 'expression_recipe.json': options['recipe_sha256'],
              **{t.staged_name: t.sha256 for t in TARGETS}}
    runner = BlenderJobRunner(executable, jobs, script)
    request = JobRequest.new('stage_mpfb_expression_keys', input_project='candidate.blend', options=options)
    result, workdir = runner.run(request, staged_inputs=staged, timeout_s=timeout_s, cancel=cancel)
    scene, report = workdir/'expression_human.blend', workdir/'expression_report.json'
    if any(p.is_symlink() or not p.is_file() for p in (scene, report)) or scene.stat().st_size < 1024:
        raise EvidenceError('Expression worker produced no actual prepared master/report')
    scene_sha, report_sha = _digest(scene, cancel), _digest(report, cancel)
    info = _read_json(report, report_sha, 4*1024*1024, cancel)
    fields = {'schema_version', 'policy', 'recipe_sha256', 'source_master_sha256', 'prepared_sha256',
              'blender_version', 'baseline', 'observation', 'samples', 'race_weights', 'scale_factor',
              'visual_quality_approved', 'engine_import_verified'}
    if (type(info) is not dict or set(info) != fields or type(info['schema_version']) is not int
            or info['schema_version'] != 1 or info['policy'] != POLICY
            or info['recipe_sha256'] != options['recipe_sha256'] or info['source_master_sha256'] != source_sha
            or info['prepared_sha256'] != scene_sha or info['visual_quality_approved'] is not False
            or info['engine_import_verified'] is not False or type(info['observation']) is not dict
            or canonical_digest(info) != canonical_digest(result.details)):
        raise EvidenceError('Expression stage lacks complete bound neutral preparation evidence')
    verify_options = dict(options, prepared_sha256=scene_sha, report_sha256=report_sha)
    verification = JobRequest.new('verify_mpfb_expression_keys', input_project='candidate.blend', options=verify_options)
    verified, verify_dir = runner.run(verification, staged_inputs={**staged,
        'expression_human.blend': scene, 'expression_report.json': report}, timeout_s=timeout_s, cancel=cancel)
    expected = {'schema_version': 1, 'policy': POLICY, 'verified_reopen': True,
                'source_master_sha256': source_sha, 'prepared_sha256': scene_sha,
                'recipe_sha256': options['recipe_sha256'], 'reference_samples': 20, 'saved_samples': 20,
                'exact_neutral_restoration': True, 'visual_quality_approved': False, 'engine_import_verified': False}
    if canonical_digest(verified.details) != canonical_digest(expected):
        raise EvidenceError('Independent expression worker did not verify the exact saved neutral master')
    paths = {**staged, 'expression_human.blend': scene, 'expression_report.json': report}
    hashes.update({'expression_human.blend': scene_sha, 'expression_report.json': report_sha})
    for name, path in paths.items():
        for candidate in (path, workdir/name, verify_dir/name):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate, cancel) != hashes[name]:
                raise ProjectStorageError('Expression input/output changed before publication: '+name)
    installed_expression_inputs(mpfb_data_dir, cancel); check_cancel(cancel)
    return PreparedExpressionKeys(source_sha, scene, scene_sha, report, report_sha, recipe,
        canonical_digest(info['observation']), expected, request.job_id, verification.job_id)
