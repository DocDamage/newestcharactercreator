"""Full-surface expression playback with camera-only head focus."""
from dataclasses import replace
import math
import struct
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel, QSlider

from ucc.preview.playback_clock import PlaybackClock
from .motion_viewer import MotionCanvas


def head_focus(cache):
    """Estimate an upper central region of the admitted upright humanoid."""
    vertices, _ = cache.frame(0)
    m = cache.world_matrix
    points = [tuple(sum(m[r*4+c]*p[c] for c in range(3))+m[r*4+3] for r in range(3))
              for p in struct.iter_unpack('<3f', vertices)]
    low = tuple(min(p[i] for p in points) for i in range(3))
    high = tuple(max(p[i] for p in points) for i in range(3))
    height = high[2]-low[2]; center_x = (low[0]+high[0])/2
    head = [p for p in points if p[2] >= high[2]-.14*height and abs(p[0]-center_x) <= .12*height]
    if not head or height <= 0:
        raise ValueError('Cannot focus the upper region of this humanoid')
    lo = tuple(min(p[i] for p in head)-.03 for i in range(3))
    hi = tuple(max(p[i] for p in head)+.03 for i in range(3))
    center = tuple((a+b)/2 for a, b in zip(lo, hi))
    return replace(cache, hips=(center,)*cache.frame_count, radius=max(.001, math.dist(lo, hi)*.6))


class ExpressionViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = self.clock = self.canvas = None
        self.layout = QVBoxLayout(self)
        self.status = QLabel('Prepare a saved expression preview to play it here.')
        self.status.setWordWrap(True); self.layout.addWidget(self.status)
        row = QHBoxLayout()
        self.play = QPushButton('Play'); self.loop = QCheckBox('Loop')
        self.focus = QCheckBox('Head focus'); self.reset = QPushButton('Reset view')
        self.position = QLabel('Frame —')
        for widget in (self.play, self.loop, self.focus, self.reset, self.position): row.addWidget(widget)
        self.layout.addLayout(row)
        self.scrub = QSlider(Qt.Orientation.Horizontal); self.layout.addWidget(self.scrub)
        note = QLabel('Complete cached Blender skin • neutral → saved strengths → neutral • '
                      'visual quality and engine imports unapproved')
        note.setWordWrap(True); self.layout.addWidget(note)
        self.timer = QTimer(self); self.timer.setInterval(8); self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.play.clicked.connect(self.toggle); self.scrub.valueChanged.connect(self.seek)
        self.focus.toggled.connect(self._focus); self.reset.clicked.connect(self._reset)
        self.loop.toggled.connect(self._loop)
        self.clear()

    def _enable(self, enabled):
        for widget in (self.play, self.loop, self.focus, self.reset, self.scrub): widget.setEnabled(enabled)

    def clear(self):
        self.timer.stop(); self.clock = self.cache = self._focused = None
        if self.canvas is not None:
            self.canvas.release(); self.layout.removeWidget(self.canvas)
            self.canvas.hide(); self.canvas.deleteLater(); self.canvas = None
        self.scrub.setRange(0, 0); self.position.setText('Frame —'); self.play.setText('Play')
        self._enable(False)
        self.status.setText('Prepare a saved expression preview to play it here.')

    def show_cache(self, cache):
        self.clear()
        focused = head_focus(cache)
        self.cache = cache; self._focused = focused
        self.clock = PlaybackClock(cache.frame_count, cache.fps, loop=self.loop.isChecked())
        self.canvas = MotionCanvas(focused if self.focus.isChecked() else cache, self)
        self.canvas.failed.connect(self._failed); self.layout.insertWidget(1, self.canvas, 1)
        self.scrub.setRange(0, cache.frame_count-1); self._enable(True); self._present()
        self.status.setText(f'Verified expression preview: {cache.frame_count} frames at {cache.fps:g} fps; '
                            f'{cache.vertex_count:,} visible vertices, {cache.triangle_count:,} triangles per frame.')

    def _failed(self, error):
        self.clear(); self.status.setText('Expression GPU playback failed: '+error)

    def _loop(self, value):
        if self.clock: self.clock.loop = value

    def _reset(self):
        if self.canvas: self.canvas.reset_view()

    def _focus(self, value):
        if self.canvas:
            self.canvas.cache = self._focused if value else self.cache
            self.canvas.reset_view()

    def _present(self):
        if self.clock is None or self.canvas is None: return
        frame = self.clock.frame
        self.canvas.frame = frame; self.canvas.update()
        self.scrub.blockSignals(True); self.scrub.setValue(frame); self.scrub.blockSignals(False)
        self.position.setText(f'Frame {frame+1} / {self.clock.count}')
        self.play.setText('Pause' if self.clock.playing else 'Play')

    def seek(self, frame):
        if self.clock:
            self.clock.seek(frame, time.monotonic()); self._present()

    def toggle(self):
        if self.clock is None: return
        if self.clock.playing:
            self.clock.pause(time.monotonic()); self.timer.stop()
        else:
            self.clock.play(time.monotonic()); self.timer.start()
        self._present()

    def tick(self):
        if self.clock is None: return
        self.clock.advance(time.monotonic()); self._present()
        if not self.clock.playing: self.timer.stop()
