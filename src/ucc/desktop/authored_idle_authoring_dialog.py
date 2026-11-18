"""Review the exact character sources and destinations for one private idle."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ucc.core.authored_idle import IdleAuthoringPermission
from ucc.core.errors import UCCError, ValidationError
from ucc.core.target_action_format import checked_text
from ucc.jobs.authored_idle_policy import IdleSourcePolicyRecord
from ucc.jobs.authored_idle_sources import IdleAuthoringSource
from ucc.jobs.target_action_context import Budget, protected


@dataclass(frozen=True, slots=True)
class AuthoredIdleAuthoringChoice:
    source_policy_records: tuple[IdleSourcePolicyRecord, ...]
    permissions: tuple[IdleAuthoringPermission, ...]
    purpose: str
    original_procedural_recipe_declared: bool
    private_authored_output_preview_confirmed: bool
    candidate_destination: Path
    proof_destination: Path | None


@dataclass(slots=True)
class _SourceRow:
    source: IdleAuthoringSource
    choose: QPushButton
    review: QLabel
    confirm: QCheckBox
    note: QLineEdit
    record: IdleSourcePolicyRecord | None = None


def _label(text: str) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class AuthoredIdleAuthoringDialog(QDialog):
    def __init__(self, sources: tuple[IdleAuthoringSource, ...], parent=None):
        super().__init__(parent)
        if (type(sources) is not tuple or not 1 <= len(sources) <= 3
                or any(type(source) is not IdleAuthoringSource for source in sources)):
            raise ValidationError('Review the exact saved character sources first')
        asset_ids = tuple(source.asset_id for source in sources)
        if asset_ids != tuple(sorted(set(asset_ids))) or 'master_and_derived_rig' not in asset_ids:
            raise ValidationError('Review the complete saved source set in order')
        hands = tuple(asset_id for asset_id in asset_ids
                      if asset_id not in {'master_and_derived_rig', 'expression_library'})
        if len(hands) > 1 or any(not re.fullmatch(r'part:ucc-hand-v1-[a-f0-9]{64}-(shorter|longer)', row)
                                for row in hands):
            raise ValidationError('Review the supported saved character sources first')

        self.choice: AuthoredIdleAuthoringChoice | None = None
        self.setWindowTitle('Create private original idle')
        self.resize(800, 660)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout.addWidget(_label('Review each source for the original idle recipe and private use of the derived rig. '
            'This creates a local candidate from the saved character. Registration and visual review are separate.'))

        self.rows: list[_SourceRow] = []
        for source in sources:
            title = {'master_and_derived_rig': 'Saved character and derived rig',
                     'expression_library': 'Expression library'}.get(source.asset_id, 'Registered left hand')
            section = QGroupBox(title)
            row_layout = QVBoxLayout(section)
            identity_label = _label(f'{source.asset_id}\nSource SHA-256 {source.sha256}\n'
                                    f'Provenance SHA-256 {source.provenance_sha256}')
            identity_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_layout.addWidget(identity_label)
            choose = QPushButton('Choose reviewed policy…')
            choose.setAccessibleName('Choose reviewed policy for ' + title)
            review = _label('Choose an existing local policy record for this source.')
            confirm = QCheckBox('I confirm private idle authoring and derived-rig use for this source.')
            confirm.setAccessibleName('Confirm private authoring for ' + title)
            note = QLineEdit()
            note.setMaxLength(2000)
            note.setPlaceholderText('Record your authorization for this use')
            note.setAccessibleName('Per-use authorization note for ' + title)
            for widget in (choose, review, confirm, note):
                row_layout.addWidget(widget)
            row = _SourceRow(source, choose, review, confirm, note)
            self.rows.append(row)
            choose.clicked.connect(lambda _checked=False, selected=row: self._choose_policy(selected))
            confirm.toggled.connect(self._refresh)
            note.textChanged.connect(self._refresh)
            layout.addWidget(section)

        form = QFormLayout()
        self.purpose = QLineEdit()
        self.purpose.setMaxLength(2000)
        self.recipe = QCheckBox('I declare use of the original procedural idle recipe.')
        self.preview = QCheckBox('I authorize private local preview of the authored output.')
        self.output_parent = QLineEdit()
        self.output_parent.setReadOnly(True)
        self.choose_parent = QPushButton('Choose output parent…')
        self.choose_parent.clicked.connect(self._choose_parent)
        parent_row = QHBoxLayout()
        parent_row.addWidget(self.output_parent, 1)
        parent_row.addWidget(self.choose_parent)
        self.candidate_name = QLineEdit()
        self.candidate_name.setMaxLength(120)
        self.write_proof = QCheckBox('Also save a local loop review proof beside the candidate.')
        self.proof_name = QLineEdit()
        self.proof_name.setMaxLength(120)
        form.addRow('Purpose', self.purpose)
        form.addRow(self.recipe)
        form.addRow(self.preview)
        form.addRow('Output parent', parent_row)
        form.addRow('New candidate folder name', self.candidate_name)
        form.addRow(self.write_proof)
        form.addRow('New proof folder name', self.proof_name)
        layout.addLayout(form)
        self.status = _label('')
        outer.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.create_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.create_button.setText('Create private candidate')
        self.create_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        for widget in (self.purpose, self.output_parent, self.candidate_name, self.proof_name):
            widget.textChanged.connect(self._refresh)
        for widget in (self.recipe, self.preview, self.write_proof):
            widget.toggled.connect(self._refresh)
        self._refresh()

    def _choose_policy(self, row: _SourceRow) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, 'Choose reviewed idle source policy', '', 'JSON records (*.json)')
        if not selected:
            return
        row.record = None
        row.confirm.setChecked(False)
        row.note.clear()
        try:
            path = _local_path(selected)
            if not path.is_file() or path.stat().st_nlink != 1:
                raise ValidationError('Choose one local single-link policy file')
            with path.open('rb') as stream:
                payload = stream.read(256 * 1024 + 1)
            if len(payload) > 256 * 1024:
                raise ValidationError('The selected idle policy file is too large')
            record = IdleSourcePolicyRecord(row.source.asset_id, path, sha256(payload).hexdigest())
            document = record.read(row.source.sha256, row.source.provenance_sha256, Budget(None, 5))
            row.record = record
            row.review.setText(f'{path.name}\nPolicy SHA-256 {record.sha256}\n{document["review_note"]}')
        except (UCCError, OSError, ValueError) as error:
            row.review.setText(str(error) if isinstance(error, UCCError) else 'The selected local policy could not be read.')
        self._refresh()

    def _choose_parent(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, 'Choose private idle output parent outside the saved project')
        if selected:
            self.output_parent.setText(selected)

    def _refresh(self, *_) -> None:
        for row in self.rows:
            for widget in (row.confirm, row.note):
                widget.setEnabled(row.record is not None)
        self.proof_name.setEnabled(self.write_proof.isChecked())
        try:
            self._choice()
        except (UCCError, OSError, ValueError) as error:
            self.create_button.setEnabled(False)
            self.status.setText(str(error))
        else:
            self.create_button.setEnabled(True)
            self.status.setText('Ready to create the private candidate using the configured Blender profile.')

    def _choice(self) -> AuthoredIdleAuthoringChoice:
        records = []
        permissions = []
        for row in self.rows:
            record = row.record
            if record is None:
                raise ValidationError('Choose the matching reviewed policy for every source.')
            note = row.note.text().strip()
            if not row.confirm.isChecked() or not note:
                raise ValidationError('Confirm each private authoring use separately and enter its authorization note.')
            permissions.append(IdleAuthoringPermission(row.source.asset_id, row.source.sha256, record.sha256, note, True))
            records.append(record)
        purpose = self.purpose.text().strip()
        if not purpose:
            raise ValidationError('Enter the purpose of this private candidate.')
        checked_text(purpose, 2000)
        if not self.recipe.isChecked() or not self.preview.isChecked():
            raise ValidationError('Declare the original recipe and confirm private local preview separately.')
        parent = _local_path(self.output_parent.text())
        if not parent.is_dir():
            raise ValidationError('Choose an existing local output parent.')
        candidate = _new_folder(parent, self.candidate_name.text())
        proof = _new_folder(parent, self.proof_name.text()) if self.write_proof.isChecked() else None
        if proof is not None and candidate.name.casefold() == proof.name.casefold():
            raise ValidationError('Choose distinct candidate and proof folder names.')
        return AuthoredIdleAuthoringChoice(tuple(records), tuple(permissions), purpose, True, True, candidate, proof)

    def accept(self) -> None:
        self.choice = None
        try:
            choice = self._choice()
            budget = Budget(None, 5)
            for row, record in zip(self.rows, choice.source_policy_records):
                record.read(row.source.sha256, row.source.provenance_sha256, budget)
        except (UCCError, OSError, ValueError) as error:
            self.status.setText(str(error) if isinstance(error, UCCError) else 'Review the selected policies and output folders again.')
            return
        self.choice = choice
        super().accept()


def _local_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or value.startswith(('\\\\', '//')):
        raise ValidationError('Choose an absolute local path.')
    return protected(path)


def _new_folder(parent: Path, name: str) -> Path:
    if (not name or name != name.strip() or name.endswith('.') or any(c in name for c in '<>:"/\\|?*')
            or any(ord(c) < 32 for c in name)):
        raise ValidationError('Enter a valid name for each new output folder.')
    path = protected(parent/name)
    if path.exists():
        raise ValidationError('Choose a folder name that does not already exist.')
    return path
