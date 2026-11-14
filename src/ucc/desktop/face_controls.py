"""One bounded facial intent control with an explicit saved-master action."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout


class FaceSlider(QSlider):
    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                           Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.sliderReleased.emit()


class FaceControls(QGroupBox):
    parameter_changed = Signal(str, float)
    apply_requested = Signal()

    def __init__(self):
        super().__init__('Face shape')
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Nose width'))
        self.slider = FaceSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName('face_nose_width')
        self.slider.setRange(0, 1000); self.slider.setValue(500)
        self.value = QDoubleSpinBox()
        self.value.setObjectName('face_nose_width_value')
        self.value.setRange(0., 1.); self.value.setDecimals(3); self.value.setSingleStep(.01); self.value.setValue(.5)
        self.slider.valueChanged.connect(lambda v: self.value.setValue(v/1000))
        self.value.valueChanged.connect(lambda v: self.slider.setValue(round(v*1000)))
        self.slider.sliderReleased.connect(self._edit)
        self.value.editingFinished.connect(self._edit)
        row.addWidget(self.slider, 1); row.addWidget(self.value)
        layout.addLayout(row)
        note = QLabel('0 narrows • 0.5 neutral • 1 widens. Save this setting, then apply it to the saved master. Generation and body refit retain it. No live geometry updates.')
        note.setWordWrap(True); layout.addWidget(note)
        self.apply = QPushButton('Apply saved face shape to master…')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self.apply)

    def _edit(self):
        self.parameter_changed.emit('nose_width', self.value.value())

    def display(self, view):
        value = dict(view.facial_parameters).get('nose_width', .5)
        self.slider.blockSignals(True); self.value.blockSignals(True)
        self.slider.setValue(round(value*1000)); self.value.setValue(value)
        self.slider.blockSignals(False); self.value.blockSignals(False)
        supported = view.part_count == 0 and view.animation_count == 0
        self.setEnabled(supported)
        self.apply.setEnabled(supported and view.master_blend is not None and bool(view.facial_parameters) and not view.dirty)
        self.setToolTip('Facial editing with attached parts or animations is not validated.' if not supported else '')
