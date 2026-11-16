"""Real Qt rights/selection controls; synthetic metadata is not engine evidence."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fixtures.godot_export_logic import review
from ucc.library.provenance import AssetPolicyError

try:
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 unavailable')
class UnityExportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop.unity_export_dialog import UnityExportDialog
        self.dialog = UnityExportDialog(review())
        self.addCleanup(self.dialog.close)
        self.addCleanup(self.dialog.deleteLater)

    def complete(self):
        d = self.dialog
        d.note.setText('UNIT_EXPLICIT_REVIEW_NOT_REAL_ASSET_AUTHORIZATION')
        d.editor.setText(str(Path.cwd()/'UNIT_INSTALLED_EDITOR_NOT_CREATED.exe'))
        d.destination.setText(str(Path.cwd()/'UNIT_EXPORT_NOT_CREATED'))
        for check in d.checks:
            check.setChecked(True)

    def test_no_default_rights_editor_or_destination(self):
        d = self.dialog
        self.assertFalse(d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        self.assertTrue(all(not check.isChecked() for check in d.checks))
        self.assertEqual(d.editor.text(), '')
        self.assertEqual(d.destination.text(), '')
        self.complete()
        self.assertTrue(d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        request = d.request('f'*64)
        self.assertEqual(request.unity_executable_sha256, 'f'*64)
        self.assertEqual(request.project_sha256, d.review.project_sha256)
        self.assertEqual(dict(request.source_bindings), {s.asset_id: s.sha256 for s in d.review.sources})
        self.assertTrue(all(p.policy.no_ai and not p.policy.ai_input_allowed
                            and not p.policy.redistribute_source_allowed for p in request.permissions))

    def test_each_review_selection_and_authorization_is_required(self):
        self.complete()
        d = self.dialog
        button = d.buttons.button(QDialogButtonBox.StandardButton.Ok)
        for check in d.checks:
            check.setChecked(False)
            self.assertFalse(button.isEnabled())
            with self.assertRaises(AssetPolicyError):
                d.request('f'*64)
            check.setChecked(True)
        for field in (d.note, d.editor, d.destination):
            text = field.text()
            field.setText(' ')
            self.assertFalse(button.isEnabled())
            field.setText(text)
        self.assertTrue(button.isEnabled())

    def test_cancelled_pickers_retain_draft_without_scanning(self):
        self.complete()
        d = self.dialog
        selected = d.editor.text(), d.destination.text()
        with patch('ucc.desktop.unity_export_dialog.QFileDialog.getOpenFileName', return_value=('', '')):
            d.browse_editor()
        with patch('ucc.desktop.unity_export_dialog.QFileDialog.getExistingDirectory', return_value=''):
            d.browse_destination()
        self.assertEqual((d.editor.text(), d.destination.text()), selected)
