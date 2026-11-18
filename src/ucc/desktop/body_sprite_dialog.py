"""Explicit private sample review over an immutable saved Action selection."""
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ucc.core.body_sprites import BodySpriteRequest, BodySpriteWindow, body_sprite_sources
from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.sprite_render import SpritePermission, SpriteSettings
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import canonical_bytes, read_document
from ucc.jobs.body_sprite_provenance import OriginalMotionProvenance


class BodySpriteDialog(QDialog):
    origin_selected = Signal(str)

    def __init__(self, project_snapshot_json: bytes, target_binding: TargetActionBinding,
                 *, context_token: object, purpose: str = 'Private registered motion sprite sample',
                 parent=None):
        super().__init__(parent)
        if type(project_snapshot_json) is not bytes or type(target_binding) is not TargetActionBinding:
            raise ValidationError('Review an immutable saved character and exact Action binding')
        project = CharacterProject.from_dict(read_document(project_snapshot_json))
        if canonical_bytes(project.to_dict()) != project_snapshot_json:
            raise ValidationError('The saved character review must be canonical and complete')
        self._snapshot = project_snapshot_json
        self._binding = target_binding
        self._sources = body_sprite_sources(project, target_binding)
        self._purpose = purpose
        self.context_token = context_token
        self._job_id = str(uuid4())
        self._valid = True
        self._busy = False
        self._origin = None
        self._pending_origin = None
        self.setWindowTitle('Render body sprite sample')
        self.resize(950, 700)
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); layout = QVBoxLayout(content)
        scroll.setWidget(content); outer.addWidget(scroll)
        description = QLabel('Render a selected part of the saved motion as transparent images and an atlas. '
                             'The complete saved motion and character remain unchanged. This private sample '
                             'does not establish artist quality, a seamless loop or distribution rights.')
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setWordWrap(True)
        layout.addWidget(description)
        self.binding_summary = QLabel('Saved character: ' + project.name + '\nSelected binding: ' + target_binding.sha256)
        self.binding_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.binding_summary.setWordWrap(True)
        layout.addWidget(self.binding_summary)
        layout.addWidget(QLabel('Full saved motion: target frames 1–300, source frames 2–301, at 30 fps.'))
        form = QFormLayout()
        self.first_frame = QSpinBox(); self.first_frame.setRange(1, 300)
        self.frame_count = QSpinBox(); self.frame_count.setRange(1, 32); self.frame_count.setValue(8)
        self.resolution = QComboBox()
        for size in (128, 256): self.resolution.addItem(f'{size} × {size}', size)
        self.resolution.setCurrentIndex(1)
        form.addRow('First target frame', self.first_frame)
        form.addRow('Consecutive frames (1–32)', self.frame_count)
        form.addRow('Pixels per image', self.resolution)
        form.addRow('Directions', QLabel('4 fixed directions; level cameras, starting at the front.'))
        layout.addLayout(form)
        self.window_summary = QLabel(); self.window_summary.setWordWrap(True)
        layout.addWidget(self.window_summary)
        origin_row = QHBoxLayout()
        self.origin_path = QLineEdit(); self.origin_path.setReadOnly(True)
        self.origin_path.setPlaceholderText('Choose the local original-motion record')
        self.choose_origin = QPushButton('Choose origin record…')
        self.choose_origin.clicked.connect(self.browse_origin)
        origin_row.addWidget(self.origin_path); origin_row.addWidget(self.choose_origin)
        layout.addLayout(origin_row)
        self.origin_summary = QLabel('The record is checked against this selected motion. It records an origin declaration; '
                                     'it is not proof of human authorship or permission to render sprites.')
        self.origin_summary.setTextFormat(Qt.TextFormat.PlainText); self.origin_summary.setWordWrap(True)
        layout.addWidget(self.origin_summary)
        self.origin_declaration = QCheckBox('I confirm the selected motion’s original-authored declaration, including the qualifications shown.')
        layout.addWidget(self.origin_declaration)
        self.table = QTableWidget(len(self._sources), 3)
        self.table.setHorizontalHeaderLabels(['Input', 'Content SHA-256', 'Private sprite permission'])
        self.checks = []
        for index, (name, digest) in enumerate(self._sources):
            label = ('Saved character' if name == 'master' else 'Expression library' if name == 'expression_library'
                     else 'Registered hand' if name.startswith('part:') else 'Selected motion')
            self.table.setItem(index, 0, QTableWidgetItem(label))
            self.table.setItem(index, 1, QTableWidgetItem(digest))
            check = QCheckBox('Reviewed and authorized'); self.checks.append(check)
            self.table.setCellWidget(index, 2, check); check.toggled.connect(self.refresh)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.resizeColumnsToContents(); layout.addWidget(self.table)
        fixed_policy = QLabel('Review every exact source separately for this private render. NoAI stays enabled; '
                              'UE-only inputs and source/sprite redistribution are not allowed.')
        fixed_policy.setWordWrap(True); layout.addWidget(fixed_policy)
        self.note = QLineEdit(); self.note.setMaxLength(2048)
        self.note.setPlaceholderText('Your reviewed license or authorization for this private sprite render')
        layout.addWidget(self.note)
        self.matte_consent = QCheckBox('Use the temporary opaque matte on render copies only; keep saved appearance unchanged.')
        layout.addWidget(self.matte_consent)
        layout.addWidget(QLabel('Fixed matte: RGB (0.55, 0.35, 0.25), roughness 1, no textures. The background is transparent.'))
        destination_row = QHBoxLayout()
        self.destination = QLineEdit(); self.destination.setPlaceholderText('New output folder outside the saved project')
        self.choose_destination = QPushButton('Choose output parent…'); self.choose_destination.clicked.connect(self.browse_destination)
        destination_row.addWidget(self.destination); destination_row.addWidget(self.choose_destination)
        layout.addLayout(destination_row)
        self.status = QLabel(); self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.render_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.render_button.setText('Verify and render sample')
        self.buttons.accepted.connect(self._accept); self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        for widget in (self.first_frame, self.frame_count): widget.valueChanged.connect(self.refresh)
        self.resolution.currentIndexChanged.connect(self.refresh)
        self.note.textChanged.connect(self.refresh); self.destination.textChanged.connect(self.refresh)
        self.origin_declaration.toggled.connect(self.refresh); self.matte_consent.toggled.connect(self.refresh)
        self.refresh()

    def _clear_consents(self):
        for check in (*self.checks, self.origin_declaration, self.matte_consent): check.setChecked(False)

    def browse_origin(self):
        if self._busy or not self._valid: return
        path, _ = QFileDialog.getOpenFileName(self, 'Choose original-motion record', '', 'JSON records (*.json);;All files (*)')
        if not path: return
        self._origin = None; self._pending_origin = Path(path)
        self.origin_path.setText(path); self._clear_consents()
        self.origin_summary.setText('Checking the selected origin record…')
        self.refresh(); self.origin_selected.emit(path)

    def set_origin_review(self, origin: OriginalMotionProvenance, summary: str, *, context_token: object) -> bool:
        if (not self._valid or context_token is not self.context_token
                or type(origin) is not OriginalMotionProvenance or origin.record_path != self._pending_origin):
            return False
        self._origin = origin; self._clear_consents()
        self.origin_summary.setText(summary + '\nRecord SHA-256: ' + origin.expected_sha256
                                    + '\nOrigin declaration only; this does not grant sprite rights or prove authorship.')
        self.refresh(); return True

    def set_origin_error(self, message: str, *, context_token: object):
        if context_token is not self.context_token or not self._valid: return
        self._origin = None; self._clear_consents(); self.origin_summary.setText(message); self.refresh()

    def invalidate(self, message: str):
        self._valid = False; self._origin = None; self._clear_consents()
        self.origin_summary.setText(message); self.refresh()

    def set_busy(self, busy: bool):
        self._busy = bool(busy); self.refresh()

    def browse_destination(self):
        if self._busy or not self._valid: return
        parent = QFileDialog.getExistingDirectory(self, 'Choose an output parent outside the saved project')
        if parent: self.destination.setText(str(Path(parent) / 'body-sprite-sample'))

    def _window(self):
        return BodySpriteWindow(self.first_frame.value(), self.first_frame.value() + self.frame_count.value() - 1)

    def _require_ready(self):
        if not self._valid: raise ValidationError('The saved character or selected motion review changed; review it again')
        if self._busy: raise ValidationError('Wait for the current review to finish')
        self._window()
        if self.resolution.currentData() not in (128, 256): raise ValidationError('Choose 128 or 256 pixels per image')
        if self._origin is None: raise ValidationError('Choose and review the original-motion record')
        if not self.origin_declaration.isChecked(): raise ValidationError('Acknowledge the original-motion declaration and qualifications')
        if not all(check.isChecked() for check in self.checks) or not self.note.text().strip():
            raise ValidationError('Separately authorize every source and enter the reviewed private-use note')
        if not self.matte_consent.isChecked(): raise ValidationError('Confirm the temporary matte on render copies')
        path = Path(self.destination.text().strip())
        if not self.destination.text().strip() or not path.is_absolute():
            raise ValidationError('Choose an absolute path for a new output folder outside the saved project')

    def refresh(self, *_):
        enabled = self._valid and not self._busy
        for widget in (self.first_frame, self.frame_count, self.resolution, self.choose_origin,
                       self.note, self.destination, self.choose_destination,
                       self.origin_declaration, self.matte_consent, *self.checks): widget.setEnabled(enabled)
        try:
            window = self._window()
        except ValidationError as error:
            self.window_summary.setText('Choose 1–32 consecutive target frames ending at or before frame 300.')
            self.render_button.setEnabled(False); self.status.setText(str(error)); return
        self.window_summary.setText(f'Selected target {window.target_first_frame}–{window.target_last_frame}; '
            f'source {window.source_frames[0]}–{window.source_frames[-1]}. '
            f'{window.sample_count} frames × 4 directions = {window.sample_count * 4} images. '
            f'Sample span {(window.sample_count - 1) / 30:.3f} s; nominal coverage {window.sample_count / 30:.3f} s.')
        try:
            self._require_ready()
        except ValidationError as error:
            self.render_button.setEnabled(False); self.status.setText(str(error)); return
        self.render_button.setEnabled(True); self.status.setText('Ready for source checks and private rendering.')

    def request(self) -> BodySpriteRequest:
        self._require_ready()
        permissions = tuple(SpritePermission(name, digest, self.note.text().strip(), True, True)
                            for name, digest in self._sources)
        return BodySpriteRequest(self._job_id, self._snapshot, self._binding, self._window(),
                                 SpriteSettings(self.resolution.currentData(), 4, 0., 0.),
                                 SkinMaterialSpec((.55, .35, .25), 1.), permissions, self._purpose, True)

    def origin_review(self) -> OriginalMotionProvenance:
        self._require_ready(); return self._origin

    def destination_path(self) -> Path:
        self._require_ready(); return Path(self.destination.text().strip())

    def _accept(self):
        try:
            self.request(); self.origin_review(); self.destination_path()
        except ValidationError as error:
            self.status.setText(str(error)); return
        self.accept()
