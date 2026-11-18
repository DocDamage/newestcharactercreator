"""Background preparation and explicit reopening of registered target Actions."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QProgressDialog

from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import MAX_JSON_BYTES, ProjectStore
from .generation import bundled_worker_path
from .target_action_dialog import TargetActionDialog
from .target_action_preview import _small_digest, publish_target_action
from .godot_saved_preview_workflow import KINDS as SAVED_GODOT_KINDS
from .target_action_diagnostic_workflow import KINDS as DIAGNOSTIC_KINDS
from .body_sprite_workflow import KINDS as BODY_SPRITE_KINDS
from .authored_idle_loop_workflow import KIND as IDLE_LOOP_REVIEW
from .authored_idle_visual_workflow import KIND as IDLE_VISUAL_DECISION
from .authored_idle_authoring_workflow import KINDS as ORIGINAL_AUTHORING_KINDS, WALK_KINDS


IDLE_MAPPING_SAVE = 'target_action_idle_mapping_save'
REVIEW_KINDS = frozenset({'target_action_review', 'target_action_mapping', IDLE_MAPPING_SAVE})
KINDS = REVIEW_KINDS | {'target_action_prepare', 'target_action_load', IDLE_LOOP_REVIEW, IDLE_VISUAL_DECISION} | (
    SAVED_GODOT_KINDS | DIAGNOSTIC_KINDS | BODY_SPRITE_KINDS | ORIGINAL_AUTHORING_KINDS)
PHASES = {
    'SOURCE_REVIEW': 'Checking the exact registered source and local preview permission...',
    'NEUTRAL_MASTER': 'Independently checking the saved neutral character...',
    'NATIVE_TARGET': 'Preparing and reopening the private target Action...',
    'PLAYBACK_CACHE': 'Preparing all 300 cached skin frames...',
    'RETAINED_VALIDATION': 'Rechecking the complete saved Action and cache proofs...',
    'PERSISTING': 'Saving the immutable private target preview...',
    'RECORD_COMMITTED': 'Private target Action saved; validating preview loading...',
    'COMPLETE': 'Saved record returned; checking the current desktop selection...',
    'TARGET_DIAGNOSTIC_SOURCE_REVIEW': 'Checking current local-preview rights for the selected clip...',
    'TARGET_DIAGNOSTIC_CAPTURE': 'Reading the complete saved clip proof...',
    'TARGET_DIAGNOSTIC_MEASURE': 'Measuring position-only root and endpoint diagnostics...',
    'TARGET_DIAGNOSTIC_FINAL_GUARD': 'Rechecking current proof and catalog authority...',
    'TARGET_DIAGNOSTIC_COMPLETE': 'Checking the diagnostic report against the current selection...',
    'REVIEW_AUTHORED_IDLE_SOURCES': 'Reviewing the exact saved MPFB authoring sources...',
    'AUTHOR_ORIGINAL_IDLE': 'Authoring and independently reopening the private original idle...',
    'REVIEW_AUTHORED_WALK_SOURCES': 'Reviewing the exact saved MPFB sources for original walk...',
    'AUTHOR_ORIGINAL_WALK': 'Authoring and independently reopening the private original walk...',
    'SAVE_AUTHORED_IDLE_PROOF': 'Saving the selected local idle review proof...',
    'SAVE_AUTHORED_IDLE_MAPPING': 'Checking the authored idle proof and saving the exact target mapping...',
}
if TYPE_CHECKING:
    from ucc.jobs.target_action import TargetActionSourceReview, TargetActionSummary


@dataclass(frozen=True, slots=True)
class TargetActionContext:
    store: ProjectStore
    project: CharacterProject
    database: Path
    project_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewedTargetAction:
    review: TargetActionSourceReview
    summaries: tuple[TargetActionSummary, ...]


@dataclass(frozen=True, slots=True)
class ReviewedMapping:
    clip_id: str
    path: Path
    sha256: str


class TargetActionProgress(QObject):
    changed = Signal(str)


class SavedTargetActionRetained(ProjectStorageError):
    """Preserve the backend commit note across BackgroundJobs' string signal."""


