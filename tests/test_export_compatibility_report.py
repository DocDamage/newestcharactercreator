"""Required-Qt coverage with synthetic receipt metadata for the shared export report."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock
import json
import os
import tempfile
import unittest

from fixtures.godot_export_logic import receipt_result

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QTreeWidget, QWidget,
    )
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class ExportCompatibilityReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.window = QWidget()
        self.addCleanup(self.window.deleteLater)
        self.window.log = QPlainTextEdit(self.window)
        self.window._error = Mock()

    def assert_no_report(self):
        self.window._error.assert_called_once()
        self.assertIsNone(self.window.findChild(QDialog, 'exportCompatibilityReport'))
        self.assertNotIn('package created', self.window.log.toPlainText())

    def test_godot_completion_displays_verified_static_scope_with_pending_checks(self):
        from ucc.desktop.godot_export_workflow import finish_export

        result = receipt_result(self.root/'UNIT_GODOT_RECEIPT')
        finish_export(self.window, result)
        self.window._error.assert_not_called()
        report = self.window.findChild(QDialog, 'exportCompatibilityReport')
        self.assertIsNotNone(report)
        self.addCleanup(report.close)
        self.assertEqual(report.windowTitle(), 'Export quality and compatibility')
        scope = report.findChild(QLabel, 'exportCompatibilityScope').text()
        self.assertIn('Godot reopened the saved static scene', scope)
        self.assertIn(str(result.destination), self.window.log.toPlainText())
        details = report.findChild(QTreeWidget, 'exportCompatibilityDetails')
        rows = [details.topLevelItem(index) for index in range(details.topLevelItemCount())]
        self.assertEqual([(row.text(0), row.text(1)) for row in rows], [
            ('Export files', 'Generated'),
            ('Offline checks', 'Verified'),
            ('Engine import and reopen', 'Verified'),
            ('Animation playback', 'Not tested'),
            ('Player build', 'Not tested'),
            ('Visual quality', 'Not reviewed'),
            ('Distribution rights', 'Not reviewed'),
        ])

    def test_report_is_modeless_accessible_and_keyboard_dismissible(self):
        from ucc.desktop.export_compatibility_report import ExportProfile, show_export_compatibility

        show_export_compatibility(self.window, ExportProfile.GODOT, self.root)
        report = self.window.findChild(QDialog, 'exportCompatibilityReport')
        self.assertIsNotNone(report)
        self.addCleanup(report.close)
        self.assertTrue(report.isVisible())
        self.assertEqual(report.windowModality(), Qt.WindowModality.NonModal)
        self.assertIsNone(self.app.activeModalWidget())
        details = report.findChild(QTreeWidget, 'exportCompatibilityDetails')
        accessible = QAccessible.queryAccessibleInterface(details)
        self.assertIsNotNone(accessible)
        self.assertEqual(accessible.text(QAccessible.Text.Name), 'Export compatibility checks')
        self.assertNotEqual(details.focusPolicy(), Qt.FocusPolicy.NoFocus)
        buttons = report.findChild(QDialogButtonBox, 'exportCompatibilityButtons')
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        self.assertTrue(close.isEnabled())
        self.assertNotEqual(close.focusPolicy(), Qt.FocusPolicy.NoFocus)
        QTest.keyClick(report, Qt.Key.Key_Escape)
        self.assertFalse(report.isVisible())

    def test_changed_godot_receipt_cannot_show_a_success_report(self):
        from ucc.desktop.godot_export_workflow import finish_export

        result = receipt_result(self.root/'UNIT_GODOT_RECEIPT')
        (result.destination/'export_receipt.json').write_bytes(b'UNIT_TAMPERED_RECEIPT')
        finish_export(self.window, result)
        self.assert_no_report()
        self.assertIn('receipt changed', self.window._error.call_args.args[0].lower())

    def test_godot_rejects_unverified_import_even_with_current_receipt_digest(self):
        from ucc.desktop.godot_export_workflow import finish_export
        from ucc.export.godot_candidate_contract import canonical_bytes

        result = receipt_result(self.root/'UNIT_GODOT_RECEIPT')
        receipt = result.destination/'export_receipt.json'
        record = json.loads(receipt.read_bytes())
        record['private_godot_import_verified'] = False
        data = canonical_bytes(record)
        receipt.write_bytes(data)
        finish_export(self.window, replace(result, receipt_sha256=sha256(data).hexdigest()))
        self.assert_no_report()

    def test_godot_completion_requires_a_receipt_digest(self):
        from ucc.desktop.godot_export_workflow import finish_export

        result = receipt_result(self.root/'UNIT_GODOT_RECEIPT')
        for invalid in (None, '', False):
            with self.subTest(invalid=invalid):
                self.window._error.reset_mock()
                finish_export(self.window, replace(result, receipt_sha256=invalid))
                self.assert_no_report()
