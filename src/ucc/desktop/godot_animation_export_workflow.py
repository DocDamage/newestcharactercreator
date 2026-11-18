"""Export a selected saved animation into a verified private Godot project."""

from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog, QInputDialog

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import MAX_JSON_BYTES, ProjectStore
from ucc.core.target_action_format import checked_sha
from ucc.jobs.export_destination import ExportDestination, plan_destination
from ucc.jobs.godot_candidate_inputs import identity, read_json, regular_file
from ucc.jobs.godot_first_party_animation import prepare_first_party_godot_animation
from ucc.jobs.godot_first_party_authorization import FirstPartyGodotAuthorization, load_first_party_godot_authorization
from ucc.jobs.godot_first_party_playback import (
    MAX_FILE, POLICY, RECEIPT, RUNTIME_FILES, VERIFIED, PublishedFirstPartyGodotPlayback, publish_first_party_godot_playback,
)
from ucc.jobs.godot_registered_runtime_files import FileIdentity, hash_file
from ucc.jobs.target_action_context import operation_budget, protected
from .catalog_location import existing_catalog_path
from .generation import bundled_worker_path
from .target_action_preview import _small_digest


KIND = 'godot_animation_export'
TIMEOUT_S = 1800
RECEIPT_LIMIT = 256 * 1024
PAYLOAD_FILES = RUNTIME_FILES | {'character.tscn', 'playback.json'}
DELIVERY_NAMES = PAYLOAD_FILES | {RECEIPT}
DeliverySeal = tuple[FileIdentity, tuple[tuple[str, FileIdentity], ...]]


@dataclass(frozen=True, slots=True)
class _Context:
    store: ProjectStore
    project: CharacterProject
    database: Path
    authorization_path: Path
    authorization: FirstPartyGodotAuthorization
    destination: ExportDestination


@dataclass(frozen=True, slots=True)
class _Result:
    context: _Context
    published: PublishedFirstPartyGodotPlayback
    diagnostic_receipt_sha256: str
    runtime_provenance_sha256: str
    seal: DeliverySeal


def _eligible(window) -> bool:
    controller = window.controller
    if window.jobs.busy or not controller.has_project or controller.dirty or controller.store is None:
        return False
    project = controller.require_project()
    return (project.family == 'humanoid.v1' and project.base_provider == 'mpfb'
            and project.master_blend is not None and bool(project.animations))


def refresh_godot_animation_export(window) -> None:
    window.godot_animation_export_action.setEnabled(_eligible(window))


def _check_selected_project(store: ProjectStore, project: CharacterProject, authorization: FirstPartyGodotAuthorization) -> None:
    selected = authorization.selection
    if (project.project_id != selected.project_id or project.revision != selected.revision
            or project.master_blend != f'master/versions/{selected.master_sha256}.blend'
            or selected.clip_id not in project.animations
            or store.load() != project or _small_digest(store.file, MAX_JSON_BYTES) != selected.project_sha256):
        raise ProjectConflict('Choose a Godot authorization for this exact saved character and attached animation')


def _check_window(window, store: ProjectStore, project: CharacterProject, database: Path) -> None:
    controller = window.controller
    if (not controller.has_project or controller.store is not store or controller.dirty
            or controller.require_project() != project or window._catalog_path() != database):
        raise ProjectConflict('The saved character or catalog changed during animated Godot export')


def _choose_executable(window, title: str) -> Path | None:
    name, _ = QFileDialog.getOpenFileName(window, title, '', 'Executable (*.exe);;All files (*)')
    if not name:
        return None
    path = Path(name)
    if path.anchor.startswith(('//', '\\\\')) or not protected(path).is_file():
        raise ValidationError('Choose an existing local installed executable')
    return path