def refresh_target_action(window) -> None:
    from .authored_idle_authoring_workflow import refresh_authored_idle_authoring
    refresh_authored_idle_authoring(window)
    from .body_sprite_workflow import refresh_body_sprite
    refresh_body_sprite(window)
    from .target_action_diagnostic_workflow import refresh_target_action_diagnostic
    refresh_target_action_diagnostic(window)
    from .godot_saved_preview_workflow import refresh_saved_godot_preview
    refresh_saved_godot_preview(window)
    action = getattr(window, 'target_action_action', None)
    if action is not None:
        ready = (window.controller.has_project and window.controller.store is not None
                 and not window.controller.dirty and not window.jobs.busy
                 and window.controller.require_project().master_blend is not None
                 and bool(window.controller.require_project().animations))
        action.setEnabled(ready)
    from .target_action_preview import refresh_target_action_preview
    refresh_target_action_preview(window)
    dialog = getattr(window, '_target_action_dialog', None)
    if dialog is not None:
        try:
            _current(window, window._target_action_context)
        except (UCCError, OSError, ValueError):
            dialog.reject()


def _current(window, context):
    if (not window.controller.has_project or window.controller.store is not context.store
            or window.controller.dirty or window.controller.require_project() != context.project
            or _small_digest(context.store.file, MAX_JSON_BYTES) != context.project_sha256):
        raise ProjectConflict('The saved character selection changed during target-preview work')


def _boundary(operation):
    try:
        return operation()
    except Exception as error:
        raw_notes = getattr(error, '__notes__', ())
        committed = next((str(note)[:1500] for note in raw_notes[-8:]
            if str(note).startswith('Completed private target binding retained at ')), None)
        notes = [str(note)[:1500] for note in raw_notes[:7]]
        if committed and committed not in notes:
            notes.append(committed)
        if notes:
            kind = SavedTargetActionRetained if committed else ProjectStorageError
            raise kind(str(error)[:3000] + '\n' + '\n'.join(notes)) from error
        raise


def _submit(window, kind, operation, *, progress=False):
    cancel = Event()
    window._target_action_record_committed = False
    window._target_action_cancel = cancel
    dialog = getattr(window, '_target_action_dialog', None)
    if dialog is not None:
        dialog.set_busy(True)
    signal = TargetActionProgress(window)
    window._target_action_progress_signal = signal
    if progress:
        body = kind in BODY_SPRITE_KINDS
        original_authoring = kind in ORIGINAL_AUTHORING_KINDS
        motion = 'walk' if kind in WALK_KINDS else 'idle'
        label = (f'Checking the saved character and original {motion} authoring inputs…' if original_authoring else
                 'Authenticating the selected source, rendering and independently reopening the private sample…'
                 if kind == 'body_sprite_export' else 'Checking the complete saved Action for private sprite use…'
                 if body else 'Validating private target-preview inputs…')
        box = QProgressDialog(label, 'Cancel operation', 0, 0, window)
        box.setWindowTitle(f'Private original {motion}' if original_authoring else
                           'Private body sprite sample' if body else 'Registered target preview')
        box.setWindowModality(Qt.WindowModality.WindowModal)
        box.setMinimumDuration(0)
        box.canceled.connect(cancel.set)
        window._target_action_progress_dialog = box
        def show_phase(phase):
            if window._target_action_progress_signal is signal:
                if phase == 'RECORD_COMMITTED':
                    window._target_action_record_committed = True
                    box.setCancelButtonText('Cancel preview loading')
                label = PHASES.get(str(phase), 'Checking the private target preview...')
                box.setLabelText(label)
                window.statusBar().showMessage(label)
        signal.changed.connect(show_phase)
        box.show()
    window._submit(kind, lambda: _boundary(lambda: operation(cancel, signal.changed.emit)), cancel=cancel)


