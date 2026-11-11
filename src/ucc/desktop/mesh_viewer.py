"""Interactive CPU-drawn GLB triangle preview for *existing* local geometry.

No OpenGL requirement, no material/shader execution, no animation, no skinning,
no editing or engine-export claims. A capped triangle subset is drawn.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ucc.preview.glb_mesh import PreviewMesh, Vec3


class MeshCanvas(QWidget):
    """Orbit, pan and zoom a static read-only GLB surface preview."""

    def __init__(self) -> None:
        super().__init__()
        self.mesh: PreviewMesh | None = None
        self.yaw = math.radians(-30)
        self.pitch = math.radians(15)
        self.zoom = 1.0
        self.pan = (0.0, 0.0)
        self._pointer: QPointF | None = None
        self.setMinimumSize(300, 280)
        self.setToolTip("Drag: orbit | Right-drag: pan | Mouse wheel: zoom | CPU-rendered static triangles")

    def set_mesh(self, mesh: PreviewMesh) -> None:
        self.mesh = mesh
        self.reset_view()

    def reset_view(self) -> None:
        self.yaw = math.radians(-30)
        self.pitch = math.radians(15)
        self.zoom = 1.0
        self.pan = (0.0, 0.0)
        self.update()

    def _project(self, point: Vec3, center: Vec3, radius: float) -> tuple[QPointF, float, Vec3] | None:
        x, y, z = (point[i]-center[i] for i in range(3))
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        xp = cy*x + sy*z
        zp = -sy*x + cy*z
        yp = cp*y-sp*zp
        zpp = sp*y+cp*zp
        depth = radius*3.5*self.zoom - zpp
        if depth <= max(.00001, radius*.05):
            return None
        focal = min(self.width(), self.height()) * 1.65 * radius
        factor = focal / depth
        screen = QPointF(self.width()*.5 + self.pan[0] + xp*factor,
                         self.height()*.5 + self.pan[1] - yp*factor)
        return screen, depth, (xp, yp, zpp)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#141924"))
        if self.mesh is None:
            painter.setPen(QColor("#c5ccd9"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Open a local GLB file to inspect its static 3D geometry")
            painter.end()
            return
        lower, upper = self.mesh.bounds
        center = tuple((lower[i]+upper[i])*.5 for i in range(3))
        radius = max(.001, math.sqrt(sum(((upper[i]-lower[i])*.5)**2 for i in range(3))))
        visible = []
        for face in self.mesh.triangles:
            projected = [self._project(p, center, radius) for p in face]
            if any(x is None for x in projected):
                continue
            points = [x[0] for x in projected]
            coords = [x[2] for x in projected]
            ax, ay, az = (coords[1][i]-coords[0][i] for i in range(3))
            bx, by, bz = (coords[2][i]-coords[0][i] for i in range(3))
            nx, ny, nz = ay*bz-az*by, az*bx-ax*bz, ax*by-ay*bx
            length = math.sqrt(nx*nx+ny*ny+nz*nz)
            intensity = (abs((nx*.5+ny*.7+nz*.6)/length) if length > 1e-8 else .15)
            visible.append((sum(x[1] for x in projected)/3, points, intensity))
        # Far-to-near painter's ordering; this is a non-physical flat-shaded diagnostic.
        visible.sort(key=lambda x: x[0], reverse=True)
        for _, points, light in visible:
            shade = round(60 + 95*light)
            painter.setBrush(QBrush(QColor(shade, min(255,shade+18), min(255,shade+35), 210)))
            painter.setPen(QPen(QColor(39, 50, 73, 165), .6))
            painter.drawPolygon(QPolygonF(points))
        painter.setPen(QColor("#e0e7f2"))
        painter.drawText(12, 20, f"GLB triangles: {self.mesh.sample_count}/{self.mesh.source_face_count} (sampled)")
        painter.drawText(12, 38, "STATIC / UNVERIFIED • no skinning, animation or engine validation")
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._pointer = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pointer is None:
            return
        current = event.position()
        dx, dy = current.x()-self._pointer.x(), current.y()-self._pointer.y()
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.yaw += dx*.008
            self.pitch = min(1.45, max(-1.45, self.pitch+dy*.008))
            self.update()
        elif event.buttons() & Qt.MouseButton.RightButton:
            self.pan = (self.pan[0]+dx, self.pan[1]+dy)
            self.update()
        self._pointer = current

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._pointer = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta:
            self.zoom = min(8., max(.25, self.zoom*(.89 if delta>0 else 1.12)))
            self.update()


class MeshViewer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.status = QLabel("Select a GLB from View → Preview GLB model...")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = MeshCanvas()
        layout.addWidget(self.canvas, 1)
        self.reset = QPushButton("Reset orbit / pan / zoom")
        self.reset.clicked.connect(self.canvas.reset_view)
        layout.addWidget(self.reset)
        self.note = QLabel("Mouse: left drag orbit, right drag pan, wheel zoom. Read-only static triangles.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def show_model(self, model: PreviewMesh) -> None:
        self.canvas.set_mesh(model)
        self.status.setText(f"Parsed {model.source_face_count:,} source triangles; previewing "
                            f"{model.sample_count:,}. Declared skins: {model.skin_count}; "
                            f"animations: {model.animation_count}. "
                            + " | ".join(model.warnings))
