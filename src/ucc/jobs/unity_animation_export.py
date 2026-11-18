"""One bounded private Unity export from registered source through fresh playback."""
from collections.abc import Callable
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import checked_sha
from .export_destination import ExportDestination, plan_destination
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .target_action_context import operation_budget, protected, require_review, source_review
from .target_action_storage import source_state
from .unity_animation_authorization import UnityAnimationAuthorization
from .unity_animation_correction import stage_unity_animation_correction
from .unity_animation_engine import verify_unity_native_animation
from .unity_animation_publication import PublishedUnityAnimation, publish_unity_animation
from .unity_animation_source import prepare_unity_animation_source
from .unity_corrected_animation_verification import verify_unity_corrected_animation


def export_unity_animation(store: ProjectStore, *, authorization: UnityAnimationAuthorization,
        database_path: Path, blender_exe: Path, worker_script: Path, unity_exe: Path,
        unity_executable_sha256: str, destination: ExportDestination, authorization_guard: Callable[[], None],
        cancel: Event | None = None, timeout_s: float = 2400,
        progress: Callable[[str], None] | None = None) -> PublishedUnityAnimation:
    """Keep the saved project, selected catalog record and private authority guarded through export."""
    if type(store) is not ProjectStore or type(authorization) is not UnityAnimationAuthorization:
        raise ValidationError('Choose Unity authority for the exact saved animation')
    database = protected(database_path)
    checked_sha(unity_executable_sha256)
    if (type(destination) is not ExportDestination or destination.path.is_relative_to(store.root)
            or destination.path.is_relative_to(database.parent)
            or plan_destination(destination.path, store.root) != destination):
        raise ValidationError('Choose a new Unity destination outside the saved project and catalog')
    with operation_budget(cancel, timeout_s) as budget:
        selection = authorization.selection
        selected_master = selection.loader_args()['expected_master_blend']
        original = source_state(store, budget)
        db_id = identity(database)[:2]

        def review():
            result = source_review(store, database, selection.clip_id, selection.project_id, selection.revision,
                                   selected_master, selection.project_sha256, budget)
            require_review(result, selection.source_binding_sha256, selection.catalog_record_sha256)
            return result

        baseline = review()

        def guard() -> None:
            budget.check()
            authorization_guard()
            if (identity(protected(database))[:2] != db_id or review() != baseline
                    or source_state(store, budget) != original):
                raise ProjectConflict('Saved Unity animation source or current catalog permission changed')

        def report(phase: str) -> None:
            guard()
            if progress is not None:
                progress(phase)

        guard()
        work = safe_directory(store, '.ucc-jobs', create=True)/('private-unity-animated-'+str(uuid4()))
        work.mkdir(exist_ok=False)
        paths = dict(unity_exe=unity_exe, guard=guard, cancel=budget.cancel)
        source = prepare_unity_animation_source(store, authorization=authorization, database_path=database,
            blender_exe=blender_exe, worker_script=worker_script, cancel=budget.cancel,
            timeout_s=budget.remaining(), progress=report)
        native = verify_unity_native_animation(source, **paths, unity_executable_sha256=unity_executable_sha256,
            work=work/'native', timeout_s=budget.remaining(), progress=report)
        report('UNITY_ATTACH_REGISTERED_CORRECTION')
        staged = stage_unity_animation_correction(native, source, **paths,
            work=work/'attach', timeout_s=budget.remaining())
        report('UNITY_VERIFY_CORRECTED_PLAYBACK')
        verified = verify_unity_corrected_animation(staged, source, **paths,
            work=work/'playback', timeout_s=budget.remaining())
        report('UNITY_PUBLISH_PRIVATE_ANIMATION')
        return publish_unity_animation(store, verified, database_path=database, destination=destination,
            guard=guard, cancel=budget.cancel, timeout_s=budget.remaining())