def _review(window, clip_id):
    if window.jobs.busy:
        return
    context = window._target_action_context
    try:
        _current(window, context)
        if clip_id not in context.project.animations:
            raise ValidationError('Select an attached registered clip')
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))
        return
    def operation(cancel, _progress):
        from ucc.jobs.target_action import review_target_action_source, list_target_action_bindings
        from ucc.jobs.target_action_context import operation_budget
        with operation_budget(cancel, 30) as budget:
            reviewed = review_target_action_source(
                context.store, database_path=context.database, clip_id=clip_id,
                expected_project_id=context.project.project_id, expected_revision=context.project.revision,
                expected_master_blend=context.project.master_blend, expected_project_sha256=context.project_sha256,
                cancel=budget.cancel, timeout_s=budget.remaining())
            summaries = list_target_action_bindings(context.store, clip_id=clip_id,
                cancel=budget.cancel, timeout_s=budget.remaining())
            budget.check()
        return ReviewedTargetAction(reviewed, summaries)
    _submit(window, 'target_action_review', operation)


def _mapping(window, selected):
    if window.jobs.busy:
        return
    review = window._target_action_dialog.review
    if review is None:
        return
    path = Path(selected)
    def operation(_cancel, _progress):
        _current(window, window._target_action_context)
        if _cancel.is_set():
            raise ProjectStorageError('Mapping review cancelled')
        _, digest = read_native_profile(path, review.source.source_sha256,
                                        review.source.snapshot_sha256, review.master_sha256)
        return ReviewedMapping(review.source.clip_id, path.resolve(), digest)
    _submit(window, 'target_action_mapping', operation)


def _save_authored_mapping(window, dialog):
    from ucc.jobs.export_destination import plan_destination

    review = dialog.review
    if window.jobs.busy or review is None or getattr(window, '_target_action_dialog', None) is not dialog:
        return
    context = window._target_action_context
    try:
        _current(window, context)
        selected, _ = QFileDialog.getOpenFileName(dialog, 'Select authored idle proof', '', 'Idle proof (*.json)')
        if not selected:
            return
        parent = QFileDialog.getExistingDirectory(dialog, 'Choose external authored idle mapping output parent')
        if not parent:
            return
        name, confirmed = QInputDialog.getText(dialog, 'Save authored idle mapping', 'New output folder name',
                                               text='idle-target-mapping')
        if not confirmed:
            return
        if not name or name in {'.', '..'} or '/' in name or '\\' in name:
            raise ValidationError('Enter a single new mapping folder name')
        _current(window, context)
        if (getattr(window, '_target_action_context', None) is not context
                or getattr(window, '_target_action_dialog', None) is not dialog
                or dialog.review is not review or window.jobs.busy or window._catalog_path() != context.database):
            raise ProjectConflict('The selected target or catalog changed while choosing the authored idle proof')
        destination = plan_destination(Path(parent)/name, context.store.root)

        def operation(cancel, progress):
            from ucc.jobs.authored_idle_target_map import publish_authored_idle_target_mapping

            progress('SAVE_AUTHORED_IDLE_MAPPING')
            output = publish_authored_idle_target_mapping(context.store, proof_file=Path(selected),
                database_path=context.database, expected_review=review, destination=destination, cancel=cancel)
            return dialog, context, review, output

        dialog.clear_mapping()
        _submit(window, IDLE_MAPPING_SAVE, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        if getattr(window, '_target_action_dialog', None) is dialog:
            dialog.set_error(str(error))


def start_target_action(window) -> None:
    if window.jobs.busy:
        window._error('Another local task is still running')
        return
    if (not window.controller.has_project or window.controller.store is None or window.controller.dirty
            or window.controller.require_project().master_blend is None
            or not window.controller.require_project().animations):
        window._error('Open a clean saved character with an attached measured source clip first')
        return
    existing = getattr(window, '_target_action_dialog', None)
    if existing is not None:
        existing.raise_()
        return
    project = window.controller.require_project()
    try:
        store = window.controller.store
        if store.load() != project:
            raise ProjectConflict('Saved character differs from the current desktop; reopen it before preparing motion')
        context = TargetActionContext(store, project, window._catalog_path(), _small_digest(store.file, MAX_JSON_BYTES))
        _current(window, context)
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))
        return
    window._target_action_context = context
    selected = window.animations.references.currentItem()
    selected = selected.text() if selected is not None else None
    dialog = TargetActionDialog(project.animations, selected, window)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    window._target_action_dialog = dialog
    dialog.source_requested.connect(lambda clip: _review(window, clip))
    dialog.mapping_requested.connect(lambda path: _mapping(window, path))
    dialog.authored_mapping_requested.connect(lambda: _save_authored_mapping(window, dialog))
    dialog.accepted.connect(lambda: _chosen(window, dialog))
    def rejected():
        cancel = getattr(window, '_target_action_cancel', None)
        if window.jobs.busy and window._work_kind in KINDS and cancel is not None:
            cancel.set()
        if window._target_action_dialog is dialog:
            window._target_action_dialog = None
        dialog.deleteLater()
    dialog.rejected.connect(rejected)
    dialog.show()
    _review(window, dialog.clips.currentText())


