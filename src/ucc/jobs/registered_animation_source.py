"""Guarded Blender preparation for one private registered animation target."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from types import ModuleType
from typing import Callable

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import checked_sha
from ucc.export.godot_candidate_contract import EngineInputPermission, canonical_bytes
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.export.godot_registered_binding import project_registered_native_proofs
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .godot_registered_native_inputs import _registered_sources
from .godot_registered_runtime_files import hash_file, read_metadata
from .protocol import JobRequest
from .runner import BlenderJobRunner
from .target_action import load_target_action, read_target_action_binding
from .target_action_context import operation_budget, protected, require_review, source_review
from .target_action_storage import ancestry, source_state
from .worker_resources import worker_dependency_files


_MAX_SOURCE_BYTES = 512 * 1024**2


@dataclass(frozen=True, slots=True)
class PreparedRegisteredAnimationSource:
    directory: Path
    fbx_path: Path
    verification_sha256: str
    binding_sha256: str
    stage_job_id: str
    verify_job_id: str


def prepare_registered_animation_source(store: ProjectStore, *, engine: str, recipe: ModuleType,
        selection: RegisteredInputSelection, permissions: tuple[EngineInputPermission, ...],
        database_path: Path, blender_exe: Path, worker_script: Path, cancel: Event | None = None,
        timeout_s: float = 1800, progress: Callable[[str], None] | None = None) -> PreparedRegisteredAnimationSource:
    """Independently reopen the saved Blender reference and its exported FBX."""
    if type(store) is not ProjectStore or type(engine) is not str or engine not in {'unity', 'unreal'}:
        raise ValidationError('This registered source requires an admitted engine and saved character')
    label = engine.title()
    database = protected(Path(database_path))
    blender = protected(Path(blender_exe))
    worker = protected(Path(worker_script))
    with operation_budget(cancel, timeout_s) as budget:
        prepared = load_target_action(store, database_path=database, **selection.loader_args(),
                                      cancel=budget.cancel, timeout_s=min(300, budget.remaining()))
        binding = read_target_action_binding(store, selection.binding_sha256, cancel=budget.cancel)
        project = store.load()

        def reviewed_source():
            review = source_review(store, database, selection.clip_id, selection.project_id, selection.revision,
                selection.loader_args()['expected_master_blend'], selection.project_sha256, budget)
            require_review(review, selection.source_binding_sha256, selection.catalog_record_sha256)
            if review.source != binding.source or review.policy.ue_only:
                raise ValidationError(f'The current registered motion is unavailable for the selected {label} use')
            return review

        review = reviewed_source()
        project_registered_native_proofs(binding, selected_binding_sha256=selection.binding_sha256,
            project=project, project_sha256=selection.project_sha256, current_source=review.source)
        permission_map = {row.asset_id: row for row in permissions}
        motion = next(role for role in permission_map if role.startswith('motion:'))
        sources = _registered_sources(store, project, budget.cancel)
        sources[motion] = review.source_path
        if set(sources) != set(permission_map):
            raise ValidationError(f'{label} permissions must match the exact consumed source roles')
        for role, path in sources.items():
            permission = permission_map[role]
            permission.require_engine(engine)
            if hash_file(path, _MAX_SOURCE_BYTES, budget)[0] != permission.source_sha256:
                raise ValidationError(f'{label} permission differs from the exact consumed source bytes')
            if role not in {'master', motion}:
                manifest, _, _ = read_metadata(path, 4 * 1024**2, budget,
                                               expected_sha256=permission.source_sha256)
                rights = manifest.get('rights', {})
                if type(rights) is not dict or rights.get('ue_only'):
                    raise ValidationError(f'A consumed source has unsupported {label} rights')
                if rights.get('no_ai') and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                    raise ValidationError(f'{label} permission must preserve the source NoAI restriction')
        if review.policy.no_ai and (not permission_map[motion].policy.no_ai or permission_map[motion].policy.ai_input_allowed):
            raise ValidationError(f'{label} permission must preserve the motion NoAI restriction')

        paths = {
            'candidate.blend': sources['master'],
            'review_motion.blend': prepared.directory/'body_first/review_motion.blend',
            'target_timeline.json': prepared.directory/'body_first/target_timeline.json',
            'source_snapshot.json': prepared.directory/'source_snapshot.json',
            'native_mapping.json': prepared.directory/'native_mapping.json',
            'target_binding.json': prepared.binding_path,
        }
        options = {recipe.INPUT_FILES[name]: hash_file(path, _MAX_SOURCE_BYTES, budget)[0]
                   for name, path in paths.items()}
        options['source_sha256'] = permission_map[motion].source_sha256
        recipe.validate_binding(binding, options)
        baseline = source_state(store, budget)
        guards = dict(prepared.watched_inputs)
        guards.update({path: permission_map[role].source_sha256 for role, path in sources.items()})
        guards.update({path: hash_file(path, _MAX_SOURCE_BYTES, budget)[0]
                       for path in {blender, worker, *worker_dependency_files(worker)}})
        authorities = ancestry(guards)
        database_identity = identity(database)[:2]

        def guard() -> None:
            budget.check()
            if (reviewed_source() != review or store.load() != project or source_state(store, budget) != baseline
                    or identity(protected(database))[:2] != database_identity
                    or any(identity(protected(path)) != stamp for path, stamp in authorities.items())
                    or any(hash_file(path, _MAX_SOURCE_BYTES, budget)[0] != digest for path, digest in guards.items())):
                raise ProjectConflict(f'{label} animation source, authorization context or worker changed')

        def verify_files(folder: Path, files: dict) -> None:
            if type(files) is not dict or set(files) != set(recipe.OUTPUT_LIMITS):
                raise ValidationError(f'{label} animation worker returned an incomplete artifact inventory')
            for name, digest in files.items():
                actual, length = hash_file(folder/name, recipe.OUTPUT_LIMITS[name], budget)
                if (actual != digest or not length
                        or (name in recipe.REFERENCES or name in recipe.CORRECTION_INPUTS) and length != recipe.OUTPUT_LIMITS[name]):
                    raise ProjectStorageError(f'{label} animation worker artifact differs from its exact report')

        runner = BlenderJobRunner(blender, safe_directory(store, '.ucc-jobs', create=True), worker)
        guard()
        if progress is not None:
            progress(f'STAGE_REGISTERED_{engine.upper()}_ANIMATION')
        stage = JobRequest.new(recipe.STAGE, input_project='candidate.blend', options=options)
        staged, staged_folder = runner.run(stage, staged_inputs=paths, cancel=budget.cancel, timeout_s=budget.remaining())
        guard()
        details = staged.details
        files = details.get('files')
        if details.get('policy') != recipe.POLICY or details.get('engine_import_verified') is not False:
            raise ValidationError(f'{label} source stage returned an unexpected verification scope')
        verify_files(staged_folder, files)
        followup = JobRequest.new(recipe.VERIFY, input_project='candidate.blend',
            options=options | {recipe.output_option(name): digest for name, digest in files.items()})
        if progress is not None:
            progress(f'REOPEN_REGISTERED_{engine.upper()}_ANIMATION')
        reopened, result = runner.run(followup, staged_inputs=paths | {name: staged_folder/name for name in files},
                                       cancel=budget.cancel, timeout_s=budget.remaining())
        guard()
        verify_files(staged_folder, files)
        verify_files(result, files)
        details = reopened.details
        verification, _, digest = read_metadata(result/recipe.VERIFY_REPORT, 256 * 1024, budget,
            expected_sha256=checked_sha(details.get('verification_sha256')))
        readback_sha, readback_length = hash_file(result/recipe.FBX_SNAPSHOT, 64 * 1024**2, budget)
        expected_report = recipe.source_report(options, files, fbx_readback_sha256=readback_sha)
        if (details.get('policy') != recipe.POLICY or details.get('engine_import_verified') is not False
                or details.get('files') != files or details.get('verification_sha256') != digest
                or not readback_length or details.get('fbx_readback_sha256') != readback_sha
                or canonical_bytes(verification) != canonical_bytes(expected_report)):
            raise ValidationError(f'{label} animation reopen returned an unexpected verification scope')
        guard()
        return PreparedRegisteredAnimationSource(result, result/recipe.FBX, digest, selection.binding_sha256,
                                                 stage.job_id, followup.job_id)
