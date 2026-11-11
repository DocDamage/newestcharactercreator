"""Offscreen Qt mesh preview tests; required on desktop GitHub CI, optional locally."""
from __future__ import annotations

import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    from PySide6.QtWidgets import QApplication
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

    def test_main_window_wires_real_preview_dock_without_fake_geometry(self):
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.assertEqual(window.tabs.count(), 3)
        self.assertFalse(window.mesh_dock.isVisible())
        self.assertTrue(window.mesh_action.isEnabled())
        window._work_kind = "mesh_preview"
        window._job_success(self.mesh())
        self.assertIs(window.mesh_viewer.canvas.mesh, window.mesh_viewer.canvas.mesh)
        self.assertIn("No rig/animation/export validation", window.log.toPlainText())
        self.assertIn("Preview", window.mesh_dock.windowTitle())
        window.close()


if __name__ == "__main__":
    unittest.main()