def start_godot_animation_export(window) -> None:
    try:
        if not _eligible(window):
            raise ValidationError('Open and save an MPFB character with an attached animation first')
        store = window.controller.store
        project = window.controller.require_project()
        database = existing_catalog_path(window._catalog_path())
        chosen, _ = QFileDialog.getOpenFileName(window, 'Choose private Godot animation authorization', '',
                                                'Godot authorization (*.json)')
        if not chosen:
            return
        authorization_path = Path(chosen)
        authorization = load_first_party_godot_authorization(authorization_path)
        _check_selected_project(store, project, authorization)
        blender = _choose_executable(window, 'Choose installed Blender executable')
        if blender is None:
            return
        console = _choose_executable(window, 'Choose installed Godot 4.7.1 console executable')
        if console is None:
            return
        main = _choose_executable(window, 'Choose matching Godot 4.7.1 main executable')
        if main is None:
            return
        if console == main or console.parent != main.parent or blender in {console, main}:
            raise ValidationError('Choose distinct executable files for Blender and the matching Godot pair')
        parent = QFileDialog.getExistingDirectory(window, 'Choose parent folder for private animated Godot project')
        if not parent:
            return
        name, accepted = QInputDialog.getText(window, 'Private animated Godot project', 'New export folder name')
        if not accepted:
            return
        if not name or name in {'.', '..'} or any(character in name for character in '<>:"/\\|?*'):
            raise ValidationError('Enter one new folder name for the private animated Godot project')
        folder = Path(parent) / name
        if folder.anchor.startswith(('//', '\\\\')) or folder.is_relative_to(store.root) or folder.is_relative_to(database.parent):
            raise ValidationError('Choose a new local export folder outside the saved project and catalog')
        destination = plan_destination(folder, store.root)
        _check_window(window, store, project, database)
        _check_selected_project(store, project, authorization)
        if window.jobs.busy or load_first_party_godot_authorization(authorization_path) != authorization:
            raise ProjectConflict('The selected Godot authorization changed or another task started')
        context = _Context(store, project, database, authorization_path, authorization, destination)
        cancel = Event()
        window._godot_animation_export_context = context
        window._submit(KIND, lambda: run_godot_animation_export(context, blender_exe=blender,
            godot_exe=console, godot_main_exe=main, destination=destination, cancel=cancel), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        window._error(str(error))


def run_godot_animation_export(context: _Context, *, blender_exe: Path, godot_exe: Path,
        godot_main_exe: Path, destination: ExportDestination, cancel: Event) -> _Result:
    def check_authorization() -> None:
        if load_first_party_godot_authorization(context.authorization_path) != context.authorization:
            raise ProjectConflict('The private Godot authorization changed during export')

    try:
        with operation_budget(cancel, TIMEOUT_S) as budget:
            if destination != context.destination:
                raise ProjectConflict('The private Godot export destination differs from the reviewed folder')
            _check_selected_project(context.store, context.project, context.authorization)
            check_authorization()
            worker = bundled_worker_path()
            common = dict(selection=context.authorization.selection, database_path=context.database,
                          permissions=context.authorization.permissions, godot_exe=godot_exe, godot_main_exe=godot_main_exe)
            prepared = prepare_first_party_godot_animation(context.store, **common, blender_exe=blender_exe,
                worker_script=worker, purpose=context.authorization.purpose, private_local_execution_confirmed=True,
                cancel=budget.cancel, timeout_s=budget.remaining())
            check_authorization()
            published = publish_first_party_godot_playback(context.store, **common, result=prepared,
                destination=destination, cancel=budget.cancel, timeout_s=budget.remaining(),
                authorization_guard=check_authorization)
            diagnostic = prepared.diagnostic.receipt_sha256
            provenance = prepared.provenance.sha256
            try:
                check_authorization()
                before = _delivery_identities(published.directory)
                record = _receipt_record(context, published, diagnostic, provenance)
                for name, expected in record['files'].items():
                    if hash_file(published.directory/name, MAX_FILE, budget)[0] != expected:
                        raise ProjectStorageError('Animated Godot output changed after publication')
                if _delivery_identities(published.directory) != before:
                    raise ProjectStorageError('Animated Godot output identity changed after publication')
                budget.check()
            except (UCCError, OSError) as error:
                error.add_note(f'Inspect the retained package at {published.directory}.')
                raise
            return _Result(context, published, diagnostic, provenance, before)
    except (UCCError, OSError) as error:
        notes = getattr(error, '__notes__', ())
        if notes:
            raise ProjectStorageError('\n'.join((str(error), *notes))) from error
        raise


def _delivery_identities(directory: Path) -> DeliverySeal:
    directory = protected(directory)
    names = {entry.name for entry in islice(directory.iterdir(), len(DELIVERY_NAMES) + 1)}
    if names != DELIVERY_NAMES:
        raise ProjectStorageError('Animated Godot output files differ from the verified package')
    return identity(directory), tuple((name, identity(regular_file(directory/name, directory,
        RECEIPT_LIMIT if name == RECEIPT else MAX_FILE))) for name in sorted(names))


def _receipt_record(context: _Context, published: PublishedFirstPartyGodotPlayback,
                    diagnostic: str, provenance: str) -> dict:
    if type(published) is not PublishedFirstPartyGodotPlayback or published.directory != context.destination.path:
        raise ValidationError('Animated Godot result does not match the reviewed export')
    receipt = regular_file(published.directory/RECEIPT, published.directory, RECEIPT_LIMIT)
    record = read_json(receipt, RECEIPT_LIMIT, expected_sha256=published.receipt_sha256)
    expected = {'schema_version', 'policy', 'private_local_only', 'binding_sha256', 'diagnostic_receipt_sha256',
                'runtime_provenance_sha256', 'observation_sha256', 'observed', 'files',
                'distribution_review_complete', 'material_appearance_approved'}
    if (set(record) != expected or type(record['schema_version']) is not int or record['schema_version'] != 1
            or record['policy'] != POLICY or record['private_local_only'] is not True
            or record['binding_sha256'] != context.authorization.selection.binding_sha256
            or record['diagnostic_receipt_sha256'] != diagnostic or record['runtime_provenance_sha256'] != provenance
            or record['observed'] != VERIFIED
            or any(type(record['observed'].get(key)) is not type(value) for key, value in VERIFIED.items())
            or record['distribution_review_complete'] is not False or record['material_appearance_approved'] is not False
            or type(record['files']) is not dict or set(record['files']) != PAYLOAD_FILES):
        raise ValidationError('The receipt does not confirm this private animated Godot export')
    for digest in (*record['files'].values(), record['observation_sha256'], diagnostic, provenance):
        checked_sha(digest)
    return record


def finish_godot_animation_export(window, result: object) -> None:
    context = getattr(window, '_godot_animation_export_context', None)
    window._godot_animation_export_context = None
    try:
        if type(result) is not _Result or context is None or result.context is not context:
            raise ValidationError('Animated Godot result does not match the reviewed export')
        _check_window(window, context.store, context.project, context.database)
        _check_selected_project(context.store, context.project, context.authorization)
        if load_first_party_godot_authorization(context.authorization_path) != context.authorization:
            raise ProjectConflict('The selected Godot authorization changed during export')
        published = result.published
        _receipt_record(context, published, result.diagnostic_receipt_sha256, result.runtime_provenance_sha256)
        if _delivery_identities(published.directory) != result.seal:
            raise ProjectStorageError('Animated Godot output identity changed after verification')
        window.log.setPlainText(
            f'Private animated Godot project verified at {published.directory}\n'
            'Open project.godot in Godot 4.7.1 with Mobile/Vulkan. Fresh Godot playback advanced the native '
            'skeleton across the loop and drew the corrected surface with lit normals.\n'
            'This package is for private local verification. Material appearance and distribution approval are pending.')
        window.statusBar().showMessage('Private animated Godot project verified')
    except (UCCError, OSError, ValueError, TypeError, KeyError) as error:
        window._error('Animated Godot export could not be confirmed. Inspect the retained result if present. '+str(error))


def godot_animation_export_error(window, error: str) -> None:
    window._godot_animation_export_context = None
    if window.jobs.cancel_requested:
        window.log.setPlainText('Animated Godot export cancelled. Private diagnostic files may remain.\n'+error)
        return
    window._error(error)
