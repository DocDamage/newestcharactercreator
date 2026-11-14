"""Actual source-compatible hand choices; selection remains provisional until Apply."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox,QGroupBox,QLabel,QPushButton,QVBoxLayout


class HandControls(QGroupBox):
    build_requested=Signal()
    apply_requested=Signal()
    preview_requested=Signal()

    def __init__(self):
        super().__init__('Left hand parts')
        self.manifest_sha256=None;self._context=None;self._current='neutral';self._can_apply=False
        layout=QVBoxLayout(self)
        note=QLabel('Build two compatible hands from this saved character. Choose a hand and apply it. Original restores the starting hand while retaining body and face settings. Restore Original before changing body or face settings.')
        note.setWordWrap(True);layout.addWidget(note)
        self.build=QPushButton('Build compatible hands…');self.build.setObjectName('build_compatible_hands')
        self.build.setEnabled(False);self.build.clicked.connect(self.build_requested.emit);layout.addWidget(self.build)
        self.choice=QComboBox();self.choice.setObjectName('left_hand_style')
        for label,value in [('Original hand','neutral'),('Shorter fingers','shorter'),('Longer fingers','longer')]:
            self.choice.addItem(label,value)
        self.choice.setEnabled(False);self.choice.currentIndexChanged.connect(self._selection_changed);layout.addWidget(self.choice)
        self.apply=QPushButton('Apply selected hand…');self.apply.setObjectName('apply_compatible_hand')
        self.apply.setEnabled(False);self.apply.clicked.connect(self.apply_requested.emit);layout.addWidget(self.apply)
        self.preview=QPushButton('View saved character and hands…');self.preview.setObjectName('preview_compatible_hand')
        self.preview.setEnabled(False);self.preview.clicked.connect(self.preview_requested.emit);layout.addWidget(self.preview)
        self.status=QLabel('Generate and save a character first.');self.status.setWordWrap(True);layout.addWidget(self.status)

    def _selection_changed(self):
        self.apply.setEnabled(self._can_apply and self.choice.currentData()!=self._current)

    def display_context(self,*,key,identity,current,can_build,can_apply,can_preview,message):
        self.manifest_sha256=identity;self._current=current;self._can_apply=can_apply and identity is not None
        if self._context != (key,identity,current):
            self.choice.blockSignals(True);self.choice.setCurrentIndex(self.choice.findData(current));self.choice.blockSignals(False)
            self._context=(key,identity,current)
        self.build.setEnabled(can_build);self.choice.setEnabled(self._can_apply)
        self.preview.setEnabled(can_preview);self.status.setText(message);self._selection_changed()
