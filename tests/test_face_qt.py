"""Actual Qt facial controls and session boundaries; worker acceptance is separate."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication = None
    IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 unavailable')
class FaceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Facial Qt tests required: '+IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['face-tests'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.controller = DesktopController(); self.controller.create(Path(self.temp.name)/'project', 'Face test')
        self.window = MainWindow(self.controller); self.addCleanup(self.window.deleteLater)

    def test_control_is_separate_bounded_and_explicitly_persistent(self):
        face = self.window.character.face
        self.assertEqual(set(self.window.character.sliders), {'height', 'muscle', 'weight'})
        self.assertEqual((face.slider.minimum(), face.slider.maximum(), face.slider.value()), (0, 1000, 500))
        self.assertFalse(face.apply.isEnabled())
        before = self.controller.store.file.read_bytes()
        face.slider.setValue(800); face.slider.sliderReleased.emit()
        self.assertEqual(self.controller.require_project().schema_version, 2)
        self.assertEqual(dict(self.controller.view().facial_parameters), {'nose_width': .8})
        self.assertTrue(self.controller.dirty)
        self.assertEqual(self.controller.store.file.read_bytes(), before)
        self.window.save_project()
        self.assertEqual(dict(self.controller.store.load().facial_parameters), {'nose_width': .8})
        self.window.undo()
        self.assertEqual(self.controller.require_project().schema_version, 1)
        self.window.redo()
        self.assertEqual(face.value.value(), .8)

    def test_keyboard_slider_edit_records_intent(self):
        QTest.keyClick(self.window.character.face.slider, Qt.Key.Key_Right)
        self.assertEqual(dict(self.controller.require_project().facial_parameters), {'nose_width': .501})
        self.assertTrue(self.controller.dirty)

    def test_default_neutral_does_not_migrate_or_clear_preview(self):
        with patch.object(self.window, '_clear_preview') as clear:
            self.window.character.face.slider.sliderReleased.emit()
        clear.assert_not_called()
        self.assertFalse(self.controller.dirty)
        self.assertEqual(self.controller.require_project().schema_version, 1)

    def test_meaningful_face_edit_and_history_clear_both_previews(self):
        with patch.object(self.window, '_clear_preview') as clear:
            self.window.character.face.value.setValue(.2)
            self.window.character.face.value.editingFinished.emit()
            self.window.undo(); self.window.redo()
        self.assertEqual(clear.call_count, 3)

    def test_unsaved_face_cannot_dispatch_and_busy_action_is_cancellable(self):
        from ucc.desktop.face_workflow import start_face
        self.controller.set_face_parameter('nose_width', .8)
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_face(self.window)
        submit.assert_not_called()
        self.assertIn('Save', error.call_args.args[0])
        self.window._work_kind = 'face_revision'
        self.window._busy_changed(True)
        self.assertFalse(self.window.character.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertIn('face shape', self.window.statusBar().currentMessage())
        self.window._busy_changed(False)


if __name__ == '__main__':
    unittest.main()
