"""One private Unreal animation export through native playback and publication."""
from pathlib import Path
from tempfile import mkdtemp
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectConflict, UCCError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import checked_sha
from .export_destination import ExportDestination, plan_destination
from .godot_candidate_inputs import identity
from .target_action_context import operation_budget, protected, require_review, source_review
from .target_action_storage import source_state
from .unreal_animation_authorization import UnrealAnimationAuthorization
from .unreal_animation_engine import verify_unreal_native_animation
from .unreal_animation_preview import verify_unreal_preview
from .unreal_animation_publication import PublishedUnrealAnimation, publish_unreal_animation
from .unreal_animation_source import prepare_unreal_animation_source
from .unreal_toolchain import preflight_unreal_toolchain


def export_unreal_animation(store: ProjectStore, *, authorization: UnrealAnimationAuthorization,
        database_path: Path, blender_exe: Path, worker_script: Path, unreal_exe: Path,
        unreal_executable_sha256: str, destination: ExportDestination, authorization_guard: Callable[[], None],
        cancel: Event | None = None, timeout_s: float = 2700,
        progress: Callable[[str], None] | None = None) -> PublishedUnrealAnimation:
    if type(store) is not ProjectStore or type(authorization) is not UnrealAnimationAuthorization:
        raise ValidationError('Choose Unreal authority for the exact saved animation')
    database = protected(database_path)
    checked_sha(unreal_executable_sha256)
    if (type(destination) is not ExportDestination or destination.path.is_relative_to(store.root)
            or destination.path.is_relative_to(database.parent)
            or plan_destination(destination.path, store.root) != destination):
        raise ValidationError('Choose a new Unreal export destination outside the saved project and catalog')
    with operation_budget(cancel, timeout_s) as budget:
        selection = authorization.selection
        master = selection.loader_args()['expected_master_blend']
        original = source_state(store, budget)
        db_identity = identity(database)[:2]

        def review():
            result = source_review(store, database, selection.clip_id, selection.project_id,
                                   selection.revision, master, selection.project_sha256, budget)
            require_review(result, selection.source_binding_sha256, selection.catalog_record_sha256)
            return result

        initial = review()

        def guard() -> None:
            budget.check()
            authorization_guard()
            if (identity(protected(database))[:2] != db_identity or review() != initial
                    or source_state(store, budget) != original):
                raise ProjectConflict('Saved Unreal animation or its current catalog permission changed')

        def report(phase: str) -> None:
            guard()
            if progress is not None:
                progress(phase)

        report('UNREAL_REVIEW_INSTALLED_TOOLCHAIN')
        toolchain = preflight_unreal_toolchain(unreal_exe, cancel=budget.cancel,
                                              timeout_s=min(300, budget.remaining()))
        if dict(toolchain.files).get(str(toolchain.editor_exe)) != unreal_executable_sha256:
            raise ValidationError('Selected Unreal editor differs from the reviewed executable')
        # The editor's DDC and native compiler impose short path limits. Keep
        # these owned retained logs under the local temporary directory.
        work = protected(Path(mkdtemp(prefix='ucc-ue-animation-')).resolve())
        try:
            source = prepare_unreal_animation_source(store, authorization=authorization, database_path=database,
                blender_exe=blender_exe, worker_script=worker_script, cancel=budget.cancel,
                timeout_s=budget.remaining(), progress=report)
            native = verify_unreal_native_animation(source, toolchain=toolchain, work=work/'native',
                guard=guard, cancel=budget.cancel, timeout_s=budget.remaining(), progress=report)
            corrected = verify_unreal_preview(source, native, toolchain=toolchain, work=work/'preview',
                guard=guard, cancel=budget.cancel, timeout_s=budget.remaining(), progress=report)
            report('UNREAL_PUBLISH_PRIVATE_ANIMATION')
            return publish_unreal_animation(store, corrected, database_path=database, destination=destination,
                guard=guard, cancel=budget.cancel, timeout_s=budget.remaining())
        except (UCCError, OSError, ValueError, RuntimeError) as error:
            error.add_note(f'Private Unreal work was retained at {work}')
            raise
