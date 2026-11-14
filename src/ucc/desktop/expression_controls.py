"""Explicit preparation and saved, bounded expression strengths."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout


class ExpressionControls(QGroupBox):
    parameter_changed = Signal(str, float)
    prepare_requested = Signal()
    preview_requested = Signal()
    reset_requested = Signal()

    def __init__(self):
        super().__init__('Facial expression preview')
        layout = QVBoxLayout(self)
        self.prepare = QPushButton('Prepare facial controls on saved master…')
        self.prepare.clicked.connect(self.prepare_requested.emit)
        layout.addWidget(self.prepare)
        form = QFormLayout()
        self.values = {}
        for name, label in (('eye_left_closure', 'Left eye closure'), ('eye_right_closure', 'Right eye closure'),
                            ('mouth_corners', 'Mouth corner pull'), ('mouth_open', 'Mouth opening')):
            value = QDoubleSpinBox()
            value.setObjectName('expression_'+name)
            value.setRange(0., .5); value.setDecimals(3); value.setSingleStep(.025)
            value.editingFinished.connect(lambda k=name, v=value: self.parameter_changed.emit(k, v.value()))
            self.values[name] = value
            form.addRow(label, value)
        layout.addLayout(form)
        self.reset = QPushButton('Reset expression strengths to zero')
        self.reset.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset)
        self.preview = QPushButton('Preview saved expression strengths…')
        self.preview.clicked.connect(self.preview_requested.emit)
        layout.addWidget(self.preview)
        self.note = QLabel('Save strengths before preview. The one-second preview returns to neutral; '
                           'the saved master stays neutral. Limited to strengths 0–0.5; full eye closure, '
                           'speech and visual quality are unverified.')
        self.note.setWordWrap(True); layout.addWidget(self.note)

    def display(self, view):
        supported = view.master_blend is not None and view.animation_count == 0
        ready = view.expression_library is not None
        self.prepare.setEnabled(supported and not ready and not view.dirty)
        self.preview.setEnabled(supported and ready and not view.dirty)
        parameters = dict(view.expression_parameters)
        for name, value in self.values.items():
            value.blockSignals(True); value.setValue(parameters.get(name, 0.)); value.blockSignals(False)
            value.setEnabled(supported and ready)
        self.reset.setEnabled(supported and ready and any(parameters.values()))
        self.setToolTip('Save settings first. Preparation preserves a registered compatible hand; '
                        'projects with attached animations are unsupported.')
