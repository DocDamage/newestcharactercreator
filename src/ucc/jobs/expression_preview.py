"""Private saved facial Action/cache, independently verified without publication."""
from dataclasses import dataclass
import json
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.expression_clip import CLIP_POLICY, build_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import TARGETS
from ucc.core.storage import ProjectStore
from ucc.preview.expression_cache import read_expression_cache, read_json, validate_clip_report
from ucc.preview.motion_cache import MotionCache
from .expression_keys import installed_expression_inputs
from .expression_storage import check_cancel, safe_directory
from .expression_verification import verify_saved_expression_master, registered_expression_source
from .geometry_evidence import EvidenceError
from .master_preview import _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class ExpressionPreview:
    cache: MotionCache
    project_id: str
    revision: int
    master_blend: str
    master_sha256: str
    library_sha256: str
    clip_sha256: str
    bindings: dict
    observed: dict
    workdir: Path
    verify_dir: Path
    stage_job_id: str
    reopen_job_id: str


def preview_saved_expressions(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
                               mpfb_data_dir: Path, expected_project_id: str, expected_revision: int,
                               expected_master_blend: str, cancel: Event | None = None,
                               timeout_s: float = 300) -> ExpressionPreview:
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before facial preview preparation')
    check_cancel(cancel); metadata_sha = _digest(store.file, cancel)
    checked = verify_saved_expression_master(store, blender_exe=blender_exe, worker_script=worker_script,
        mpfb_data_dir=mpfb_data_dir, expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_master_blend=initial.master_blend, cancel=cancel, timeout_s=timeout_s)
    clip = build_expression_clip(initial, checked.sha256)
    assets = installed_expression_inputs(mpfb_data_dir, cancel)
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    inputs = jobs/('expression-preview-'+str(uuid4())); inputs.mkdir(exist_ok=False)
    recipe = inputs/'expression_clip.json'
    with recipe.open('x', encoding='utf-8') as stream:
        json.dump(clip, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    options = {'master_sha256': checked.sha256, 'clip_sha256': _digest(recipe, cancel),
               **{t.role+'_'+t.family+'_sha256': t.sha256 for t in TARGETS}}
    staged = {'candidate.blend': checked.master, 'expression_clip.json': recipe,
              **{t.staged_name: assets[t.staged_name] for t in TARGETS}}
    hashes = {'candidate.blend': checked.sha256, 'expression_clip.json': options['clip_sha256'],
              **{t.staged_name: t.sha256 for t in TARGETS}}
    runner = BlenderJobRunner(Path(blender_exe), jobs, Path(worker_script))
    request = JobRequest.new('stage_mpfb_expression_clip', input_project='candidate.blend', options=options)
    stage, workdir = runner.run(request, staged_inputs=staged, timeout_s=timeout_s, cancel=cancel)
    outputs = {'expression_motion.blend': 'motion_sha256', 'expression_motion.json': 'motion_report_sha256',
               'expression_skin.bin': 'cache_sha256', 'expression_skin.json': 'cache_manifest_sha256'}
    bindings = dict(options)
    for name, field in outputs.items():
        path = workdir/name
        if path.is_symlink() or not path.is_file():
            raise EvidenceError('Expression stage produced no actual complete output: '+name)
        bindings[field] = _digest(path, cancel)
    expected_stage = {'schema_version': 1, 'policy': CLIP_POLICY, 'master_sha256': checked.sha256,
        'clip_sha256': options['clip_sha256'], **{k: bindings[k] for k in outputs.values()}, 'frame_count': 25,
        'visual_quality_approved': False, 'engine_import_verified': False}
    if canonical_digest(stage.details) != canonical_digest(expected_stage):
        raise EvidenceError('Expression stage is not bound to its complete saved Action/cache files')
    verification = JobRequest.new('verify_mpfb_expression_clip', input_project='candidate.blend', options=bindings)
    verified, verify_dir = runner.run(verification, staged_inputs={**staged,
        **{name: workdir/name for name in outputs}}, timeout_s=timeout_s, cancel=cancel)
    report = read_json(workdir/'expression_motion.json', bindings['motion_report_sha256'], 4*1024*1024)
    validate_clip_report(report, bindings)
    if report['neutral_state_sha256'] != canonical_digest(checked.observed['observation']):
        raise EvidenceError('Expression preview changed the independently verified neutral character')
    cache = read_expression_cache(workdir, bindings, verified.details, report, cancel_check=lambda: check_cancel(cancel))
    for name, path in {**staged, **{name: workdir/name for name in outputs}}.items():
        expected = hashes[name] if name in hashes else bindings[outputs[name]]
        for candidate in (path, workdir/name, verify_dir/name):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate, cancel) != expected:
                raise ProjectStorageError('Expression preview input/output changed before display: '+name)
    installed_expression_inputs(mpfb_data_dir, cancel)
    if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
        raise ProjectConflict('Project changed during facial preview; saved project remains authoritative')
    registered_expression_source(store, initial, cancel); check_cancel(cancel)
    return ExpressionPreview(cache, initial.project_id, initial.revision, initial.master_blend, checked.sha256,
        initial.expression.library_sha256, options['clip_sha256'], bindings, verified.details,
        workdir, verify_dir, request.job_id, verification.job_id)
