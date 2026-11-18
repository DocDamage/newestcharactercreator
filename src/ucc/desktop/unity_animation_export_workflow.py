"""Export the exact saved animation into a verified private Unity project."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QFileDialog, QInputDialog

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import MAX_JSON_BYTES, ProjectStore
from ucc.core.target_action_format import checked_sha
from ucc.jobs.export_destination import ExportDestination, plan_destination
from ucc.jobs.export_guards import bounded_paths
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.godot_registered_runtime_files import FileIdentity, hash_file, read_metadata
from ucc.jobs.target_action_context import Budget, operation_budget, protected
from ucc.jobs.unity_animation_authorization import UnityAnimationAuthorization, load_unity_animation_authorization
from ucc.jobs.unity_animation_engine import MAX_OUTPUT, UNITY_VERSION
from ucc.jobs.unity_animation_export import export_unity_animation
from ucc.jobs.unity_animation_payload import PAYLOAD_DIRECTORIES, PORTABLE_FILES, verify_unity_animation_payload
from ucc.jobs.unity_animation_publication import README, RECEIPT, PublishedUnityAnimation
from .catalog_location import existing_catalog_path
from .generation import bundled_worker_path
from .target_action_preview import _small_digest


KIND = 'unity_animation_export'
TIMEOUT_S = 2400
AUTHORIZATION_LIMIT = 256 * 1024
RECEIPT_LIMIT = 512 * 1024
DELIVERY_NAMES = PORTABLE_FILES | {'README.txt', RECEIPT}
DeliverySeal = tuple[tuple[str, FileIdentity], ...]


@dataclass(frozen=True, slots=True)
class _Context:
    store: ProjectStore
    project: CharacterProject
    database: Path
    authorization_path: Path
    authorization: UnityAnimationAuthorization
    authorization_sha256: str
    destination: ExportDestination


@dataclass(frozen=True, slots=True)
class _Result:
    context: _Context
    published: PublishedUnityAnimation
    seal: DeliverySeal


def refresh_unity_animation_export(window, *, busy: bool = False) -> None:
    window.unity_animation_export_action.setEnabled(not busy and _eligible(window))


def _eligible(window) -> bool:
    controller = window.controller
    if window.jobs.busy or not controller.has_project or controller.dirty or controller.store is None:
        return False
    project = controller.require_project()
    return (project.family == 'humanoid.v1' and project.base_provider == 'mpfb'
            and project.master_blend is not None and bool(project.animations))


def _check_selected_project(store: ProjectStore, project: CharacterProject,
                            authorization: UnityAnimationAuthorization) -> None:
    selected = authorization.selection
    if (selected.project_id != project.project_id or selected.revision != project.revision
            or project.master_blend != f'master/versions/{selected.master_sha256}.blend'
            or selected.clip_id not in project.animations
            or store.load() != project or _small_digest(store.file, MAX_JSON_BYTES) != selected.project_sha256):
        raise ProjectConflict('Choose Unity authorization for this exact saved character and attached animation')


def _check_window(window, store: ProjectStore, project: CharacterProject, database: Path) -> None:
    controller = window.controller
    if (not controller.has_project or controller.store is not store or controller.dirty
            or controller.require_project() != project or existing_catalog_path(window._catalog_path()) != database):
        raise ProjectConflict('The saved character or catalog changed during animated Unity export')


def _read_authorization(path: Path, budget: Budget) -> tuple[UnityAnimationAuthorization, str]:
    if not path.is_absolute() or path.anchor.startswith(('//', '\\\\')):
        raise ValidationError('Choose a local Unity animation authorization file')
    digest, _ = hash_file(path, AUTHORIZATION_LIMIT, budget)
    authorization = load_unity_animation_authorization(path)
    if hash_file(path, AUTHORIZATION_LIMIT, budget)[0] != digest:
        raise ProjectConflict('The private Unity authorization changed while reading')
    return authorization, digest


def _check_authorization(context: _Context, budget: Budget) -> None:
    if _read_authorization(context.authorization_path, budget) != (context.authorization, context.authorization_sha256):
        raise ProjectConflict('The selected Unity authorization changed during export')


def _choose_executable(window, title: str) -> Path | None:
    chosen, _ = QFileDialog.getOpenFileName(window, title, '', 'Executable (*.exe);;All files (*)')
    if not chosen:
        return None
    path = Path(chosen)
    if not path.is_absolute() or path.anchor.startswith(('//', '\\\\')) or not protected(path).is_file():
        raise ValidationError('Choose an existing local installed executable')
    return path


def start_unity_animation_export(window) -> None:
    try:
        if not _eligible(window):
            raise ValidationError('Open and save an MPFB character with an attached animation first')
        store = window.controller.store
        project = window.controller.require_project()
        database = existing_catalog_path(window._catalog_path())
        chosen, _ = QFileDialog.getOpenFileName(window, 'Choose private Unity animation authorization', '',
                                                'Unity authorization (*.json)')
        if not chosen:
            return
        authorization_path = Path(chosen)
        authorization, digest = _read_authorization(authorization_path, Budget(None, 5))
        _check_selected_project(store, project, authorization)
        blender = _choose_executable(window, 'Choose installed Blender executable')
        if blender is None:
            return
        unity = _choose_executable(window, f'Choose installed Unity {UNITY_VERSION} executable')
        if unity is None:
            return
        if blender == unity:
            raise ValidationError('Choose distinct installed Blender and Unity executables')
        parent = QFileDialog.getExistingDirectory(window, 'Choose parent folder for private animated Unity project')
        if not parent:
            return
        name, accepted = QInputDialog.getText(window, 'Private animated Unity project', 'New export folder name')
        if not accepted:
            return
        if not name or name in {'.', '..'} or any(character in name for character in '<>:"/\\|?*'):
            raise ValidationError('Enter one new folder name for the private animated Unity project')
        folder = Path(parent) / name
        if folder.anchor.startswith(('//', '\\\\')) or folder.is_relative_to(store.root) or folder.is_relative_to(database.parent):
            raise ValidationError('Choose a new local export folder outside the saved project and catalog')
        destination = plan_destination(folder, store.root)
        _check_window(window, store, project, database)
        _check_selected_project(store, project, authorization)
        if window.jobs.busy:
            raise ProjectConflict('Another local task started during Unity export selection')
        context = _Context(store, project, database, authorization_path, authorization, digest, destination)
        _check_authorization(context, Budget(None, 5))
        cancel = Event()
        window._unity_animation_export_context = context
        window.log.setPlainText('Preparing private animated Unity export…')
        window._submit(KIND, lambda: _run_export(context, blender, unity, cancel), cancel=cancel)
    except (UCCError, OSError, ValueError, TypeError) as error:
        window._error(str(error))


def _receipt_files(context: _Context, published: PublishedUnityAnimation, budget: Budget) -> dict[str, str]:
    if type(published) is not PublishedUnityAnimation or published.directory != context.destination.path:
        raise ValidationError('Animated Unity result does not match the reviewed export destination')
    record, _, _ = read_metadata(published.directory/RECEIPT, RECEIPT_LIMIT, budget,
                                 expected_sha256=published.receipt_sha256)
    fixed = dict(schema_version=1, policy='UCC_PRIVATE_UNITY_ANIMATION_EXPORT_V1', unity_version=UNITY_VERSION,
                 private_local_only=True, corrective_runtime_verified=True, native_loop_verified=True,
                 material_appearance_approved=False, distribution_review_complete=False)
    if (set(record) != set(fixed) | {'files', 'verification_sha256'}
            or any(type(record[key]) is not type(value) or record[key] != value for key, value in fixed.items())
            or type(record['files']) is not dict or set(record['files']) != PORTABLE_FILES):
        raise ValidationError('The receipt does not confirm the private animated Unity export')
    for digest in (*record['files'].values(), record['verification_sha256'], published.receipt_sha256):
        checked_sha(digest)
    return record['files'] | {'README.txt': sha256(README).hexdigest(), RECEIPT: published.receipt_sha256}


def _delivery_seal(directory: Path, budget: Budget) -> DeliverySeal:
    paths = {}
    for path in bounded_paths(directory, budget.cancel, maximum_entries=128, allowed_directories=PAYLOAD_DIRECTORIES):
        budget.check()
        paths[path.relative_to(directory).as_posix()] = identity(path)
    if set(paths) != DELIVERY_NAMES | PAYLOAD_DIRECTORIES | {'.'}:
        raise ProjectStorageError('Animated Unity output differs from the verified package')
    return tuple(sorted(paths.items()))


def _run_export(context: _Context, blender: Path, unity: Path, cancel: Event) -> _Result:
    try:
        with operation_budget(cancel, TIMEOUT_S) as budget:
            _check_selected_project(context.store, context.project, context.authorization)
            _check_authorization(context, budget)
            published = export_unity_animation(context.store, authorization=context.authorization,
                database_path=context.database, blender_exe=blender, worker_script=bundled_worker_path(),
                unity_exe=unity, unity_executable_sha256=hash_file(unity, MAX_OUTPUT, budget)[0],
                destination=context.destination, authorization_guard=lambda: _check_authorization(context, budget),
                cancel=budget.cancel, timeout_s=budget.remaining())
            try:
                _check_authorization(context, budget)
                expected = _receipt_files(context, published, budget)
                seal = _delivery_seal(published.directory, budget)
                verify_unity_animation_payload(published.directory, expected, budget)
                if _delivery_seal(published.directory, budget) != seal:
                    raise ProjectStorageError('Animated Unity output identity changed during verification')
                budget.check()
            except (UCCError, OSError) as error:
                error.add_note(f'Inspect the retained package at {context.destination.path}.')
                raise
            return _Result(context, published, seal)
    except (UCCError, OSError) as error:
        notes = getattr(error, '__notes__', ())
        if notes:
            raise ProjectStorageError('\n'.join((str(error), *notes))) from error
        raise


def finish_unity_animation_export(window, result: object) -> None:
    context = getattr(window, '_unity_animation_export_context', None)
    window._unity_animation_export_context = None
    if window.jobs.cancel_requested:
        unity_animation_export_error(window, '')
        return
    try:
        if type(result) is not _Result or context is None or result.context is not context:
            raise ValidationError('Animated Unity result does not match the reviewed export')
        _check_window(window, context.store, context.project, context.database)
        _check_selected_project(context.store, context.project, context.authorization)
        budget = Budget(None, 5)
        _check_authorization(context, budget)
        _receipt_files(context, result.published, budget)
        if _delivery_seal(result.published.directory, budget) != result.seal:
            raise ProjectStorageError('Animated Unity output identity changed after verification')
        window.log.setPlainText(
            f'Private animated Unity project verified at {result.published.directory}\n'
            f'Open the project in Unity {UNITY_VERSION} with Direct3D 11. Open Assets/UCC/AnimatedCharacter.unity, '
            'then press Play. A fresh Unity run verified the native animation loop and corrected lit surface.\n'
            'This package is for private local verification. Material appearance and distribution approval are pending.')
        window.statusBar().showMessage('Private animated Unity project verified')
    except (UCCError, OSError, ValueError, TypeError) as error:
        window._error('Animated Unity export could not be confirmed. Inspect the retained result if present. '+str(error))


def unity_animation_export_error(window, error: str) -> None:
    window._unity_animation_export_context = None
    if window.jobs.cancel_requested:
        window.log.setPlainText('Animated Unity export cancelled. Private diagnostic files may remain.\n'+error)
        return
    window._error(error)