def _chosen(window, dialog):
    choice, review = dialog.choice, dialog.review
    window._target_action_dialog = None
    dialog.deleteLater()
    if choice is None or review is None:
        return
    context = window._target_action_context
    try:
        _current(window, context)
        if (choice.operation not in {'prepare', 'load', 'godot_saved', 'diagnostics', 'body_sprites'} or choice.clip_id != review.source.clip_id
                or not choice.local_preview_confirmed):
            raise ValidationError('Confirm the exact reviewed source for this private preview')
        if choice.operation == 'body_sprites':
            from .body_sprite_workflow import start_body_sprite
            start_body_sprite(window, context, review, choice.binding_sha256)
            return
        if choice.operation == 'diagnostics':
            from .target_action_diagnostic_workflow import start_target_action_diagnostic
            start_target_action_diagnostic(window, context, review, choice.binding_sha256,
                                           local_preview_confirmed=choice.local_preview_confirmed)
            return
        from .target_action_diagnostic_workflow import clear_target_action_diagnostic
        clear_target_action_diagnostic(window, 'Another target preview was selected')
        if choice.operation == 'godot_saved':
            from .godot_saved_preview_workflow import start_saved_godot_preview
            start_saved_godot_preview(window, context, review, choice.binding_sha256)
            return
        from .godot_saved_preview_workflow import clear_saved_godot_preview
        clear_saved_godot_preview(window, 'Another target preview was selected')
        executable = None
        worker = None
        if choice.operation == 'prepare':
            executable = window._blender_executable
            if executable is None or executable.is_symlink() or not executable.is_file():
                selected, _ = QFileDialog.getOpenFileName(
                    window, 'Choose installed Blender for private target preview', '',
                    'Blender executable (*.exe);;All files (*)' if os.name == 'nt' else 'All files (*)')
                if not selected:
                    return
                executable = Path(selected)
                if executable.is_symlink() or not executable.is_file():
                    raise ValidationError('Choose a regular installed Blender executable')
                window._blender_executable = executable
            worker = bundled_worker_path()
        window._target_action_selection = (review, choice)
        from .target_action_preview import clear_target_action_preview
        clear_target_action_preview(window)
        def operation(cancel, progress):
            from ucc.jobs.target_action import prepare_target_action, load_target_action
            common = dict(database_path=context.database, expected_project_id=context.project.project_id,
                expected_revision=context.project.revision, expected_master_blend=context.project.master_blend,
                expected_project_sha256=review.project_sha256,
                expected_source_binding_sha256=review.source.source_binding_sha256,
                expected_catalog_record_sha256=review.source.catalog_record_sha256,
                cancel=cancel, progress=progress)
            if choice.operation == 'load':
                return load_target_action(context.store, binding_sha256=choice.binding_sha256,
                    expected_clip_id=choice.clip_id, timeout_s=300, **common)
            return prepare_target_action(context.store, clip_id=choice.clip_id,
                expected_source_sha256=review.source.source_sha256, expected_policy=review.policy,
                mapping_profile=choice.mapping_profile, expected_mapping_sha256=choice.mapping_sha256,
                purpose=choice.purpose, local_preview_confirmed=choice.local_preview_confirmed,
                blender_exe=executable, worker_script=worker, timeout_s=1800, **common)
        _submit(window, 'target_action_' + choice.operation, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))


