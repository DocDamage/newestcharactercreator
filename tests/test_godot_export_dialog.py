"""Real Qt review defaults/controls; synthetic source metadata, no rights claim."""
import os,unittest
from pathlib import Path
from unittest.mock import patch
from fixtures.godot_export_logic import review
try:
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
except ImportError:QApplication=None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class GodotDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop.godot_export_dialog import GodotExportDialog
        self.dialog=GodotExportDialog(review());self.addCleanup(self.dialog.close)

    def test_no_default_rights_destination_or_implicit_policy_upgrade(self):
        d=self.dialog;button=d.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(button.isEnabled());self.assertTrue(all(not c.isChecked() for c in d.checks));self.assertEqual(d.destination.text(),'')
        d.note.setText('UNIT_EXPLICIT_REVIEW_NOT_REAL_ASSET_AUTHORIZATION');d.destination.setText(str(Path.cwd()/'UNIT_EXPORT_NOT_CREATED'))
        for check in d.checks:check.setChecked(True)
        self.assertTrue(button.isEnabled());request=d.request()
        self.assertEqual(len(request.permissions),len(review().sources))
        self.assertTrue(all(p.policy.no_ai and not p.policy.ai_input_allowed and not p.policy.redistribute_source_allowed for p in request.permissions))
        d.checks[0].setChecked(False);self.assertFalse(button.isEnabled())

    def test_cancelled_parent_picker_keeps_existing_draft(self):
        d=self.dialog;d.destination.setText('UNIT_DRAFT')
        with patch('ucc.desktop.godot_export_dialog.QFileDialog.getExistingDirectory',return_value=''):d.browse()
        self.assertEqual(d.destination.text(),'UNIT_DRAFT')
