"""Offscreen Qt mesh preview tests; required on desktop GitHub CI, optional locally."""
from __future__ import annotations

import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    from PySide6.QtWidgets import QApplication, QFileDialog
    from ucc.desktop.controller import DesktopController
    from ucc.core.master_versions import stage_unverified_master
    from ucc.jobs.master_preview import MasterPreview
    from ucc.desktop.mesh_viewer import MeshViewer
    from ucc.desktop.window import MainWindow
    from ucc.preview.glb_mesh import PreviewMesh
except ImportError as exc:
    QApplication = None
    IMPORT_ERROR = str(exc)


@unittest.skipIf(QApplication is None and os.environ.get("UCC_REQUIRE_QT") != "1", "Optional PySide6 unavailable")
class PreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError("Qt preview CI requires real PySide6: " + IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(["ucc-preview-tests"])

    @staticmethod
    def mesh():
        return PreviewMesh(
            triangles=(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)),),
            bounds=((0.,0.,0.),(1.,1.,0.)), source_face_count=1,
            skin_count=0, animation_count=0, warnings=("Unit-test triangle",),
        )

    def test_viewer_draws_real_qt_image_and_shows_static_warning(self):
        viewer = MeshViewer()
        self.addCleanup(viewer.deleteLater)
        viewer.resize(440, 480)
        viewer.show_model(self.mesh())
        viewer.show()
        self.app.processEvents()
        image = viewer.canvas.grab().toImage()
        self.assertFalse(image.isNull())
        self.assertGreater(image.width(), 0)
        self.assertIn("1", viewer.status.text())
        self.assertIn("static", viewer.note.text().lower())

    def test_orbit_reset_restores_defaults(self):
        viewer = MeshViewer()
        self.addCleanup(viewer.deleteLater)
        viewer.show_model(self.mesh())
        viewer.canvas.yaw = 12
        viewer.canvas.pitch = 1.0
        viewer.canvas.zoom = 3
        viewer.reset.click()
        self.assertAlmostEqual(viewer.canvas.yaw, math.radians(-30))
        self.assertEqual(viewer.canvas.zoom, 1.0)

    def test_saved_master_preview_button_uses_explicit_blender_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = DesktopController()
            controller.create(root / "character", "Preview Test")
            source = root / "mock-only-staging"
            source.mkdir()
            blend = source / "fake.blend"
            blend.write_bytes(b"BLENDER" + b"unit-test-only" * 90)
            stage_unverified_master(controller.store, blend, authorized_source_root=source)
            controller.open(root / "character")
            window = MainWindow(controller)
            self.addCleanup(window.deleteLater)
            self.assertTrue(window.character.preview_master.isEnabled())
            self.assertTrue(window.preview_master_action.isEnabled())
            exe = root / "fake-test-blender"
            exe.write_bytes(b"not executed")
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(exe), "")):
                with patch.object(window, "_submit") as submit:
                    window.character.preview_master.click()
            submit.assert_called_once()
            args, kwargs = submit.call_args
            self.assertEqual(args[0], "saved_master_preview")
            self.assertTrue(callable(args[1]))
            self.assertFalse(kwargs["cancel"].is_set())
            snapshot = controller.require_project()
            result = MasterPreview(
                self.mesh(), snapshot.project_id, snapshot.revision,
                snapshot.master_blend, "1" * 64, "2" * 64, 19158, "5.3.0",
            )
            window._work_kind = "saved_master_preview"
            window._job_success(result)
            self.assertIsNotNone(window.mesh_viewer.canvas.mesh)
            self.assertIn("STATIC PREVIEW", window.log.toPlainText())
            self.assertIn("No animations", window.log.toPlainText())
            window.close()

    def test_new_project_clears_old_preview_geometry(self):
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        window._work_kind = "mesh_preview"
        window._job_success(self.mesh())
        self.assertIsNotNone(window.mesh_viewer.canvas.mesh)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = DesktopController()
            controller.create(root / "character", "Other Character")
            with patch.object(QFileDialog, "getExistingDirectory",
                              return_value=str(root / "character")):
                window.open_project()
        self.assertIsNone(window.mesh_viewer.canvas.mesh)
        self.assertTrue(window.mesh_dock.isHidden())
        self.assertFalse(window.preview_master_action.isEnabled())
        window.close()

    def test_main_window_wires_real_preview_dock_without_fake_geometry(self):
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.assertEqual(window.tabs.count(), 3)
        self.assertFalse(window.mesh_dock.isVisible())
        self.assertTrue(window.mesh_action.isEnabled())
        window._work_kind = "mesh_preview"
        window._job_success(self.mesh())
        self.assertIsNotNone(window.mesh_viewer.canvas.mesh)
        self.assertEqual(window.mesh_viewer.canvas.mesh.source_face_count, 1)
        self.assertIn("No rig/animation/export validation", window.log.toPlainText())
        self.assertIn("Preview", window.mesh_dock.windowTitle())
        window.close()


if __name__ == "__main__":
    unittest.main()
