"""Private source bone segments, with transport independent of target skinning."""
import struct
import time
from typing import Callable

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from ucc.animations.source_skeleton import SourceSkeletonCache
from ucc.preview.playback_clock import PlaybackClock


class SourceSkeletonCanvas(QWidget):
    """Two fixed orthographic views of the actual measured endpoints."""
    def __init__(self, guard: Callable[[], bool], parent=None):
        super().__init__(parent)
        self.guard = guard
        self.setMinimumSize(360, 260)
        self.cache = None
        self.segments = b''

    def present(self, cache: SourceSkeletonCache, frame: int) -> None:
        self.cache = cache
        self.segments = cache.frame(frame)
        self.update()

    def clear(self) -> None:
        self.cache = None
        self.segments = b''
        self.update()

    def paintEvent(self, event) -> None:
        if self.cache is not None and not self.guard():
            self.clear()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#171d26'))
        cache = self.cache
        if cache is None:
            painter.setPen(QColor('#dddddd'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No source skeleton loaded')
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()/2
        scale = max(1., min(width-32, self.height()-64))/(2*max(cache.radius, 1e-6))
        center = tuple((a+b)/2 for a, b in zip(cache.minimum, cache.maximum))
        for panel, axis in enumerate((0, 1)):
            painter.setPen(QColor('#dddddd'))
            painter.drawText(QPointF(panel*width+12, 22), ('Front: X / Z', 'Side: Y / Z')[panel])
            painter.setPen(QPen(QColor('#87caff'), 1.5))
            def project(point):
                return QPointF((panel+.5)*width+(point[axis]-center[axis])*scale,
                               self.height()/2-(point[2]-center[2])*scale)
            for values in struct.iter_unpack('<6f', self.segments):
                painter.drawLine(project(values[:3]), project(values[3:]))


class SourceSkeletonViewer(QWidget):
    invalidated = Signal()

    def __init__(self, guard: Callable[[], bool], parent=None):
        super().__init__(parent)
        self.guard = guard
        self.cache = None
        self.clock = None
        layout = QVBoxLayout(self)
        title = QLabel('Measured source skeleton only. Skin, retargeting and motion quality are unverified.')
        title.setWordWrap(True)
        layout.addWidget(title)
        self.canvas = SourceSkeletonCanvas(self._authorized)
        layout.addWidget(self.canvas, 1)
        self.status = QLabel('No source skeleton loaded')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.play = QPushButton('Play')
        self.start = QPushButton('Go to source start')
        row.addWidget(self.play)
        row.addWidget(self.start)
        layout.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        layout.addWidget(self.slider)
        self.play.clicked.connect(self.toggle_play)
        self.start.clicked.connect(lambda: self.seek(0))
        self.slider.valueChanged.connect(self.seek)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.guard_timer = QTimer(self)
        self.guard_timer.setInterval(500)
        self.guard_timer.timeout.connect(self._authorized)
        self.clear()

    def show_cache(self, cache: SourceSkeletonCache) -> None:
        self.clear()
        self.cache = cache
        self.clock = PlaybackClock(cache.frame_count, cache.fps, loop=False)
        self.slider.setRange(0, cache.frame_count-1)
        for control in (self.play, self.start, self.slider):
            control.setEnabled(True)
        self.guard_timer.start()
        self._present()

    def clear(self) -> None:
        self.timer.stop()
        self.guard_timer.stop()
        self.cache = None
        self.clock = None
        self.canvas.clear()
        self.play.setText('Play')
        self.status.setText('No source skeleton loaded')
        for control in (self.play, self.start, self.slider):
            control.setEnabled(False)
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    def _authorized(self) -> bool:
        if self.clock is None:
            return False
        try:
            if self.guard():
                return True
        except Exception:
            pass
        self.clear()
        self.invalidated.emit()
        return False

    def _present(self) -> None:
        if not self._authorized():
            return
        self.canvas.present(self.cache, self.clock.frame)
        self.slider.blockSignals(True)
        self.slider.setValue(self.clock.frame)
        self.slider.blockSignals(False)
        clock = self.cache.clock
        self.status.setText(
            f'Source frame {clock.source_frame_at_index(self.clock.frame)} '
            f'of {clock.source_first_frame}-{clock.source_last_frame}; {clock.fps:g} fps. '
            f'Sample span {clock.sample_span_s:.6f} s; nominal coverage {clock.nominal_coverage_s:.6f} s.')
        self.play.setText('Pause' if self.clock.playing else 'Play')

    def toggle_play(self) -> None:
        if not self._authorized():
            return
        if self.clock.playing:
            self.clock.pause(time.monotonic())
            self.timer.stop()
        else:
            self.clock.play(time.monotonic())
            self.timer.start()
        self._present()

    def seek(self, index: int) -> None:
        if not self._authorized():
            return
        self.clock.seek(index, time.monotonic())
        self._present()

    def tick(self) -> None:
        if not self._authorized():
            return
        self.clock.advance(time.monotonic())
        if not self.clock.playing:
            self.timer.stop()
        self._present()

    def closeEvent(self, event) -> None:
        self.clear()
        self.invalidated.emit()
        event.accept()
