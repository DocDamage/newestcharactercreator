"""Existing desktop actions for prepared characters with bound source IDs."""
from pathlib import Path
from threading import Event

from ucc.core.errors import UCCError, ValidationError
from ucc.core.reference_master_intent import supports_referenced_master_intent
from ucc.jobs.face_discovery import discover_face_data
from ucc.jobs.reference_master_revision import ReferencedMasterResult, revise_referenced_master


def run_referenced_master(store, database: Path | None, *, operation: str,
        blender_exe: Path, project_id: str, revision: int, master_blend: str | None,
        cancel: Event) -> ReferencedMasterResult:
    snapshot = store.load()
    if (database is None or not supports_referenced_master_intent(snapshot)
            or snapshot.project_id != project_id or snapshot.revision != revision
            or snapshot.master_blend != master_blend):
        raise ValidationError('Reference-aware editing requires the exact saved prepared character and source catalog')
    from .generation import bundled_worker_path
    script = bundled_worker_path()
    data = discover_face_data(store, blender_exe=blender_exe, worker_script=script, cancel=cancel)
    return revise_referenced_master(store, database, operation=operation,
        blender_exe=blender_exe, worker_script=script, mpfb_data_dir=data,
        expected_project_id=project_id, expected_revision=revision,
        expected_master_blend=master_blend, cancel=cancel)


def finish_referenced_master(window, result: ReferencedMasterResult) -> None:
    try:
        window.controller.accept_saved_reference_master(result.project)
        window._clear_preview(); window.refresh_project()
    except (UCCError, OSError, ValueError) as error:
        window._error('Saved character could not be adopted into this session: '+str(error)); return
    action = ('Saved settings already match; no new master revision.' if result.revision is None
              else 'Saved character changes applied and independently reopened.')
    window.log.setPlainText(action+'\nSource references and expression strengths retained. '
        'The registered hand keeps its selection. Undo/redo restores the master and hand together.\n'
        'Use View saved character to inspect the result. Visual quality and engine imports remain unapproved.')


def show_referenced_master_error(window, error: str) -> None:
    window._clear_preview()
    if 'ProjectConflict' in error and window.controller.store is not None and not window.controller.dirty:
        try:
            window.controller.open(window.controller.store.root); window.refresh_project()
            window.log.setPlainText(error+'\nExternal saved changes were preserved and reloaded.'); return
        except (UCCError, OSError, ValueError):
            pass
    if window.jobs.cancel_requested:
        window.refresh_project()
        window.log.setPlainText('Character operation cancelled. No new result was adopted.'); return
    window._error(error)
