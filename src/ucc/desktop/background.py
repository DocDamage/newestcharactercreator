"""Single-shot Qt worker; long-running filesystem/HTTP probes never block paint events."""
from __future__ import annotations

from typing import Any, Callable
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot


class JobWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func = func

    def run(self) -> None:
        try:
            self.succeeded.emit(self.func())
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
        finally:
            self.finished.emit()


class BackgroundJobs(QObject):
    """One explicit work unit at a time; keeps thread references alive until exit."""

    def __init__(self, on_success: Callable[[object], None],
                 on_error: Callable[[str], None], on_busy: Callable[[bool], None]) -> None:
        super().__init__()
        self.on_success = on_success
        self.on_error = on_error
        self.on_busy = on_busy
        self._thread: QThread | None = None
        self._worker: JobWorker | None = None
        self._cancel: Event | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def submit(self, func: Callable[[], Any], *, cancel: Event | None = None) -> bool:
        if self.busy:
            return False
        thread = QThread()
        worker = JobWorker(func)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self.on_success)
        worker.failed.connect(self.on_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._completed)
        self._thread = thread
        self._worker = worker
        self._cancel = cancel
        self.on_busy(True)
        thread.start()
        return True

    def cancel(self) -> bool:
        """Request cooperative cancellation; never force-delete a running Qt thread."""
        if not self.busy or self._cancel is None:
            return False
        self._cancel.set()
        return True

    @Slot()
    def _completed(self) -> None:
        self._thread = None
        self._worker = None
        self._cancel = None
        self.on_busy(False)
