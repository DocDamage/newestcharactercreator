"""Two fresh read-only neutral-key inspections; not source-adoption permission."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.expressions import POLICY, TARGETS, is_sha256
from ucc.core.storage import ProjectStore
from .expression_keys import installed_expression_inputs
from .expression_storage import check_cancel, safe_directory
from .geometry_evidence import EvidenceError
from .master_preview import _master_file, _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class CheckedExpressionMaster:
    master: Path
    sha256: str
    observed: dict
    report: Path
    report_sha256: str
    stage_job_id: str
    reopen_job_id: str


def _inspect_expression_copy(store: ProjectStore, *, master_blend: str, blender_exe: Path,
                              worker_script: Path, mpfb_data_dir: Path, cancel: Event | None = None,
                              timeout_s: float = 300) -> CheckedExpressionMaster:
    """For already-admitted sources or a private transaction's worker output.

    Callers must separately establish source provenance. Twelve valid keys do
    not authorize adopting an arbitrary externally rehashed master.
    """
    if type(timeout_s) not in (int, float) or not .05 <= timeout_s <= 3600 or not math.isfinite(timeout_s):
        raise ValidationError('Expression inspection timeout_s is outside the supported range')
    executable, script = Path(blender_exe), Path(worker_script)
    if any(p.is_symlink() or not p.is_file() for p in (executable, script)):
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    check_cancel(cancel); source, sha = _master_file(store, master_blend)
    if _digest(source, cancel) != sha:
        raise ProjectStorageError('Prepared expression master differs from its immutable identity')
    assets = installed_expression_inputs(mpfb_data_dir, cancel)
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    inputs = jobs/('expression-inspection-'+str(uuid4())); inputs.mkdir(exist_ok=False)
    recipe = inputs/'expression_recipe.json'
    with recipe.open('x', encoding='utf-8') as stream:
        json.dump(build_expression_recipe(sha), stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    options = {'master_sha256': sha, 'recipe_sha256': _digest(recipe, cancel),
               **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
    staged = {'candidate.blend': source, 'expression_recipe.json': recipe,
              **{t.staged_name: assets[t.staged_name] for t in TARGETS}}
    hashes = {'candidate.blend': sha, 'expression_recipe.json': options['recipe_sha256'],
              **{t.staged_name: t.sha256 for t in TARGETS}}
    runner = BlenderJobRunner(executable, jobs, script); records = []; requests = []; directories = []
    for _ in range(2):
        request = JobRequest.new('inspect_mpfb_expression_keys', input_project='candidate.blend', options=options)
        result, directory = runner.run(request, staged_inputs=staged, timeout_s=timeout_s, cancel=cancel)
        records.append(result.details); requests.append(request); directories.append(directory)
    proof = records[0]
    fields = {'schema_version', 'policy', 'master_sha256', 'recipe_sha256', 'blender_version', 'observation',
              'expression_keys_sha256', 'samples', 'race_weights', 'scale_factor', 'sample_count',
              'exact_neutral_restoration', 'visual_quality_approved', 'engine_import_verified'}
    if (type(proof) is not dict or set(proof) != fields or type(proof['schema_version']) is not int
            or proof['schema_version'] != 1 or proof['policy'] != POLICY or proof['master_sha256'] != sha
            or proof['recipe_sha256'] != options['recipe_sha256'] or type(proof['sample_count']) is not int
            or proof['sample_count'] != 20 or not is_sha256(proof['expression_keys_sha256'])
            or proof['exact_neutral_restoration'] is not True or proof['visual_quality_approved'] is not False
            or proof['engine_import_verified'] is not False or type(proof['observation']) is not dict
            or type(proof['blender_version']) is not str or not proof['blender_version'].startswith('5.3.')
            or canonical_digest(proof) != canonical_digest(records[1])):
        raise EvidenceError('Two independent expression inspections disagree on the exact neutral master')
    for name, path in staged.items():
        for candidate in (path, *(d/name for d in directories)):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate, cancel) != hashes[name]:
                raise ProjectStorageError('Prepared expression inspection input changed: '+name)
    installed_expression_inputs(mpfb_data_dir, cancel); check_cancel(cancel)
    report = inputs/'inspection.json'
    with report.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return CheckedExpressionMaster(source, sha, proof, report, _digest(report, cancel),
                                    requests[0].job_id, requests[1].job_id)
