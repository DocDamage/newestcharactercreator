"""Create a separate saved project for explicit target-action attachment."""
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog, QInputDialog

from ucc.core.errors import ProjectStorageError, UCCError


KIND = 'private_target_copy'


def _eligible(window) -> bool:
    controller = window.controller
    if window.jobs.busy or not controller.has_project or controller.dirty:
        return False
    project = controller.require_project()
    return (project.family == 'humanoid.v1' and project.base_provider == 'mpfb'
            and project.master_blend is not None)


def refresh_private_target_copy(window) -> None:
    window.private_target_copy_action.setEnabled(_eligible(window))


def start_private_target_copy(window) -> None:
    if not _eligible(window):
        window._error('Open a saved MPFB character with an editable master')
        return
    controller = window.controller
    store = controller.store
    project = controller.require_project()
    folder = QFileDialog.getExistingDirectory(window, 'Choose parent folder for the separate target copy')
    if not folder:
        return
    name, accepted = QInputDialog.getText(
        window, 'Create separate target copy', 'New project folder name', text=store.root.name + '-target')
    if not accepted:
        return
    if not name or name in {'.', '..'} or any(character in name for character in '<>:"/\\|?*'):
        window._error('Enter one new folder name for the separate target copy')
        return
    if not _eligible(window) or controller.store is not store or controller.require_project() != project:
        window._error('The original saved character changed while choosing the target folder')
        return
    destination = Path(folder) / name
    cancel = Event()

    def copy_saved_project() -> Path:
        from ucc.jobs.private_target_copy import create_private_target_copy

        try:
            return create_private_target_copy(store, expected_project=project, destination=destination, cancel=cancel)
        except (UCCError, OSError) as error:
            notes = getattr(error, '__notes__', ())
            if notes:
                raise ProjectStorageError('\n'.join((str(error), *notes))) from error
            raise

    window._submit(KIND, copy_saved_project, cancel=cancel)


def finish_private_target_copy(window, result: Path) -> None:
    window.log.setPlainText(
        f'Saved separate target project at {result}\nOpen that folder before attaching the reviewed idle.')
    window.statusBar().showMessage('Separate target copy saved')
