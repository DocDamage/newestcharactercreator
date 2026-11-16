"""Qt permission/selection tests using nonshipping metadata, never a real Action."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from types import SimpleNamespace
import unittest

from ucc.library.provenance import LicensePolicy

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.target_action_dialog import TargetActionDialog
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 not installed')
class TargetActionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Target Action Qt tests require PySide6')
        cls.app = QApplication.instance() or QApplication(['target-action-dialog-tests'])

    def setUp(self):
        self.clips = ('unit-original#clip-0000', 'unit-other#clip-0000')
        self.dialog = TargetActionDialog(self.clips)
        self.addCleanup(self.dialog.deleteLater)
        self.review = SimpleNamespace(source=SimpleNamespace(clip_id=self.clips[0], source_sha256='a'*64),
            policy=LicensePolicy('Unit author', 'Nonshipping unit fixture', 'unit:test',
                                 reviewed=True, no_ai=True, local_preview_allowed=True))
        self.saved = SimpleNamespace(clip_id=self.clips[0], binding_sha256='b'*64)
        self.dialog.set_review(self.review, (self.saved,))

    def test_consent_and_saved_selection_are_never_automatic(self):
        d = self.dialog
        self.assertFalse(d.consent.isChecked())
        self.assertIsNone(d.bindings.currentData())
        self.assertFalse(d.prepare.isEnabled())
        self.assertFalse(d.load.isEnabled())
        self.assertFalse(d.clips.isEditable())
        self.assertIn('Source-only', d.source_details.toPlainText())
        self.assertTrue(any('engine use remain unapproved' in label.text()
                            for label in d.findChildren(type(d.status))))

    def test_new_preview_requires_purpose_exact_map_and_reconfirmation(self):
        d = self.dialog
        d.purpose.setText('Private nonshipping target test')
        d.consent.setChecked(True)
        self.assertFalse(d.prepare.isEnabled())
        d.set_mapping(Path('unit-map.json'), 'c'*64)
        self.assertFalse(d.consent.isChecked())
        self.assertFalse(d.prepare.isEnabled())
        d.consent.setChecked(True)
        self.assertTrue(d.prepare.isEnabled())
        d.purpose.setText('   ')
        self.assertFalse(d.prepare.isEnabled())
        d.purpose.setText('Private nonshipping target test')
        d.prepare.click()
        self.assertEqual(d.choice.operation, 'prepare')
        self.assertEqual(d.choice.clip_id, self.clips[0])
        self.assertEqual(d.choice.mapping_sha256, 'c'*64)
        self.assertTrue(d.choice.local_preview_confirmed)

    def test_saved_load_requires_explicit_sha_and_consent_but_no_new_map(self):
        d = self.dialog
        d.bindings.setCurrentIndex(1)
        self.assertFalse(d.load.isEnabled())
        d.consent.setChecked(True)
        self.assertTrue(d.load.isEnabled())
        self.assertFalse(d.prepare.isEnabled())
        d.load.click()
        self.assertEqual(d.choice.operation, 'load')
        self.assertEqual(d.choice.binding_sha256, 'b'*64)
        self.assertIsNone(d.choice.mapping_profile)
        self.assertIsNone(d.choice.mapping_sha256)

    def test_changing_registered_source_discards_old_review_map_and_permission(self):
        d = self.dialog
        requested = []
        d.source_requested.connect(requested.append)
        d.set_mapping(Path('unit-map.json'), 'c'*64)
        d.purpose.setText('Unit preview')
        d.consent.setChecked(True)
        d.bindings.setCurrentIndex(1)
        d.clips.setCurrentIndex(1)
        self.assertEqual(requested, [self.clips[1]])
        self.assertIsNone(d.review)
        self.assertIsNone(d.mapping_sha256)
        self.assertFalse(d.consent.isChecked())
        self.assertIsNone(d.bindings.currentData())
        self.assertFalse(d.prepare.isEnabled())
        self.assertFalse(d.load.isEnabled())
        d.set_review(self.review, (self.saved,))
        self.assertIsNone(d.review, 'Late review for another source must not be adopted')

    def test_busy_disables_choices_and_actions(self):
        d = self.dialog
        d.bindings.setCurrentIndex(1)
        d.consent.setChecked(True)
        self.assertTrue(d.load.isEnabled())
        d.set_busy(True)
        self.assertFalse(d.clips.isEnabled())
        self.assertFalse(d.choose_mapping.isEnabled())
        self.assertFalse(d.load.isEnabled())
        self.assertFalse(d.prepare.isEnabled())
        d.set_busy(False)
        self.assertTrue(d.load.isEnabled())


if __name__ == '__main__':
    unittest.main()
