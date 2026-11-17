"""Registered-only canvas authority; manual playback keeps its existing behavior."""
from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtWidgets import QDockWidget

from ucc.preview.motion_cache import MotionCache
from .motion_viewer import MotionCanvas, MotionViewer


class RegisteredNativeViewer(MotionViewer):
    invalidated = Signal()

    def __init__(self, current: Callable[[], bool], parent=None):
        self._current = current
        self._clearing = False
        super().__init__(parent)
        for label in (self.status, self.position, self.note, self.surface_status):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.authority_timer = QTimer(self)
        self.authority_timer.setInterval(500)
        self.authority_timer.timeout.connect(self._allowed)

    def _allowed(self) -> bool:
        if self.cache is None or self._clearing:
            return False
        try:
            current = self._current()
        except Exception:
            current = False
        if not current:
            self.clear()
            self.invalidated.emit()
        return current

    def _make_canvas(self, cache: MotionCache):
        return MotionCanvas(cache, self, paint_guard=self._allowed)

    def _connect_canvas(self, canvas):
        canvas.failed.connect(lambda error: self._failed(error) if self.canvas is canvas else None)

    def _enable(self, enabled):
        super()._enable(enabled)
        self.try_fit.setEnabled(False)
        self.review_body.setEnabled(False)

    def show_cache(self, cache: MotionCache):
        super().show_cache(cache)
        if self.cache is not None:
            self.authority_timer.start()

    def clear(self):
        if self._clearing:
            return
        self._clearing = True
        try:
            if hasattr(self, 'authority_timer'):
                self.authority_timer.stop()
            canvas = self.canvas
            super().clear()
            if canvas is not None:
                canvas.cache = None
                canvas._paint_guard = lambda: False
        finally:
            self._clearing = False

    def _failed(self, error):
        self.clear()
        self.status.setText('Registered animation unavailable: '+str(error))
        self.invalidated.emit()

    def _present(self):
        if self._allowed():
            super()._present()

    def tick(self):
        if self._allowed():
            super().tick()

    def seek(self, frame):
        if self._allowed():
            super().seek(frame)

    def toggle(self):
        if self._allowed():
            super().toggle()

    def _reset(self):
        if self._allowed():
            super()._reset()

    def closeEvent(self, event):
        self.clear()
        self.invalidated.emit()
        super().closeEvent(event)


class RegisteredNativeDock(QDockWidget):
    def __init__(self, window):
        super().__init__('Registered cached skin — private preview', window)
        self.owner = window

    def closeEvent(self, event):
        from .registered_native_workflow import clear_registered_native
        if self.owner.motion_dock is self:
            clear_registered_native(self.owner)
        event.accept()
