"""Explicit registered-source and saved-binding choices for private previews."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)


@dataclass(frozen=True, slots=True)
class TargetActionChoice:
    operation: str
    clip_id: str
    binding_sha256: str | None
    mapping_profile: Path | None
    mapping_sha256: str | None
    purpose: str
    local_preview_confirmed: bool


class TargetActionDialog(QDialog):
    source_requested = Signal(str)
    mapping_requested = Signal(str)

    def __init__(self, clips: tuple[str, ...], selected: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Prepare registered clip preview')
        self.resize(760, 520)
        self.choice = None
        self.review = None
        self.mapping_sha256 = None
        self._busy = False
        layout = QVBoxLayout(self)
        description = QLabel(
            'Prepare a private saved target Action, reopen one saved binding, or inspect its diagnostic measurements. '
            'Playback runs once: source frames 2–301 correspond to target frames 1–300. '
            'The editable master and source-only registration stay unchanged. '
            'Editing, usable-action quality, visual quality and engine use remain unapproved.')
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.clips = QComboBox()
        self.clips.addItems(clips)
        if selected in clips:
            self.clips.setCurrentIndex(clips.index(selected))
        form.addRow('Attached source clip', self.clips)
        self.source_details = QPlainTextEdit('Reviewing the exact registered source…')
        self.source_details.setReadOnly(True)
        self.source_details.setMaximumHeight(120)
        form.addRow('Registered source', self.source_details)
        self.bindings = QComboBox()
        self.bindings.addItem('Choose a saved binding explicitly', None)
        form.addRow('Saved binding SHA-256', self.bindings)
        self.mapping = QLineEdit()
        self.mapping.setReadOnly(True)
        self.mapping.setPlaceholderText('Choose an explicitly reviewed target mapping JSON')
        self.choose_mapping = QPushButton('Choose reviewed mapping…')
        row = QHBoxLayout()
        row.addWidget(self.mapping, 1)
        row.addWidget(self.choose_mapping)
        form.addRow('Mapping for new preview', row)
        self.mapping_hash = QLabel('No mapping reviewed')
        self.mapping_hash.setWordWrap(True)
        form.addRow('Mapping SHA-256', self.mapping_hash)
        self.purpose = QLineEdit()
        self.purpose.setMaxLength(2000)
        self.purpose.setPlaceholderText('Record the purpose of this new private preview')
        form.addRow('Purpose for new preview', self.purpose)
        layout.addLayout(form)
        self.consent = QCheckBox('I confirm this exact registered source for private local Blender/target preview only.')
        self.consent.setChecked(False)
        layout.addWidget(self.consent)
        self.status = QLabel('Reviewing source identity. No saved binding is selected automatically.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.diagnostics = QPushButton('Inspect selected clip diagnostics...')
        layout.addWidget(self.diagnostics)
        self.body_sprites = QPushButton('Render selected saved clip sprites…')
        layout.addWidget(self.body_sprites)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.prepare = buttons.addButton('Prepare new private preview', QDialogButtonBox.ButtonRole.ActionRole)
        self.load = buttons.addButton('Load selected saved preview', QDialogButtonBox.ButtonRole.ActionRole)
        self.godot_saved = buttons.addButton('Open saved Godot preview...', QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.clips.currentTextChanged.connect(self._source_changed)
        self.choose_mapping.clicked.connect(self._choose_mapping)
        self.bindings.currentIndexChanged.connect(self._refresh)
        self.purpose.textChanged.connect(self._refresh)
        self.consent.toggled.connect(self._refresh)
        self.prepare.clicked.connect(lambda: self._choose('prepare'))
        self.load.clicked.connect(lambda: self._choose('load'))
        self.godot_saved.clicked.connect(lambda: self._choose('godot_saved'))
        self.diagnostics.clicked.connect(lambda: self._choose('diagnostics'))
        self.body_sprites.clicked.connect(lambda: self._choose('body_sprites'))
        self._refresh()

    def _source_changed(self, clip_id):
        self.review = None
        self.mapping_sha256 = None
        self.mapping.clear()
        self.mapping_hash.setText('No mapping reviewed')
        self.bindings.clear()
        self.bindings.addItem('Choose a saved binding explicitly', None)
        self.consent.setChecked(False)
        self.source_details.setPlainText('Reviewing the exact registered source…')
        self._refresh()
        self.source_requested.emit(clip_id)

    def set_busy(self, busy: bool):
        self._busy = busy
        self._refresh()

    def set_review(self, review, summaries):
        if review.source.clip_id != self.clips.currentText():
            return
        self.review = review
        policy = review.policy
        self.source_details.setPlainText(
            f'{review.source.source_sha256}\n{policy.provider} — {policy.license_name}\n{policy.source_uri}\n'
            '300 source frames at 30 fps. Source-only and editing permissions are unchanged.')
        self.bindings.clear()
        self.bindings.addItem('Choose a saved binding explicitly', None)
        for item in summaries:
            if item.clip_id == review.source.clip_id:
                self.bindings.addItem(f'{item.clip_id} — {item.binding_sha256}', item.binding_sha256)
        self.bindings.setCurrentIndex(0)
        self.status.setText('Choose a saved SHA to validate and load, or review a mapping and prepare a new private Action.')
        self._refresh()

    def set_mapping(self, path: Path, sha256: str):
        self.mapping.setText(str(path))
        self.mapping_sha256 = sha256
        self.mapping_hash.setText(sha256)
        self.consent.setChecked(False)
        self._refresh()

    def set_error(self, message: str):
        self.status.setText(message)
        self._refresh()

    def _choose_mapping(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, 'Choose reviewed target mapping', '', 'Target mapping JSON (*.json)')
        if selected:
            self.mapping_sha256 = None
            self.mapping.setText(selected)
            self.mapping_hash.setText('Reviewing mapping identity…')
            self.consent.setChecked(False)
            self._refresh()
            self.mapping_requested.emit(selected)

    def _refresh(self, *_):
        ready = self.review is not None and not self._busy
        self.clips.setEnabled(not self._busy)
        self.bindings.setEnabled(ready)
        self.choose_mapping.setEnabled(ready)
        self.purpose.setEnabled(ready)
        self.consent.setEnabled(ready)
        consent = ready and self.consent.isChecked()
        purpose = self.purpose.text().strip()
        valid_purpose = bool(purpose and all(c.isprintable() for c in purpose))
        self.prepare.setEnabled(bool(consent and self.mapping_sha256 and valid_purpose))
        self.load.setEnabled(bool(consent and self.bindings.currentData()))
        self.godot_saved.setEnabled(bool(consent and self.bindings.currentData()))
        self.diagnostics.setEnabled(bool(consent and self.bindings.currentData()))
        self.body_sprites.setEnabled(bool(consent and self.bindings.currentData()))

    def _choose(self, operation: str):
        button = {'prepare': self.prepare, 'load': self.load, 'godot_saved': self.godot_saved,
                  'diagnostics': self.diagnostics, 'body_sprites': self.body_sprites}[operation]
        if not button.isEnabled():
            return
        self.choice = TargetActionChoice(
            operation, self.clips.currentText(), self.bindings.currentData() if operation in {'load', 'godot_saved', 'diagnostics', 'body_sprites'} else None,
            Path(self.mapping.text()) if operation == 'prepare' else None,
            self.mapping_sha256 if operation == 'prepare' else None,
            self.purpose.text().strip(), self.consent.isChecked())
        self.accept()
