"""Plaintext presentation of captured, immutable position-only diagnostics."""
from __future__ import annotations

import json

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from ucc.animations.target_action_diagnostic import TargetActionDiagnostics
from ucc.core.errors import ValidationError


class TargetActionDiagnosticDialog(QDialog):
    closed = Signal()

    def __init__(self, report: TargetActionDiagnostics, parent=None):
        super().__init__(parent)
        if type(report) is not TargetActionDiagnostics:
            raise ValidationError('A captured registered-clip diagnostic report is required')
        self.setWindowTitle('Private registered clip diagnostics')
        self.resize(780, 640)
        self.report: TargetActionDiagnostics | None = report
        self._closed = False
        if parent is not None:
            parent.installEventFilter(self)
        layout = QVBoxLayout(self)
        self.status = QLabel('Position-only diagnostic — no automatic loop or usable-action verdict.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        scope = QLabel(
            'Root world-head travel and source hip-midpoint travel are distinct measurements. '
            'The cached hip midpoint is not a root bone. Endpoint position gaps do not establish '
            'loop quality, gait, planted feet, contact, or orientation continuity. '
            'Walking, visual quality, engine delivery, shipping and all broader approvals remain false.')
        scope.setTextFormat(Qt.TextFormat.PlainText)
        scope.setWordWrap(True)
        layout.addWidget(scope)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        # The exact typed report owns this closed aggregate-only serialization.
        # No filesystem reads, guard callbacks, jobs or engine calls occur here.
        self.details.setPlainText(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False))
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def clear_report(self, message: str = 'Diagnostic report closed') -> None:
        self.report = None
        self.details.clear()
        self.status.setText(str(message))

    def closeEvent(self, event) -> None:
        self.clear_report()
        if not self._closed:
            self._closed = True
            self.closed.emit()
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parent() and event.type() == QEvent.Type.Close:
            self.close()
        return super().eventFilter(watched, event)
