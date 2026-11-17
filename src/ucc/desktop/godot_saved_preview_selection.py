"""Review three explicit proof files and their exact per-source policies."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredRuntimeManifest, MAX_MANIFEST_BYTES
from ucc.export.godot_saved_preview import SelectedProofFile
from ucc.jobs.godot_registered_runtime_files import read_bytes, read_metadata
from ucc.jobs.target_action_context import operation_budget, protected


@dataclass(frozen=True, slots=True)
class ReviewedSavedPreviewFiles:
    draw_receipt: SelectedProofFile
    body_receipt: SelectedProofFile
    retained_manifest: SelectedProofFile
    permissions: tuple[EngineInputPermission, ...]


def review_saved_preview_files(draw: Path, body: Path, retained: Path, *, cancel=None):
    """Metadata review only; the separate loader validates the complete proof."""
    with operation_budget(cancel, 30) as budget:
        d, _, draw_sha = read_metadata(protected(Path(draw)), 4*1024*1024, budget)
        c, _, body_sha = read_metadata(protected(Path(body)), 4*1024*1024, budget)
        raw, manifest_sha = read_bytes(protected(Path(retained)), MAX_MANIFEST_BYTES, budget)
        manifest = RegisteredRuntimeManifest.from_bytes(raw)
        if (d.get('diagnostic_receipt_sha256') != body_sha
                or c.get('retention_manifest_sha256') != manifest_sha):
            raise ValidationError('The selected draw, body and retained inputs do not belong together')
        for permission in manifest.permissions:
            permission.require_godot()
        budget.check()
        return ReviewedSavedPreviewFiles(
            SelectedProofFile(Path(draw), draw_sha), SelectedProofFile(Path(body), body_sha),
            SelectedProofFile(Path(retained), manifest_sha), manifest.permissions)


class SavedPreviewPolicyDialog(QDialog):
    def __init__(self, reviewed: ReviewedSavedPreviewFiles, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Review saved Godot preview')
        self.resize(760, 600)
        layout = QVBoxLayout(self)
        label = QLabel('Open three saved images locally under the displayed source policies. '
                       'The complete saved proof and current character binding are checked before display.')
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        lines = []
        for label, proof in (('Draw receipt', reviewed.draw_receipt),
                             ('Body receipt', reviewed.body_receipt),
                             ('Retained manifest', reviewed.retained_manifest)):
            lines.extend((label + ': ' + str(proof.path), proof.sha256, ''))
        for permission in reviewed.permissions:
            policy = permission.policy
            lines.extend((permission.asset_id, permission.source_sha256,
                          policy.provider + ' / ' + policy.license_name, policy.source_uri,
                          f'Reviewed: {policy.reviewed}; NoAI: {policy.no_ai}; UE-only: {policy.ue_only}',
                          f'Per-use source-only input: {permission.source_only}; Unreal use: {policy.can_use_unreal}',
                          f'Local preview: {policy.local_preview_allowed}; cross-engine use: {policy.can_use_non_unreal}',
                          f'AI input: {policy.ai_input_allowed}; source redistribution: {policy.redistribute_source_allowed}', ''))
        self.details = QPlainTextEdit('\n'.join(lines))
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        self.consent = QCheckBox('I confirm these exact reviewed policies for this private local image preview.')
        self.consent.setChecked(False)
        layout.addWidget(self.consent)
        facts = QLabel('Private diagnostic frames only. Appearance, artist approval and shipping readiness remain unapproved.')
        facts.setWordWrap(True)
        facts.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(facts)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.open = buttons.addButton('Open verified frames', QDialogButtonBox.ButtonRole.AcceptRole)
        self.open.setEnabled(False)
        self.consent.toggled.connect(self.open.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