def finish_target_action(window, result) -> None:
    if window._work_kind in ORIGINAL_AUTHORING_KINDS:
        from .authored_idle_authoring_workflow import finish_authored_idle_authoring
        finish_authored_idle_authoring(window, result)
        return
    if window._work_kind == IDLE_LOOP_REVIEW:
        from .authored_idle_loop_workflow import finish_idle_loop_review
        finish_idle_loop_review(window, result)
        return
    if window._work_kind == IDLE_VISUAL_DECISION:
        from .authored_idle_visual_workflow import finish_visual_decision
        finish_visual_decision(window, result)
        return
    if window._work_kind in BODY_SPRITE_KINDS:
        from .body_sprite_workflow import finish_body_sprite
        finish_body_sprite(window, result)
        return
    if window._work_kind in DIAGNOSTIC_KINDS:
        from .target_action_diagnostic_workflow import finish_target_action_diagnostic
        finish_target_action_diagnostic(window, result)
        return
    if window._work_kind in SAVED_GODOT_KINDS:
        from .godot_saved_preview_workflow import finish_saved_godot_preview
        finish_saved_godot_preview(window, result)
        return
    kind = window._work_kind
    dialog = getattr(window, '_target_action_dialog', None)
    if kind == IDLE_MAPPING_SAVE:
        _finish_authored_mapping(window, dialog, result)
        return
    if kind in {'target_action_review', 'target_action_mapping'}:
        _close_progress(window)
        if dialog is None or window.jobs.cancel_requested:
            return
        try:
            _current(window, window._target_action_context)
            if kind == 'target_action_review' and type(result) is ReviewedTargetAction:
                dialog.set_review(result.review, result.summaries)
            elif kind == 'target_action_mapping' and type(result) is ReviewedMapping:
                if dialog.review is None or result.clip_id != dialog.review.source.clip_id:
                    raise ProjectConflict('Selected registered clip changed during mapping review')
                dialog.set_mapping(result.path, result.sha256)
            else:
                raise ValidationError('Unexpected target-preview review result')
        except (UCCError, OSError, ValueError) as error:
            dialog.set_error(str(error))
        return
    _close_progress(window)
    review, choice = window._target_action_selection
    try:
        if window.jobs.cancel_requested:
            raise ProjectStorageError('Cancellation arrived after a saved target record was returned')
        publish_target_action(window, window._target_action_context, review, result,
                              selected_binding=choice.binding_sha256 if choice.operation == 'load' else None)
        window.log.setPlainText(
            'PRIVATE REGISTERED TARGET ACTION READY\n'
            f'Registered source: {result.clip_id}\n'
            f'Saved binding: {result.binding_sha256}\n'
            f'Saved target Action: {result.directory / "body_first/review_motion.blend"}\n'
            f'Binding record: {result.binding_path}\n'
            'The saved Action and complete cached skin passed independent reopen checks. '
            'Play/Pause and frame seek are available; playback runs once and holds the last frame.\n'
            'Source frames 2–301 correspond to target Action frames 1–300. '
            'Master, project history and source-only registration are unchanged.\n'
            'Editing, usable-action quality, visual quality and engine use remain unapproved.')
    except (UCCError, OSError, ValueError, TypeError, AttributeError) as error:
        from .target_action_preview import clear_target_action_preview
        clear_target_action_preview(window)
        path = getattr(result, 'binding_path', 'the retained private target records')
        window._error(f'Saved private target Action record retained at {path}; preview was not loaded. {error}')


