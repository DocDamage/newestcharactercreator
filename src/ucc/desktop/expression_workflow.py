"""Desktop orchestration for real expression workers, never simulated geometry."""
from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from ucc.core.errors import UCCError, ValidationError
from ucc.jobs.expression_preparation import ExpressionPreparation, prepare_saved_expressions
from ucc.jobs.expression_preview import ExpressionPreview, preview_saved_expressions
from ucc.jobs.face_discovery import discover_face_data


def edit_expression(window, name=None, value=None):
    def edit():
        before = window.controller.require_project()
        if name is None: window.controller.reset_expression()
        else: window.controller.set_expression_parameter(name, value)
        if before != window.controller.require_project(): window._clear_preview()
    window._apply(edit)


def start_expression(window, *, prepare=False):
    def start():
        if window.jobs.busy: raise ValidationError('Another local task is still running')
        if window.controller.store is None: raise ValidationError('Open a saved character first')
        if window.controller.dirty: raise ValidationError('Save all settings before preparing an expression preview')
        snapshot = window.controller.require_project()
        if snapshot.master_blend is None or snapshot.animations:
            raise ValidationError('Expressions require an existing MPFB master without attached animations')
        if prepare == (snapshot.expression is not None):
            raise ValidationError('Facial controls are already prepared' if prepare else 'Prepare facial controls first')
        from .hand_workflow import _executable
        executable = _executable(window)
        if executable is None: return
        store = window.controller.store; cancel = Event()
        def run():
            from .generation import bundled_worker_path
            script = bundled_worker_path()
            data = discover_face_data(store, blender_exe=executable, worker_script=script, cancel=cancel)
            operation = prepare_saved_expressions if prepare else preview_saved_expressions
            return operation(store, blender_exe=executable, worker_script=script, mpfb_data_dir=data,
                expected_project_id=snapshot.project_id, expected_revision=snapshot.revision,
                expected_master_blend=snapshot.master_blend, cancel=cancel)
        window._clear_preview()
        window._submit('expression_prepare' if prepare else 'expression_preview', run, cancel=cancel)
    # Starting a worker changes no metadata. Refreshing here would overwrite
    # the busy callback's disabled menu actions with idle project state.
    try:
        start()
    except (UCCError, OSError, ValueError, TypeError, KeyError) as error:
        window._error(f'{type(error).__name__}: {error}')


def finish_expression(window, result):
    try:
        if isinstance(result, ExpressionPreparation):
            window.controller.accept_saved_expression_master(result.project, library_sha256=result.library_sha256)
            window._clear_preview(); window.refresh_project()
            window.log.setPlainText('Facial controls prepared and independently reopened. The saved master is neutral. '
                'The previous master and compatible hand selection remain recoverable through undo/redo. '
                'Set strengths, save, then request an expression preview.')
        elif isinstance(result, ExpressionPreview):
            from .expression_binding import bind_expression, clear_expression
            from .expression_viewer import ExpressionViewer
            bind_expression(window, result)
            try:
                if getattr(window, 'expression_viewer', None) is None:
                    window.expression_viewer = ExpressionViewer()
                    window.expression_dock = QDockWidget('Facial expression playback', window)
                    window.expression_dock.setWidget(window.expression_viewer)
                    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, window.expression_dock)
                window.expression_viewer.show_cache(result.cache)
                window.expression_dock.show(); window.expression_dock.raise_()
            except BaseException:
                clear_expression(window); raise
            window.log.setPlainText('All 25 saved expression frames independently verified against reference skin and '
                'complete playback buffers. Saved master remains neutral. Visual quality and engine imports are unapproved.')
        else: raise ValidationError('Unexpected expression worker result')
    except (UCCError, OSError, ValueError) as error:
        window._error('Expression result could not be adopted: '+str(error))


def expression_error(window, error):
    window._clear_preview()
    if window.jobs.cancel_requested:
        window.refresh_project()
        window.log.setPlainText('Expression operation cancelled. No new result was adopted.'); return
    if 'ProjectConflict' in error and window.controller.store is not None and not window.controller.dirty:
        try:
            window.controller.open(window.controller.store.root); window.refresh_project()
            window.log.setPlainText(error+'\nExternal saved changes were preserved and reloaded.'); return
        except (UCCError, OSError, ValueError): pass
    window._error(error)
