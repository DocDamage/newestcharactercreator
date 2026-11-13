"""Interactive full-surface playback of verified precomputed Blender skin."""
from __future__ import annotations
from dataclasses import replace
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox, QComboBox

from ucc.preview.motion_cache import MotionCache
from ucc.preview.playback_clock import PlaybackClock
from ucc.preview.surface_review import POLICY as ARM_POLICY
from ucc.preview.body_contacts import POLICY as BODY_POLICY
from ucc.core.errors import ValidationError
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
        self.highlight_intersections=False;self.focus_intersections=False
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
                yaw=self.yaw,pitch=self.pitch,zoom=self.zoom,pan=self.pan,
                highlight_intersections=self.highlight_intersections,focus_intersections=self.focus_intersections)
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
    fit_requested=Signal()
    body_review_requested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.cache=None;self.clock=None;self.canvas=None;self.comparison=None;self.fit_busy=False
        self._base_cache=None;self._body_caches=None;self._gpu_failed=False
        self.layout=QVBoxLayout(self)
        self.status=QLabel("Prepare a verified FBX body preview, then load its motion in UCC.")
        self.status.setWordWrap(True);self.layout.addWidget(self.status)
        self.variant=QComboBox();self.variant.addItems(['Original motion','Fitted motion'])
        self.variant.setToolTip('Compare at the same source frame and camera. Fitting changes target motion; contact quality remains unapproved.')
        self.variant.hide();self.layout.addWidget(self.variant)
        self.variant.currentIndexChanged.connect(self._switch_variant)
        self.inspection=QComboBox();self.inspection.addItems(['Hand / opposite arm','Hand / head and torso'])
        self.inspection.setToolTip('Central body includes the head, neck and spine chain. Other body pairs, solid containment and grasp intent are not evaluated. Focus resets when changing inspection.')
        self.inspection.hide();self.layout.addWidget(self.inspection)
        self.inspection.currentIndexChanged.connect(lambda _index:self._select_cache())
        self.transport=QHBoxLayout()
        self.play=QPushButton("Play");self.loop=QCheckBox("Loop");self.loop.setChecked(True)
        self.reset=QPushButton("Reset view");self.position=QLabel("Frame —")
        for w in (self.play,self.loop,self.reset,self.position):self.transport.addWidget(w)
        self.layout.addLayout(self.transport)
        surface_controls=QHBoxLayout()
        self.highlight=QCheckBox("Highlight hand/arm intersections");self.highlight.setChecked(True)
        self.highlight.setToolTip("Checks each hand against the opposite upper-limb branch, including the shoulder. Other body-part pairs and correct grasp/contact are not evaluated.")
        self.focus=QCheckBox("Focus");self.next_flagged=QPushButton("Next flagged frame")
        self.max_pairs=QPushButton("Max pairs")
        self.try_fit=QPushButton('Try bounded hand/arm fit')
        self.try_fit.setToolTip('Search small arm and wrist corrections limited to 30 mm, 15 degrees and existing joint/skin bounds. Original motion is retained on failure. Grasp and visual quality remain unapproved.')
        self.try_fit.clicked.connect(self.fit_requested.emit)
        self.review_body=QPushButton('Review hand/body contacts')
        self.review_body.setToolTip('Independently inspect every saved frame against the head, neck and spine chain. Read-only; can take several minutes.')
        self.review_body.clicked.connect(self.body_review_requested.emit)
        self.max_pairs.setToolTip("Jump to the frame with the most intersecting triangle pairs. This ranks pair counts, not penetration depth or contact quality.")
        for w in (self.highlight,self.focus,self.next_flagged,self.max_pairs):surface_controls.addWidget(w)
        self.layout.addLayout(surface_controls)
        self.layout.addWidget(self.try_fit)
        self.layout.addWidget(self.review_body)
        self.surface_status=QLabel("Surface inspection has not been run for this cache.")
        self.surface_status.setWordWrap(True);self.layout.addWidget(self.surface_status)
        self.scrub=QSlider(Qt.Orientation.Horizontal);self.scrub.setRange(0,0);self.layout.addWidget(self.scrub)
        self.note=QLabel("Precomputed skin playback • private joint correction • visual/contact/engine quality unapproved")
        self.note.setWordWrap(True);self.layout.addWidget(self.note)
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.play.clicked.connect(self.toggle);self.scrub.valueChanged.connect(self.seek)
        self.loop.toggled.connect(self._loop_changed);self.reset.clicked.connect(self._reset)
        self.highlight.toggled.connect(lambda _checked:self._present())
        self.focus.toggled.connect(lambda _checked:self._present());self.next_flagged.clicked.connect(self.next_surface_frame)
        self.max_pairs.clicked.connect(self.max_surface_frame)
        self._enable(False)

    def _enable(self,enabled):
        for w in (self.play,self.loop,self.reset,self.scrub):w.setEnabled(enabled)
        surface=self.cache.surface_review if self.cache else None
        checked=bool(enabled and surface and surface.status=="CHECKED")
        self.highlight.setEnabled(checked)
        for w in (self.focus,self.next_flagged,self.max_pairs):w.setEnabled(checked and bool(surface.flagged_frames))
        self.try_fit.setEnabled(checked and surface.policy==ARM_POLICY and bool(surface.flagged_frames) and self.comparison is None and not self.fit_busy)
        self.review_body.setEnabled(bool(enabled and self._base_cache and self._base_cache.surface_review and
            self._base_cache.surface_review.status=='CHECKED' and self._body_caches is None and not self.fit_busy))
        self.variant.setEnabled(enabled)
        self.inspection.setEnabled(enabled)

    def set_fit_busy(self,busy: bool):
        self.fit_busy=busy;self._enable(self.clock is not None and not self._gpu_failed and not getattr(self.canvas,'error',''))

    def clear(self):
        self.timer.stop();self.clock=None;self.cache=None;self.comparison=None
        self._base_cache=None;self._body_caches=None;self._gpu_failed=False
        self.variant.blockSignals(True);self.variant.setCurrentIndex(0);self.variant.blockSignals(False);self.variant.hide()
        self.inspection.blockSignals(True);self.inspection.setCurrentIndex(0);self.inspection.blockSignals(False);self.inspection.hide()
        if self.canvas is not None:
            self.canvas.release();self.layout.removeWidget(self.canvas);self.canvas.hide();self.canvas.deleteLater();self.canvas=None
        self.play.setText("Play");self.scrub.setRange(0,0);self.position.setText("Frame —");self._enable(False)
        self.status.setText("Prepare a verified FBX body preview, then load its motion in UCC.")
        self.note.setText('Precomputed skin playback • private joint correction • visual/contact/engine quality unapproved')
        self.focus.setChecked(False);self.surface_status.setText("Surface inspection has not been run for this cache.")

    def show_cache(self,cache: MotionCache):
        self.clear();self.cache=cache;self._base_cache=cache;self.clock=PlaybackClock(cache.frame_count,cache.fps,loop=self.loop.isChecked())
        self.canvas=MotionCanvas(cache,self);self.canvas.failed.connect(self._failed)
        self.layout.insertWidget(1,self.canvas,1)
        self.scrub.setRange(0,cache.frame_count-1);self._enable(True)
        self.status.setText(f"Verified cached motion: {cache.frame_count} frames at {cache.fps:g} fps • {cache.vertex_count:,} visible vertices • {cache.triangle_count:,} triangles")
        self._present()

    def show_comparison(self,original: MotionCache,fitted: MotionCache):
        if (original.frame_count!=fitted.frame_count or original.fps!=fitted.fps or
            original.source_first_frame!=fitted.source_first_frame or original.hips!=fitted.hips or
            original.world_matrix!=fitted.world_matrix or original.vertex_count!=fitted.vertex_count or
            original.triangle_count!=fitted.triangle_count):
            raise ValidationError('Original/fitted playback timing, character or root trajectory differs')
        self.show_cache(original);self.comparison=(original,fitted);self.variant.show();self._enable(True)
        self.note.setText('Original/fitted comparison at the same frame and camera • target motion is changed • contact/engine quality unapproved')

    def _switch_variant(self,index):
        if self.comparison is None or self.canvas is None:return
        self._select_cache()

    def show_body_contacts(self,original,fitted=None):
        bases=self.comparison if self.comparison is not None else (self._base_cache,)
        reviews=(original,fitted) if fitted is not None else (original,)
        if (not bases[0] or len(bases)!=len(reviews) or any(base.surface_review is None or review.policy!=BODY_POLICY or
            len(review.pairs)!=base.frame_count or len(review.triangles)!=base.frame_count or
            review.triangle_hashes!=base.surface_review.triangle_hashes for base,review in zip(bases,reviews))):
            raise ValidationError('Body inspection does not match the complete visible playback topology')
        self._body_caches=tuple(replace(base,surface_review=review) for base,review in zip(bases,reviews))
        self.inspection.show();self.inspection.setCurrentIndex(1);self._select_cache()

    def _select_cache(self):
        if self.canvas is None or self.clock is None:return
        index=self.variant.currentIndex() if self.comparison is not None else 0
        bases=self._body_caches if self.inspection.currentIndex()==1 and self._body_caches is not None else (
            self.comparison if self.comparison is not None else (self._base_cache,))
        self.cache=bases[index];self.canvas.cache=self.cache
        self.focus.setChecked(False)
        self._enable(not self._gpu_failed and not getattr(self.canvas,'error',''));self._present()

    def _failed(self,error):
        self._gpu_failed=True
        self.timer.stop()
        if self.clock:self.clock.playing=False
        self._enable(False)
        self.status.setText("3D animation unavailable: "+error+". Use the private Blender animation; check your GPU driver and desktop OpenGL 3.3 support.")

    def _loop_changed(self,checked):
        if self.clock:self.clock.loop=checked

    def _reset(self):
        self.focus.setChecked(False)
        if self.canvas:self.canvas.reset_view()

    def next_surface_frame(self):
        if self.cache is None or self.cache.surface_review is None:return
        frames=self.cache.surface_review.flagged_frames
        if not frames:return
        frame=next((i for i in frames if i>self.clock.frame),frames[0])
        self._focus_surface_frame(frame)

    def max_surface_frame(self):
        if self.cache is None or self.cache.surface_review is None or not self.cache.surface_review.flagged_frames:return
        frame=max(self.cache.surface_review.flagged_frames,key=lambda i:sum(self.cache.surface_review.pairs[i]))
        self._focus_surface_frame(frame)

    def _focus_surface_frame(self,frame):
        if self.clock.playing:self.toggle()
        self.canvas.pan=(0.,0.);self.canvas.zoom=1.
        self.focus.setChecked(True);self.seek(frame)

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
        surface=self.cache.surface_review
        if surface is not None:
            label='Hand/body' if surface.policy==BODY_POLICY else 'Hand/opposite-arm'
            self.highlight.setText('Highlight hand/body intersections' if surface.policy==BODY_POLICY else 'Highlight hand/arm intersections')
            self.highlight.setToolTip('Checks each hand against the head and torso. Arms, legs, solid containment and grasp intent are outside this review.' if surface.policy==BODY_POLICY else
                'Checks each hand against the opposite upper-limb branch, including the shoulder. Other body-part pairs and correct grasp/contact are not evaluated.')
            text=(f"{label} review: {len(surface.flagged_frames)} flagged frames; current frame {sum(surface.pairs[frame])} triangle pairs. Contact quality remains unapproved."
                  if surface.status=="CHECKED" else "Surface inspection unavailable for this rig or workload; no contact verdict.")
            self.surface_status.setText(text)
        self.canvas.highlight_intersections=self.highlight.isChecked() and self.highlight.isEnabled()
        self.canvas.focus_intersections=self.focus.isChecked() and self.focus.isEnabled()
        self.canvas.frame=frame;self.canvas.update()

    def hideEvent(self,event):
        if self.clock and self.clock.playing:self.toggle()
        super().hideEvent(event)

    def closeEvent(self,event):
        self.clear();super().closeEvent(event)
