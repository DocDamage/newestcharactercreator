"""Actual offscreen PySide6 widgets; optional locally, mandatory on desktop CI."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication = None
    QT_IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get("UCC_REQUIRE_QT") != "1", "Optional PySide6 not installed")
class DesktopQtSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError(f"Qt smoke tests REQUIRED but PySide6 UI import failed: {QT_IMPORT_ERROR}")
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

    def test_generate_action_requires_explicit_blender_selection(self):
        self.assertTrue(self.window.character.generate.isEnabled())
        exe = Path(self.tmp.name) / "selected-blender"
        exe.write_bytes(b"fake-test-executable-not-invoked")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                       return_value=(str(exe), "")):
                with patch.object(self.window, "_submit") as submit:
                    self.window.character.generate.click()
        submit.assert_called_once()
        args, kwargs = submit.call_args
        self.assertEqual(args[0], "generate_humanoid")
        self.assertTrue(callable(args[1]))
        self.assertFalse(kwargs["cancel"].is_set())

    def test_dialog_shows_saved_body_controls_not_unsaved_slider_values(self):
        self.controller.set_morph("height", .8)
        self.controller.set_morph("weight", .2)
        self.controller.save()
        self.window.refresh_project()
        exe = Path(self.tmp.name) / "test-selected-blender"
        exe.write_bytes(b"test fake executable not launched")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No) as dialog:
            with patch.object(self.window, "_submit") as submit:
                self.window.generate_humanoid()
        submit.assert_not_called()
        message = dialog.call_args.args[2]
        self.assertIn("height=0.800", message)
        self.assertIn("weight=0.200", message)
        self.assertIn("new Blender master", message)

    def test_dirty_metadata_blocks_generation_without_a_worker(self):
        self.controller.rename("Unsaved hero")
        with patch.object(self.window, "_error") as error:
            with patch.object(self.window, "_submit") as submit:
                self.window.generate_humanoid()
        error.assert_called_once()
        self.assertIn("Save all metadata", error.call_args.args[0])
        submit.assert_not_called()

    def test_busy_blender_generation_locks_all_project_edits(self):
        self.window._work_kind = "generate_humanoid"
        self.window._busy_changed(True)
        self.assertFalse(self.window.character.generate.isEnabled())
        self.assertFalse(self.window.new_action.isEnabled())
        self.assertFalse(self.window.open_action.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.window._busy_changed(False)
        self.assertTrue(self.window.character.generate.isEnabled())
        self.assertTrue(self.window.new_action.isEnabled())
        self.assertFalse(self.window.cancel_generation_action.isEnabled())

    def test_genuine_workflow_result_refreshes_project_but_does_not_certify(self):
        # Structural unit-test bytes; neither this test nor this output is MPFB proof.
        from ucc.core.master_versions import stage_unverified_master
        from ucc.jobs.humanoid_generation import HumanoidGeneration
        worker = Path(self.tmp.name) / "fake-worker-results"
        worker.mkdir()
        master = worker / "generated_human.blend"
        master.write_bytes(b"BLENDER" + b"unit-test-only" * 100)
        result = stage_unverified_master(
            self.controller.store, master, authorized_source_root=worker
        )
        outcome = HumanoidGeneration(
            result, {
                "created_vertex_count": 2000, "reopened_bone_count": 60,
                "macro_parameters_observed": {"height": .5, "muscle": .5, "weight": .5},
                "macro_evaluated_sha256": "a" * 64,
            },
            "unit-create", "unit-inspect",
        )
        self.window._work_kind = "generate_humanoid"
        self.window._job_success(outcome)
        self.assertEqual(self.window.controller.view().geometry_state, "generated_unverified")
        self.assertTrue(self.window.character.open_master.isEnabled())
        self.assertIn("MPFB evaluated shape", self.window.log.toPlainText())
        self.assertIn("height=0.500", self.window.log.toPlainText())
        self.assertIn("NOT live morph editing", self.window.log.toPlainText())
        self.assertIn("Master geometry has not passed", self.window.character.blockers.toPlainText())

    def test_tools_are_real_and_cannot_claim_geometry(self):
        self.assertIn("PNG", self.window.tools.pack.text())
        self.assertFalse(self.window.character.open_master.isEnabled())
        self.assertIn("does not live-edit", self.window.character.note.text())
        self.assertIn("local", self.window.tools.ai.text())


if __name__ == "__main__":
    unittest.main()
