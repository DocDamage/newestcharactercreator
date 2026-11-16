"""Actual Qt review/settings defaults; metadata fixtures are not render proof."""
import os,unittest
from unittest.mock import patch
from pathlib import Path
try:
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
except ImportError:
    QApplication=None
from fixtures.godot_export_logic import review
from ucc.core.errors import ValidationError


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 not installed')
class SpriteDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_no_default_rights_and_exact_camera_request(self):
        from ucc.desktop.sprite_dialog import SpriteRenderDialog
        dialog=SpriteRenderDialog(review());self.addCleanup(dialog.close)
        button=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(button.isEnabled());self.assertTrue(all(not c.isChecked() for c in dialog.checks))
        self.assertEqual(dialog.resolution.currentData(),256);self.assertEqual(dialog.directions.currentData(),4)
        dialog.note.setText('UNIT_ONLY reviewed private sprite rights');dialog.destination.setText(str(Path.cwd()/'UNIT_NEW_SPRITES'))
        self.assertFalse(button.isEnabled())
        with self.assertRaises(ValidationError):dialog.request()
        for c in dialog.checks:c.setChecked(True)
        dialog.resolution.setCurrentIndex(0);dialog.directions.setCurrentIndex(1);dialog.yaw.setValue(-45);dialog.pitch.setValue(15)
        request=dialog.request();self.assertTrue(button.isEnabled());self.assertEqual(request.settings.angles(),(315,0,45,90,135,180,225,270))
        self.assertEqual(request.settings.resolution,128);self.assertEqual(request.settings.pitch_deg,15)
        self.assertTrue(all(p.no_ai and not p.redistribute_source_allowed for p in request.permissions))
        self.assertEqual(dict(request.source_bindings),{s.asset_id:s.sha256 for s in dialog.review.sources})

    def test_cancelled_picker_retains_current_destination(self):
        from ucc.desktop.sprite_dialog import SpriteRenderDialog
        dialog=SpriteRenderDialog(review());self.addCleanup(dialog.close);dialog.destination.setText('existing local draft')
        with patch('ucc.desktop.sprite_dialog.QFileDialog.getExistingDirectory',return_value=''):dialog.browse()
        self.assertEqual(dialog.destination.text(),'existing local draft')
