"""Qt presentation tests using NONSHIPPING scalar-only synthetic diagnostics."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from fixtures.target_action_diagnostic_ui_logic import synthetic_report
from ucc.core.errors import ValidationError
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.target_action_diagnostic_dialog import TargetActionDiagnosticDialog
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class DiagnosticDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Diagnostic dialog tests require Qt')
        cls.app = QApplication.instance() or QApplication(['diagnostic-dialog-tests'])

    def test_captured_report_plaintext_scope_and_exact_identity(self):
        report = synthetic_report()
        dialog = TargetActionDiagnosticDialog(report)
        self.addCleanup(dialog.deleteLater)
        self.assertIs(dialog.report, report)
        self.assertEqual(dialog.status.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn(report.selection.binding_sha256, dialog.details.toPlainText())
        self.assertIn('"automatic_threshold_pass": false', dialog.details.toPlainText())
        self.assertIn('not a root bone', dialog.findChildren(type(dialog.status))[1].text())

    def test_clear_and_close_remove_measurements_and_report_emit_once(self):
        dialog = TargetActionDiagnosticDialog(synthetic_report())
        self.addCleanup(dialog.deleteLater)
        calls = []
        dialog.closed.connect(lambda: calls.append(dialog.report))
        dialog.clear_report('<b>changed</b>')
        self.assertIsNone(dialog.report)
        self.assertEqual(dialog.details.toPlainText(), '')
        self.assertEqual(dialog.status.text(), '<b>changed</b>')
        dialog.close(); dialog.close()
        self.assertEqual(calls, [None])

    def test_untyped_reports_rejected(self):
        for raw in (None, {}, synthetic_report().to_dict()):
            with self.assertRaises(ValidationError):
                TargetActionDiagnosticDialog(raw)


if __name__ == '__main__':
    unittest.main()
