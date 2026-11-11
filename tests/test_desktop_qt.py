"""Actual offscreen PySide6 widgets; optional locally, mandatory on desktop CI."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
from pathlib import Path
import unittest

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "Install PySide6 [desktop] extra to exercise actual Qt UI")
class DesktopQtSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["ucc-qt-tests"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.controller = DesktopController()
        self.controller.create(Path(self.tmp.name) / "hero", "Testing Hero")
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.deleteLater)

    def test_real_qt_tabs_and_save_action(self):
        self.assertEqual(self.window.tabs.count(), 3)
        self.assertEqual(self.window.character.heading.text(), "Testing Hero")
        self.assertFalse(self.window.save_action.isEnabled())
        self.window.rename("Changed Hero")
        self.assertTrue(self.window.save_action.isEnabled())
        self.window.save_project()
        self.assertFalse(self.window.save_action.isEnabled())
        self.assertEqual(self.controller.view().name, "Changed Hero")

    def test_slider_and_advanced_anatomy_controls(self):
        self.assertFalse(self.window.character.advanced.isVisible())
        self.window.character.mode.setCurrentText("Advanced")
        # setVisible may be false until window shown, but the group isn't hidden by mode.
        self.assertFalse(self.window.character.advanced.isHidden())
        self.assertGreater(self.window.character.slot_table.rowCount(), 30)
        slider = self.window.character.sliders["muscle"]
        slider.setValue(650)
        slider.sliderReleased.emit()
        self.assertAlmostEqual(dict(self.controller.view().morphs)["muscle"], .65)
        self.window.undo()
        self.assertAlmostEqual(dict(self.controller.view().morphs)["muscle"], .5)

    def test_tools_are_real_and_cannot_claim_geometry(self):
        self.assertIn("PNG", self.window.tools.pack.text())
        self.assertFalse(self.window.character.open_master.isEnabled())
        self.assertIn("not yet implemented", self.window.character.note.text())
        self.assertIn("local", self.window.tools.ai.text())


if __name__ == "__main__":
    unittest.main()
