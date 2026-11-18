"""Explicit saved Action → private sprite dialog → four-worker host API."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from ucc.core.body_sprites import body_sprite_sources
from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.body_sprite_provenance import OriginalMotionProvenance

KINDS = frozenset({'body_sprite_review', 'body_sprite_origin', 'body_sprite_export'})


@dataclass(frozen=True, slots=True)
class BodySelection:
    context: object
    review: object
    binding_sha256: str
    token: object


@dataclass(frozen=True, slots=True)
class BodyReview:
    token: object
    binding: TargetActionBinding
    snapshot: bytes


@dataclass(frozen=True, slots=True)
class OriginReview:
    token: object
    path: Path
    provenance: OriginalMotionProvenance
    summary: str


@dataclass(frozen=True, slots=True)
class BodyCompleted:
    token: object
    result: object


def _current(window, selection):
    from .target_action_workflow import _current as current_target
    current_target(window, selection.context)
    if window._catalog_path() != selection.context.database:
        raise ProjectConflict('The selected catalog changed during private sprite work')
    if getattr(window, '_body_sprite_selection', None) is not selection:
        raise ProjectConflict('The selected saved binding was superseded')


def _source_review(selection, cancel, timeout):
    from ucc.jobs.target_action import review_target_action_source
    ctx = selection.context
    current = review_target_action_source(ctx.store, database_path=ctx.database,
        clip_id=selection.review.source.clip_id, expected_project_id=ctx.project.project_id,
        expected_revision=ctx.project.revision, expected_master_blend=ctx.project.master_blend,
        expected_project_sha256=ctx.project_sha256, cancel=cancel, timeout_s=timeout)
    if current != selection.review:
        raise ProjectConflict('The selected motion source or current policy changed; reopen its saved binding')
    return current


def start_body_sprite(window, context, review, binding_sha256):
    if window.jobs.busy or not binding_sha256:
        raise ValidationError('Explicitly select a saved binding while no other local task is running')
    clear_body_sprite(window)
    selection = BodySelection(context, review, binding_sha256, object())
    window._body_sprite_selection = selection
    _current(window, selection)
    from .target_action_workflow import _submit
    def operation(cancel, progress):
        from ucc.jobs.target_action import load_target_action, read_target_action_binding
        ctx = selection.context
        loaded = load_target_action(ctx.store, binding_sha256=binding_sha256,
            database_path=ctx.database, expected_project_id=ctx.project.project_id,
            expected_revision=ctx.project.revision, expected_master_blend=ctx.project.master_blend,
            expected_project_sha256=ctx.project_sha256, expected_clip_id=review.source.clip_id,
            expected_source_binding_sha256=review.source.source_binding_sha256,
            expected_catalog_record_sha256=review.source.catalog_record_sha256,
            cancel=cancel, timeout_s=300, progress=progress)
        binding = read_target_action_binding(ctx.store, binding_sha256, cancel=cancel)
        if loaded.binding_sha256 != binding.sha256 or loaded.project_sha256 != ctx.project_sha256:
            raise ProjectConflict('Saved sprite binding changed during complete retained-proof loading')
        body_sprite_sources(ctx.project, binding)
        return BodyReview(selection.token, binding, canonical_bytes(ctx.project.to_dict()))
    _submit(window, 'body_sprite_review', operation, progress=True)


def _origin(window, path, owner=None):
    selection = getattr(window, '_body_sprite_selection', None)
    dialog = getattr(window, '_body_sprite_dialog', None)
    if (selection is None or dialog is None or (owner is not None and owner is not dialog)
            or dialog.context_token is not selection.token):
        return
    try:
        _current(window, selection)
        if window.jobs.busy:
            raise ValidationError('Wait for the current origin review to finish')
        requested = Path(path)
        token = selection.token
        binding = window._body_sprite_binding
        window._body_sprite_origin_path = requested
        from .target_action_workflow import _submit
        def operation(cancel, _progress):
            from ucc.jobs.body_sprite_provenance import review_original_motion_record
            from ucc.jobs.target_action_context import operation_budget
            with operation_budget(cancel, 30) as budget:
                current = _source_review(selection, budget.cancel, budget.remaining())
                origin, metadata = review_original_motion_record(requested,
                    binding, current.policy, budget)
                label = ('Independently checked original-motion record' if metadata['record_format'] ==
                    'INDEPENDENT_PREPARED_NATIVE300_AUDIT_V1' else 'Original-motion declaration record')
                summary = (label+'\n'
                    'This metadata declaration does not prove human authorship or grant sprite rights.\n'
                    'Review each exact rendered source separately for this private use.')
                if metadata['original_script_exit_success'] is False:
                    summary += '\nThe historical original script failed; its qualified independent full-clip recheck is retained.'
                return OriginReview(token, requested, origin, summary)
        _submit(window, 'body_sprite_origin', operation)
        dialog.set_busy(True)
    except (UCCError, OSError, ValueError) as error:
        dialog.set_origin_error(str(error), context_token=selection.token)


def _render(window, dialog):
    selection = getattr(window, '_body_sprite_selection', None)
    if (selection is None or getattr(window, '_body_sprite_dialog', None) is not dialog
            or dialog.context_token is not selection.token):
        return
    try:
        _current(window, selection)
        if window.jobs.busy:
            raise ValidationError('Another local task is still running')
        request = dialog.request()
        origin = dialog.origin_review()
        if (request.target_binding != window._body_sprite_binding
                or request.project_snapshot_json != canonical_bytes(selection.context.project.to_dict())
                or type(origin) is not OriginalMotionProvenance):
            raise ValidationError('Sprite request differs from the reviewed saved character and origin')
        from ucc.jobs.export_destination import plan_destination
        destination = plan_destination(dialog.destination_path(), selection.context.store.root)
        executable = window._blender_executable
        if executable is None or executable.is_symlink() or not executable.is_file():
            chosen, _ = QFileDialog.getOpenFileName(window, 'Choose installed Blender for private sprite rendering', '', 'All files (*)')
            if not chosen:
                dialog.show()
                return
            executable = Path(chosen)
            if executable.is_symlink() or not executable.is_file():
                raise ValidationError('Choose a regular installed Blender executable')
            window._blender_executable = executable
        from .generation import bundled_worker_path
        worker = bundled_worker_path()
        from .target_action_workflow import _submit
        window._body_sprite_request = request
        window._body_sprite_destination = destination.path
        def operation(cancel, _progress):
            from ucc.jobs.body_sprite_export import export_body_sprite_sample
            from .body_sprite_receipt import verify_body_sprite_delivery
            result = export_body_sprite_sample(selection.context.store, request=request,
                database_path=selection.context.database, destination=destination,
                blender_exe=executable, worker_script=worker,
                original_author_record=origin.record_path, original_author_record_sha256=origin.expected_sha256,
                original_motion_role=origin.motion_role, original_motion_uri_aliases=origin.uri_aliases,
                cancel=cancel, timeout_s=2400)
            try:
                verify_body_sprite_delivery(result, request, destination.path, cancel)
            except Exception as error:
                error.add_note('Completed private sprite output retained at '+str(destination.path))
                raise
            return BodyCompleted(selection.token, result)
        _submit(window, 'body_sprite_export', operation, progress=True)
        dialog.set_busy(True)
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))
        dialog.show()


def finish_body_sprite(window, result):
    from .target_action_workflow import _close_progress
    _close_progress(window)
    selection = getattr(window, '_body_sprite_selection', None)
    try:
        if selection is None or window.jobs.cancel_requested:
            raise ProjectStorageError('Private sprite operation was cancelled or superseded')
        _current(window, selection)
        kind = window._work_kind
        if kind == 'body_sprite_review':
            if type(result) is not BodyReview or result.token is not selection.token or result.binding.sha256 != selection.binding_sha256:
                raise ValidationError('Unexpected saved sprite binding review result')
            from .body_sprite_dialog import BodySpriteDialog
            window._body_sprite_binding = result.binding
            dialog = BodySpriteDialog(result.snapshot, result.binding, context_token=selection.token, parent=window)
            window._body_sprite_dialog = dialog
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.origin_selected.connect(lambda path: _origin(window, path, dialog))
            dialog.accepted.connect(lambda: _render(window, dialog))
            dialog.rejected.connect(lambda: clear_body_sprite(window))
            dialog.show()
        elif kind == 'body_sprite_origin':
            dialog = getattr(window, '_body_sprite_dialog', None)
            if (type(result) is not OriginReview or result.token is not selection.token or dialog is None
                    or result.path != window._body_sprite_origin_path):
                raise ValidationError('Origin review was superseded')
            dialog.set_origin_review(result.provenance, result.summary, context_token=selection.token)
        elif kind == 'body_sprite_export':
            from ucc.jobs.body_sprite_export import BodySpriteExport
            if (type(result) is not BodyCompleted or result.token is not selection.token
                    or type(result.result) is not BodySpriteExport):
                raise ValidationError('Unexpected private sprite completion')
            request = window._body_sprite_request
            if (result.result.destination != window._body_sprite_destination
                    or result.result.image_count != request.image_count
                    or result.result.selected_target_frames != request.window.target_frames
                    or result.result.selected_source_frames != request.window.source_frames):
                raise ValidationError('Private sprite result differs from the selected output')
            window.log.setPlainText('PRIVATE REGISTERED BODY SPRITE SAMPLE\n'
                f'{request.image_count} transparent images at {request.settings.resolution} pixels.\n'
                f'Target frames {request.window.target_first_frame}–{request.window.target_last_frame}; '
                f'source frames {request.window.source_frames[0]}–{request.window.source_frames[-1]} at 30 fps.\n'
                f'Output: {result.result.destination}\nReceipt SHA-256: {result.result.receipt_sha256}\n'
                'Temporary matte was not adopted. No visual quality, usable-action, engine or distribution approval is granted.')
            clear_body_sprite(window)
        else:
            raise ValidationError('Unexpected private sprite operation')
    except (UCCError, OSError, ValueError, TypeError, AttributeError) as error:
        if type(result) is BodyCompleted:
            window._error('Completed private sprite output retained at '+str(result.result.destination)+'; desktop completion was not accepted. '+str(error))
            clear_body_sprite(window)
        else:
            body_sprite_error(window, str(error))


def body_sprite_error(window, error):
    from .target_action_workflow import _close_progress
    _close_progress(window)
    dialog = getattr(window, '_body_sprite_dialog', None)
    if dialog is not None and window._work_kind == 'body_sprite_origin':
        selection = getattr(window, '_body_sprite_selection', None)
        if selection is not None:
            dialog.set_origin_error(str(error), context_token=selection.token)
        return
    window._error('Private sprite work did not complete. Retained private outputs, if any, are described below.\n'+str(error))
    clear_body_sprite(window)


def refresh_body_sprite(window):
    selection = getattr(window, '_body_sprite_selection', None)
    if selection is not None:
        try:
            _current(window, selection)
        except (UCCError, OSError, ValueError):
            clear_body_sprite(window)


def resume_body_sprite(window):
    dialog = getattr(window, '_body_sprite_dialog', None)
    if dialog is not None:
        dialog.set_busy(False)
    refresh_body_sprite(window)


def clear_body_sprite(window):
    window._body_sprite_selection = None
    window._body_sprite_binding = None
    window._body_sprite_request = None
    window._body_sprite_destination = None
    window._body_sprite_origin_path = None
    if window.jobs.busy and window._work_kind in KINDS:
        cancel = getattr(window, '_target_action_cancel', None)
        if cancel is not None:
            cancel.set()
    dialog = getattr(window, '_body_sprite_dialog', None)
    window._body_sprite_dialog = None
    if dialog is not None:
        dialog.blockSignals(True)
        dialog.invalidate('The saved character or selected motion review was closed')
        dialog.reject()
        dialog.deleteLater()
