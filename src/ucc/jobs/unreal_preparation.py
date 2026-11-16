"""Guarded source-only Blender stage/fresh reopen for a reviewed Unreal request."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import math
import os
import sys
import time
from ucc.core.errors import ValidationError, ProjectConflict, ProjectStorageError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.storage import ProjectStore
from ucc.export.unreal_contract import UnrealExportRequest, PROFILE, READINESS_FLAGS
from ucc.export.unreal_blender_recipe import POLICY, STAGE, VERIFY, FILES, NORMAL_BYTES, VERIFICATION_FILE, recipe
from ucc.export.godot_candidate_contract import canonical_bytes
from .static_export_sources import static_export_sources
from .skin_material_preparation import _BudgetCancel
from .expression_verification import verify_saved_expression_master
from .expression_storage import safe_directory
from .godot_candidate_inputs import regular_file, identity, read_json
from .master_preview import _digest
from .worker_resources import worker_dependency_files
from .export_guards import bounded_paths, protected_file, source_snapshot, cancel_context, failure_reason
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class PreparedUnrealSource:
    directory: Path
    files: tuple[tuple[str, str], ...]
    verification_sha256: str
    stage_job_id: str
    verify_job_id: str
    request_sha256: str
    workdir: Path

    @property
    def expected_unreal_material_slot_name(self) -> str:
        path = regular_file(self.directory/'unreal_source_stage.json', self.directory, FILES['unreal_source_stage.json'])
        if _digest(path, None) != dict(self.files)['unreal_source_stage.json']:
            raise ProjectStorageError('Unreal source material proof changed')
        value = read_json(path, FILES['unreal_source_stage.json'])['fbx_metadata']['expected_unreal_material_slot_name']
        if type(value) is not str or not 1 <= len(value) <= 160:
            raise ValidationError('Unreal source material slot identity is invalid')
        return value


def prepare_unreal_source(store: ProjectStore, *, request: UnrealExportRequest,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
        cancel: Event | None = None, timeout_s: float = 900) -> PreparedUnrealSource:
    if (type(request) is not UnrealExportRequest or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Unreal source preparation needs a reviewed request and bounded deadline')
    deadline, _ = cancel_context(cancel, time.monotonic()+timeout_s)
    try:
        return _prepare(store, request=request, blender_exe=blender_exe, worker_script=worker_script,
            mpfb_data_dir=mpfb_data_dir, cancel=cancel, deadline=deadline)
    except BaseException as error:
        reason, message = failure_reason(cancel, deadline)
        if reason:
            normalized = ProjectStorageError(message)
            for note in getattr(error, '__notes__', ()):
                normalized.add_note(note)
            raise normalized from error
        raise


def _prepare(store, *, request, blender_exe, worker_script, mpfb_data_dir, cancel, deadline):
    budget = _BudgetCancel(cancel, deadline)
    def remaining():
        reason, message = failure_reason(cancel, deadline)
        if reason:
            raise ProjectStorageError(message)
        return max(.05, deadline-time.monotonic())
    remaining(); initial = store.load()
    review, sources, binding = static_export_sources(store, project_id=request.project_id,
        revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unreal export')
    if (review.project_sha256 != request.project_sha256
            or dict(request.source_bindings) != {s.asset_id:s.sha256 for s in review.sources}):
        raise ProjectConflict('Unreal source review is stale')
    executable = regular_file(Path(blender_exe), Path(blender_exe).parent, 512*1024*1024)
    worker = regular_file(Path(worker_script), Path(worker_script).parent, 256*1024)
    protected = {store.file, *sources.values(), executable, *worker_dependency_files(worker)}
    # In a checkout the core is ordinary Python. In a frozen app its worker copy
    # belongs to the validated explicit worker payload; the enclosing transaction
    # also guards the selected application/toolchain binary.
    host_core = Path(__file__).resolve().parents[1]
    if host_core.is_dir():
        protected.update(p for p in bounded_paths(host_core, budget) if p.is_file() and p.suffix == '.py')
    if getattr(sys, 'frozen', False):
        protected.add(Path(sys.executable))
    data = Path(mpfb_data_dir)
    if (not data.is_absolute() or not data.is_dir() or data.resolve() != data
            or any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)() for p in (data, *data.parents))):
        raise ProjectStorageError('Unreal source needs its selected canonical installed MPFB data directory')
    for path in bounded_paths(data.parent, budget, maximum_entries=65536):
        if path.is_file() and (path.is_relative_to(data) or path.suffix in ('.py', '.toml')):
            protected.add(path)
    for path in protected:
        protected_file(path)
    closure = source_snapshot(store, budget)
    hashes = {path:_digest(path, budget) for path in protected}
    identities = {path:identity(path) for path in protected}
    def guard():
        remaining()
        if store.load() != initial or source_snapshot(store, budget) != closure:
            raise ProjectConflict('Original Unreal source/proof/history changed during preparation')
        for path, expected in hashes.items():
            protected_file(path)
            if identity(path) != identities[path] or _digest(path, budget) != expected:
                raise ProjectStorageError('Unreal source, executable, helper or selected MPFB data changed')
        current, _, current_binding = static_export_sources(store, project_id=request.project_id,
            revision=request.revision, master_blend=initial.master_blend, cancel=budget, purpose='Unreal export')
        if current != review or current_binding != binding:
            raise ProjectConflict('Unreal source closure review became stale')
    guard(); root = safe_directory(store, '.ucc-jobs', create=True)
    work = root/('unreal-source-'+request.job_id); work.mkdir(exist_ok=False)
    work_identity = identity(work)
    journal = work/'preparation.json'
    def status(state, **extra):
        if (work.is_symlink() or getattr(work, 'is_junction', lambda:False)()
                or work.resolve() != work or identity(work) != work_identity):
            raise ProjectStorageError('Unreal source diagnostic root was redirected or replaced')
        temporary = work/'preparation.tmp'
        if temporary.exists() or temporary.is_symlink() or journal.is_symlink():
            raise ProjectStorageError('Unreal source journal path is occupied or redirected')
        temporary_identity = None
        try:
            with temporary.open('xb') as stream:
                temporary_identity = identity(temporary)[:2]
                stream.write(canonical_bytes({'schema_version':1, 'policy':POLICY,
                    'request_sha256':request.sha256, 'state':state,
                    **{name:False for name in READINESS_FLAGS}, **extra}))
            os.replace(temporary, journal)
        finally:
            if (temporary_identity is not None and work.resolve() == work
                    and identity(work) == work_identity and temporary.is_file() and not temporary.is_symlink()
                    and temporary.resolve() == temporary and identity(temporary)[:2] == temporary_identity):
                temporary.unlink()
    try:
        status('VERIFY_SAVED_EXPRESSION_MASTER')
        verify_saved_expression_master(store, blender_exe=executable, worker_script=worker,
            mpfb_data_dir=data, expected_project_id=initial.project_id, expected_revision=initial.revision,
            expected_master_blend=initial.master_blend, cancel=budget, timeout_s=remaining())
        guard()
        document = recipe(request, SkinMaterialSpec.from_dict(binding['spec']))
        recipe_path = work/'unreal_source_recipe.json'
        with recipe_path.open('xb') as stream:
            stream.write(canonical_bytes(document))
        recipe_sha = _digest(recipe_path, budget); recipe_identity = identity(recipe_path)
        def recipe_guard():
            regular_file(recipe_path, work, 256*1024)
            if identity(recipe_path) != recipe_identity or _digest(recipe_path, budget) != recipe_sha:
                raise ProjectStorageError('Unreal source recipe changed')
        options = {'master_sha256':dict(request.source_bindings)['master'], 'recipe_sha256':recipe_sha}
        runner = BlenderJobRunner(executable, work/'workers', worker)
        status('BLENDER_UNREAL_SOURCE_STAGE'); recipe_guard()
        stage_job = JobRequest.new(STAGE, input_project='candidate.blend', options=options)
        staged, folder = runner.run(stage_job, staged_inputs={'candidate.blend':sources['master'],
            'unreal_source_recipe.json':recipe_path}, cancel=budget, timeout_s=remaining())
        guard(); recipe_guard()
        paths = {name:regular_file(folder/name, folder, maximum) for name,maximum in FILES.items()}
        if paths['source_corner_normals.bin'].stat().st_size != NORMAL_BYTES:
            raise ValidationError('Unreal source normals lack complete byte coverage')
        output_hashes = {name:_digest(path, budget) for name,path in paths.items()}
        output_ids = {name:identity(path) for name,path in paths.items()}
        def staged_guard():
            for name,path in paths.items():
                regular_file(path, folder, FILES[name])
                if identity(path) != output_ids[name] or _digest(path, budget) != output_hashes[name]:
                    raise ProjectStorageError('Sealed Unreal staged output changed')
        if staged.details != {'policy':POLICY, 'request_sha256':request.sha256,
                'files':output_hashes, 'engine_import_verified':False}:
            raise ValidationError('Unreal source stage reply differs from its actual outputs')
        status('BLENDER_UNREAL_SOURCE_FRESH_REOPEN'); staged_guard(); recipe_guard()
        verify_job = JobRequest.new(VERIFY, input_project='candidate.blend', options={**options,
            **{name.replace('.', '_')+'_sha256':value for name,value in output_hashes.items()}})
        verified, reopened = runner.run(verify_job, staged_inputs={'candidate.blend':sources['master'],
            'unreal_source_recipe.json':recipe_path, **paths}, cancel=budget, timeout_s=remaining())
        guard(); recipe_guard(); staged_guard()
        proof_path = regular_file(reopened/VERIFICATION_FILE, reopened, 128*1024)
        proof_sha = _digest(proof_path, budget)
        if verified.details != {'policy':POLICY, 'request_sha256':request.sha256,
                'verification_sha256':proof_sha, 'files':output_hashes, 'engine_import_verified':False}:
            raise ValidationError('Fresh Unreal source reply differs from its actual output bindings')
        expected = {'schema_version':1, 'policy':POLICY, 'profile':PROFILE,
            'request_sha256':request.sha256, 'recipe_sha256':recipe_sha,
            'master_sha256':options['master_sha256'], 'files':output_hashes,
            'original_state_preserved':True, 'source_reference_recomputed':True,
            'fresh_original_master_reopened':True, 'exported_fbx_rebuilt':False,
            'project_pointer_changed':False, 'runtime_deformation_verified':False,
            **{name:False for name in READINESS_FLAGS}}
        if canonical_bytes(read_json(proof_path, 128*1024)) != canonical_bytes(expected):
            raise ValidationError('Unreal source verification changed its bindings or capabilities')
        for name,maximum in FILES.items():
            if _digest(regular_file(reopened/name, reopened, maximum), budget) != output_hashes[name]:
                raise ProjectStorageError('Unreal source verification changed sealed output bytes')
        for name,path in {'candidate.blend':sources['master'], 'unreal_source_recipe.json':recipe_path}.items():
            if _digest(regular_file(reopened/name, reopened, 512*1024*1024), budget) != _digest(path, budget):
                raise ProjectStorageError('Unreal source verification changed its staged inputs')
        guard(); staged_guard(); recipe_guard()
        if _digest(proof_path, budget) != proof_sha:
            raise ProjectStorageError('Unreal source verification receipt changed')
        status('UNREAL_SOURCE_VERIFIED_ENGINE_IMPORT_PENDING', files=output_hashes,
            verification_sha256=proof_sha, stage_job_id=stage_job.job_id, verify_job_id=verify_job.job_id)
        remaining()
        return PreparedUnrealSource(reopened, tuple(sorted(output_hashes.items())), proof_sha,
            stage_job.job_id, verify_job.job_id, request.sha256, work)
    except BaseException as error:
        reason, message = failure_reason(cancel, deadline)
        error.add_note('Retained Unreal source diagnostics: '+str(work))
        try:
            status('FAILED', failure_reason=reason or 'error', error=message or str(error)[:1200],
                raw_error_type=type(error).__name__, raw_error=str(error)[:1200])
        except (OSError, ProjectStorageError) as journal_error:
            error.add_note('Unreal source journal failure: '+str(journal_error))
        raise
