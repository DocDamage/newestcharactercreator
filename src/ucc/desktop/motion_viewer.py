"""Interactive full-surface playback of verified precomputed Blender skin."""
from __future__ import annotations
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox

from ucc.preview.motion_cache import MotionCache
from ucc.preview.playback_clock import PlaybackClock
from .motion_gpu import SkinRenderer


class MotionCanvas(QOpenGLWidget):
    failed=Signal(str)

    def __init__(self,cache: MotionCache,parent=None):
        super().__init__(parent)
        format=QSurfaceFormat();format.setVersion(3,3);format.setProfile(QSurfaceFormat.CoreProfile)
        format.setDepthBufferSize(24);self.setFormat(format)
        self.cache=cache;self.frame=0;self.renderer=None;self.error=""
        self._context_timer=QTimer(self);self._context_timer.setSingleShot(True)
        self._context_timer.timeout.connect(self._check_context)
        self.yaw=-.45;self.pitch=.15;self.zoom=1.;self.pan=(0.,0.);self._pointer=None
        self.setMinimumSize(300,300)
        self.setToolTip("Drag: orbit | Right-drag: pan | Wheel: zoom | Actual cached Blender skin")

    def initializeGL(self):
        try:
            self.renderer=SkinRenderer(self.context())
            self.context().aboutToBeDestroyed.connect(self.release)
        except Exception as error:self._fail(str(error))

    def release(self):
        if self.renderer is not None:
            self.makeCurrent();self.renderer.close();self.renderer=None;self.doneCurrent()

    def _fail(self,error):
        if not self.error:
            self.error=error;self.failed.emit(error)

    def paintGL(self):
        if self.renderer is None or self.error:return
        try:
            dpr=self.devicePixelRatioF()
            self.renderer.draw(self.cache,self.frame,round(self.width()*dpr),round(self.height()*dpr),
                yaw=self.yaw,pitch=self.pitch,zoom=self.zoom,pan=self.pan)
        except Exception as error:self._fail(str(error))

    def reset_view(self):
        self.yaw=-.45;self.pitch=.15;self.zoom=1.;self.pan=(0.,0.);self.update()

    def mousePressEvent(self,event):self._pointer=event.position()

    def mouseReleaseEvent(self,event):self._pointer=None

    def mouseMoveEvent(self,event):
        if self._pointer is None:return
        delta=event.position()-self._pointer;self._pointer=event.position()
        if event.buttons()&Qt.MouseButton.RightButton:
            self.pan=(self.pan[0]-delta.x()*.005,self.pan[1]+delta.y()*.005)
        else:
            self.yaw+=delta.x()*.008;self.pitch=max(-1.35,min(1.35,self.pitch+delta.y()*.008))
        self.update()

    def wheelEvent(self,event):
        self.zoom=max(.35,min(8.,self.zoom*(.85 if event.angleDelta().y()>0 else 1/.85)));self.update()

    def showEvent(self,event):
        super().showEvent(event)
        self._context_timer.start(500)

    def _check_context(self):
        if self.isVisible() and not self.isValid():self._fail("A desktop OpenGL 3.3 context could not be created")


class MotionViewer(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.cache=None;self.clock=None;self.canvas=None
        self.layout=QVBoxLayout(self)
        self.status=QLabel("Prepare a verified FBX body preview, then load its motion in UCC.")
        self.status.setWordWrap(True);self.layout.addWidget(self.status)
        self.transport=QHBoxLayout()
        self.play=QPushButton("Play");self.loop=QCheckBox("Loop");self.loop.setChecked(True)
        self.reset=QPushButton("Reset view");self.position=QLabel("Frame —")
        for w in (self.play,self.loop,self.reset,self.position):self.transport.addWidget(w)
        self.layout.addLayout(self.transport)
        self.scrub=QSlider(Qt.Orientation.Horizontal);self.scrub.setRange(0,0);self.layout.addWidget(self.scrub)
        self.note=QLabel("Precomputed skin playback • private joint correction • visual/contact/engine quality unapproved")
        self.note.setWordWrap(True);self.layout.addWidget(self.note)
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.play.clicked.connect(self.toggle);self.scrub.valueChanged.connect(self.seek)
        self.loop.toggled.connect(self._loop_changed);self.reset.clicked.connect(self._reset)
        self._enable(False)

    def _enable(self,enabled):
        for w in (self.play,self.loop,self.reset,self.scrub):w.setEnabled(enabled)

    def clear(self):
        self.timer.stop();self.clock=None;self.cache=None
        if self.canvas is not None:
            self.canvas.release();self.layout.removeWidget(self.canvas);self.canvas.hide();self.canvas.deleteLater();self.canvas=None
        self.play.setText("Play");self.scrub.setRange(0,0);self.position.setText("Frame —");self._enable(False)
        self.status.setText("Prepare a verified FBX body preview, then load its motion in UCC.")

    def show_cache(self,cache: MotionCache):
        self.clear();self.cache=cache;self.clock=PlaybackClock(cache.frame_count,cache.fps,loop=self.loop.isChecked())
        self.canvas=MotionCanvas(cache,self);self.canvas.failed.connect(self._failed)
        self.layout.insertWidget(1,self.canvas,1)
        self.scrub.setRange(0,cache.frame_count-1);self._enable(True)
        self.status.setText(f"Verified cached motion: {cache.frame_count} frames at {cache.fps:g} fps • {cache.vertex_count:,} visible vertices • {cache.triangle_count:,} triangles")
        self._present()

    def _failed(self,error):
        self.timer.stop()
        if self.clock:self.clock.playing=False
        self._enable(False)
        self.status.setText("3D animation unavailable: "+error+". Use the private Blender animation; check your GPU driver and desktop OpenGL 3.3 support.")

    def _loop_changed(self,checked):
        if self.clock:self.clock.loop=checked

    def _reset(self):
        if self.canvas:self.canvas.reset_view()

    def toggle(self):
        if self.clock is None:return
        if self.clock.playing:self.clock.pause(time.monotonic());self.timer.stop()
        else:self.clock.play(time.monotonic());self.timer.start()
        self._present()

    def seek(self,frame):
        if self.clock is not None:self.clock.seek(frame,time.monotonic());self._present()

    def tick(self):
        if self.clock is None:return
        self.clock.advance(time.monotonic());self._present()
        if not self.clock.playing:self.timer.stop()

    def _present(self):
        if self.clock is None:return
        frame=self.clock.frame
        self.scrub.blockSignals(True);self.scrub.setValue(frame);self.scrub.blockSignals(False)
        self.position.setText(f"Source frame {frame+self.cache.source_first_frame} • {frame+1} / {self.clock.count} • {frame/self.clock.fps:.2f} s")
        self.play.setText("Pause" if self.clock.playing else "Play")
        self.canvas.frame=frame;self.canvas.update()

    def hideEvent(self,event):
        if self.clock and self.clock.playing:self.toggle()
        super().hideEvent(event)

    def closeEvent(self,event):
        self.clear();super().closeEvent(event)