def _close_progress(window):
    progress = getattr(window, '_target_action_progress_dialog', None)
    if progress is not None:
        progress.reset()
        progress.deleteLater()
        window._target_action_progress_dialog = None
    signal = getattr(window, '_target_action_progress_signal', None)
    window._target_action_progress_signal = None
    if signal is not None:
        signal.deleteLater()


def _finish_authored_mapping(window, dialog, result):
    from ucc.jobs.authored_idle_target_map import PublishedAuthoredIdleTargetMapping

    _close_progress(window)
    if type(result) is not tuple or len(result) != 4 or type(result[3]) is not PublishedAuthoredIdleTargetMapping:
        if dialog is not None:
            dialog.set_error('Unexpected authored idle mapping result')
        return
    owner, context, review, output = result
    message = f'Saved reviewed mapping at {output.path}\nMapping SHA-256 {output.sha256}'
    window.log.setPlainText(message)
    if (dialog is not owner or window.jobs.cancel_requested or window._target_action_context is not context
            or dialog.review is not review):
        return
    try:
        _current(window, context)
    except (UCCError, OSError, ValueError) as error:
        dialog.set_error(str(error))
        return
    dialog.status.setText(message + '\nUse Choose reviewed mapping to select it for private preview.')


def target_action_error(window, error: str) -> None:
    if window._work_kind in ORIGINAL_AUTHORING_KINDS:
        from .authored_idle_authoring_workflow import authored_idle_authoring_error
        authored_idle_authoring_error(window, error)
        return
    if window._work_kind == IDLE_LOOP_REVIEW:
        from .authored_idle_loop_workflow import idle_loop_review_error
        idle_loop_review_error(window, error)
        return
    if window._work_kind == IDLE_VISUAL_DECISION:
        from .authored_idle_visual_workflow import visual_decision_error
        visual_decision_error(window, error)
        return
    if window._work_kind in BODY_SPRITE_KINDS:
        from .body_sprite_workflow import body_sprite_error
        body_sprite_error(window, error)
        return
    if window._work_kind in DIAGNOSTIC_KINDS:
        from .target_action_diagnostic_workflow import target_action_diagnostic_error
        target_action_diagnostic_error(window, error)
        return
    if window._work_kind in SAVED_GODOT_KINDS:
        from .godot_saved_preview_workflow import saved_godot_preview_error
        saved_godot_preview_error(window, error)
        return
    _close_progress(window)
    dialog = getattr(window, '_target_action_dialog', None)
    if dialog is not None and window._work_kind in REVIEW_KINDS:
        dialog.set_error(error)
        return
    if window._work_kind in REVIEW_KINDS and window.jobs.cancel_requested:
        window.log.setPlainText('Registered source review cancelled. Existing saved private records are retained.')
        return
    if (getattr(window, '_target_action_record_committed', False)
            or error.startswith('SavedTargetActionRetained:')):
        message = 'Saved private target Action record retained; preview loading did not complete.'
        error = error.removeprefix('SavedTargetActionRetained: ')
    elif window._work_kind == 'target_action_load':
        message = 'Preview loading did not complete. This load does not modify saved target Action records.'
    else:
        message = 'Target preview was not loaded. Saved private records, if any, are retained.'
    window._error(message + '\n' + error)


def resume_target_action(window) -> None:
    from .body_sprite_workflow import resume_body_sprite
    resume_body_sprite(window)
    dialog = getattr(window, '_target_action_dialog', None)
    if dialog is not None:
        dialog.set_busy(False)
    refresh_target_action(window)
