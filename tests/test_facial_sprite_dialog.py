"""Actual Qt camera/rights/strength review; no Blender render claims."""
import os,unittest
try:
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
except ImportError:QApplication=None
from fixtures.facial_sprite_logic import request
from fixtures.godot_export_logic import review
from ucc.core.errors import ValidationError


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class FacialSpriteDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_saved_clip_settings_and_four_explicit_source_permissions(self):
        from ucc.desktop.facial_sprite_dialog import FacialSpriteDialog
        dialog=FacialSpriteDialog(review(),request().clip);self.addCleanup(dialog.close)
        button=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(button.isEnabled());self.assertTrue(all(not c.isChecked() for c in dialog.checks))
        dialog.note.setText('UNIT_ONLY_ANIMATED_RENDER_GRANT');dialog.destination.setText('UNIT_NEW_FACIAL_SPRITES')
        with self.assertRaises(ValidationError):dialog.request()
        for check in dialog.checks:check.setChecked(True)
        dialog.resolution.setCurrentIndex(0);dialog.directions.setCurrentIndex(1);dialog.yaw.setValue(15);dialog.pitch.setValue(10)
        result=dialog.request();self.assertTrue(button.isEnabled());self.assertEqual(result.review.settings.resolution,128)
        self.assertEqual(result.review.settings.directions,8);self.assertEqual(result.clip['timeline']['last_frame'],25)
        self.assertEqual(result.clip['parameters'],request().clip['parameters']);self.assertTrue(all(p.no_ai for p in result.review.permissions))
