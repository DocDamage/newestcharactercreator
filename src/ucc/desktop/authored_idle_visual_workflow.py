"""Collect and save the reviewer's own decision for the current private idle."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QInputDialog, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from ucc.core.errors import ProjectConflict, ProjectStorageError, UCCError, ValidationError
from ucc.jobs.export_destination import plan_destination


KIND = 'target_action_idle_visual_decision'


class IdleVisualDecisionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Record idle visual decision')
        layout = QVBoxLayout(self)
        guidance = QLabel(
            'Review the stance and motion, hands and body clearance, feet and root, and the loop transition. '
            'This records your assessment for the current private idle.')
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        form = QFormLayout()
        self.decision = QComboBox()
        self.decision.addItem('Choose a decision', None)
        self.decision.addItem('Approve visual review', 'approve')
        self.decision.addItem('Needs changes', 'rework')
        self.reviewer = QLineEdit()
        self.reviewer.setMaxLength(160)
        self.note = QPlainTextEdit()
        form.addRow('Decision', self.decision)
        form.addRow('Reviewer', self.reviewer)
        form.addRow('Review notes', self.note)
        layout.addLayout(form)
        self.attest = QCheckBox('I viewed this exact idle and this is my own decision.')
        layout.addWidget(self.attest)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.save = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.save.setText('Choose decision folder…')
        self.save.setAutoDefault(False)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.decision.currentIndexChanged.connect(self._refresh)
        self.reviewer.textChanged.connect(self._refresh)
        self.note.textChanged.connect(self._refresh)
        self.attest.toggled.connect(self._refresh)
        self._refresh()

    def _ready(self) -> bool:
        note = self.note.toPlainText().strip()
        return bool(self.decision.currentData() and self.reviewer.text().strip()
                    and note and len(note) <= 2000 and self.attest.isChecked())

    def _refresh(self) -> None:
        self.save.setEnabled(self._ready())

    def accept(self) -> None:
        if self._ready():
            super().accept()

    def declaration(self):
        from ucc.core.authored_idle_visual_review import AuthoredIdleVisualDecision

        if self.result() != QDialog.DialogCode.Accepted or not self._ready():
            raise ValidationError('Complete your own visual review before saving a decision')
        return AuthoredIdleVisualDecision(self.decision.currentData(), self.reviewer.text().strip(),
                                          self.note.toPlainText().strip(), self.attest.isChecked())


def start_visual_decision(window, context, proof_file: Path, admitted, still_current) -> None:
    from .target_action_workflow import _submit

    try:
        if window.jobs.busy or not still_current():
            raise ProjectConflict('Load and review the current idle loop before recording a visual decision')
        dialog = IdleVisualDecisionDialog(window)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            decision = dialog.declaration()
        finally:
            dialog.deleteLater()
        parent = QFileDialog.getExistingDirectory(window, 'Choose parent folder for the idle visual decision')
        if not parent:
            return
        name, selected = QInputDialog.getText(window, 'Save idle visual decision', 'New output folder name',
                                              text='idle-visual-decision')
        if not selected:
            return
        if not name or name in {'.', '..'} or any(character in name for character in '<>:"/\\|?*'):
            raise ValidationError('Enter a new local folder name for the idle visual decision')
        if window.jobs.busy or not still_current():
            raise ProjectConflict('The current idle loop changed while entering the decision')
        destination = plan_destination(Path(parent)/name, context.store.root)

        def operation(cancel, _progress):
            from ucc.jobs.authored_idle_visual_review import publish_authored_idle_visual_decision

            try:
                identity = admitted.review_identity
                return publish_authored_idle_visual_decision(
                    context.store, proof_file=proof_file, selection=identity.selection,
                    database_path=context.database, expected_identity=identity, decision=decision,
                    destination=destination, cancel=cancel)
            except (UCCError, OSError) as error:
                notes = getattr(error, '__notes__', ())
                if notes:
                    raise ProjectStorageError('\n'.join((str(error), *notes))) from error
                raise

        _submit(window, KIND, operation, progress=True)
    except (UCCError, OSError, ValueError) as error:
        window._error(str(error))


def finish_visual_decision(window, result) -> None:
    from ucc.jobs.authored_idle_visual_review import PublishedAuthoredIdleVisualDecision
    from .target_action_workflow import _close_progress

    _close_progress(window)
    if type(result) is not PublishedAuthoredIdleVisualDecision:
        window._error('Unexpected private visual decision result')
        return
    window.log.setPlainText(f'Saved private idle visual decision at {result.path}\nDecision SHA-256 {result.sha256}')
    window.statusBar().showMessage('Private visual decision saved')


def visual_decision_error(window, error: str) -> None:
    from .target_action_workflow import _close_progress

    _close_progress(window)
    window._error(error)
