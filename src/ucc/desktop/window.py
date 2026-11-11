"""Standalone UCC project and asset workstation. No pretend mesh/viewport functionality."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QLabel, QMainWindow, QMessageBox,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ucc.ai.probe import probe_comfyui, probe_webui
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.metadata import inspect_animation_file
from ucc.core.errors import UCCError, ValidationError
from ucc.export.inspect_glb import inspect_glb
from ucc.library.provenance import LicensePolicy
from ucc.sprites.atlas import pack_frames
from ucc.sprites.plan import CameraProfile, build_plan

from .background import BackgroundJobs
from .controller import DesktopController, ProjectView
from .panes import AnimationPane, CharacterPane, ToolsPane


class MainWindow(QMainWindow):
    """Actual metadata editor, asset inspector, atlas packer, and local read-only probes."""

    def __init__(self, controller: DesktopController | None = None) -> None:
        super().__init__()
        self.controller = controller if controller is not None else DesktopController()
        self.setWindowTitle("Universal Character Creator — development desktop")
        self.resize(1030, 740)
        self.tabs = QTabWidget()
        self.character = CharacterPane()
        self.animations = AnimationPane()
        self.tools = ToolsPane()
        self.tabs.addTab(self.character, "Character")
        self.tabs.addTab(self.animations, "Animation library")
        self.tabs.addTab(self.tools, "Tools")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        self.log.setPlainText(
            "Ready. The application edits project metadata and existing files. "
            "Actual humanoid creation and 3D viewport remain contingent on a real Blender/MPFB smoke test."
        )
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(QLabel("Results and diagnostics (local only)"))
        layout.addWidget(self.log)
        self.setCentralWidget(container)
        self._make_menu()
        self.jobs = BackgroundJobs(self._job_success, self._job_error, self._busy_changed)
        self._work_kind = ""
        self._connect()
        self.statusBar().showMessage("No character project opened")
        if self.controller.has_project:
            self.refresh_project()

    def _make_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        self.new_action = self._action(menu, "&New character...", "Ctrl+N", self.new_project)
        self.open_action = self._action(menu, "&Open character...", "Ctrl+O", self.open_project)
        self.save_action = self._action(menu, "&Save metadata", "Ctrl+S", self.save_project)
        self.save_action.setEnabled(False)
        menu.addSeparator()
        self.quit_action = self._action(menu, "E&xit", "Ctrl+Q", self.close)
        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = self._action(edit, "&Undo", "Ctrl+Z", self.undo)
        self.redo_action = self._action(edit, "&Redo", "Ctrl+Shift+Z", self.redo)
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        help_menu = self.menuBar().addMenu("&Help")
        self.about_action = self._action(help_menu, "Capabilities and limitations", "", self.about)

    @staticmethod
    def _action(menu, text: str, shortcut: str, callback: Callable) -> QAction:
        action = QAction(text, menu)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _connect(self) -> None:
        self.character.name_requested.connect(self.rename)
        self.character.morph_requested.connect(self.set_morph)
        self.character.open_master_requested.connect(self.open_master_in_blender)
        self.animations.inspect_requested.connect(self.inspect_animation)
        self.animations.index_requested.connect(self.index_animation)
        self.animations.refresh_requested.connect(self.refresh_catalog)
        self.tools.glb_requested.connect(self.inspect_glb_file)
        self.tools.ai_requested.connect(self.probe_ai)
        self.tools.atlas_requested.connect(self.pack_atlas)

    def _error(self, msg: str) -> None:
        self.log.setPlainText(msg)
        self.statusBar().showMessage("Operation failed")
        QMessageBox.warning(self, "UCC operation blocked", msg)

    def _apply(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
            if self.controller.has_project:
                self.refresh_project()
        except (UCCError, OSError, ValueError, TypeError, KeyError) as exc:
            self._error(f"{type(exc).__name__}: {exc}")

    def refresh_project(self) -> None:
        state = self.controller.view()
        self.character.display(state)
        self.save_action.setEnabled(state.dirty)
        self.undo_action.setEnabled(state.can_undo)
        self.redo_action.setEnabled(state.can_redo)
        self.statusBar().showMessage(
            f"{state.name} — revision {state.revision} — "
            + ("unsaved metadata" if state.dirty else "saved")
            + f" — {state.geometry_state}"
        )
        self.setWindowTitle("Universal Character Creator — " + state.name + (" *" if state.dirty else ""))

    def _confirm_discard(self) -> bool:
        if not self.controller.dirty:
            return True
        response = QMessageBox.question(
            self, "Unsaved metadata changes", "Discard unsaved metadata edits?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        name, ok = QInputDialog.getText(self, "New character", "Character name")
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(self, "Select an empty project folder")
        if folder:
            self._apply(lambda: self.controller.create(folder, name))

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        folder = QFileDialog.getExistingDirectory(self, "Open an existing UCC project directory")
        if folder:
            self._apply(lambda: self.controller.open(folder))

    def save_project(self) -> None:
        self._apply(self.controller.save)

    def rename(self, value: str) -> None:
        if self.controller.has_project and value != self.controller.require_project().name:
            self._apply(lambda: self.controller.rename(value))

    def set_morph(self, key: str, value: float) -> None:
        if self.controller.has_project:
            self._apply(lambda: self.controller.set_morph(key, value))

    def undo(self) -> None:
        self._apply(self.controller.undo)

    def redo(self) -> None:
        self._apply(self.controller.redo)

    def open_master_in_blender(self) -> None:
        def execute() -> None:
            target = self.controller.master_path()
            message = (
                "This opens an existing saved .blend in the installed Blender GUI. "
                "Unsaved metadata controls have NOT been applied to its geometry. Continue?"
            )
            if QMessageBox.question(self, "Open Blender", message) != QMessageBox.StandardButton.Yes:
                return
            executable, _ = QFileDialog.getOpenFileName(self, "Select installed Blender executable")
            if not executable:
                return
            exe = Path(executable)
            if not exe.is_file() or exe.is_symlink():
                raise ValidationError("Choose an existing non-symlink Blender executable")
            # No shell invocation and disable auto-execution in untrusted .blend projects.
            subprocess.Popen([str(exe), "--disable-autoexec", str(target)], shell=False)
            self.statusBar().showMessage("Opening saved master in external Blender")
        self._apply(execute)

    @staticmethod
    def _catalog_path() -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        if not base:
            raise ValidationError("No local application data folder available")
        folder = Path(base)
        if folder.is_symlink():
            raise ValidationError("Application data folder cannot be a symlink")
        return folder / "animation_library.db"

    def _submit(self, kind: str, operation: Callable[[], object]) -> None:
        if self.jobs.busy:
            self._error("Another local task is still running")
            return
        self._work_kind = kind
        if not self.jobs.submit(operation):
            self._error("Could not start task")

    def _busy_changed(self, busy: bool) -> None:
        self.animations.setEnabled(not busy)
        self.tools.setEnabled(not busy)
        self.statusBar().showMessage("Working on local files..." if busy else "Local task finished")

    def _job_success(self, result: object) -> None:
        if self._work_kind == "catalog":
            assert isinstance(result, list)
            self.animations.display_catalog(result)
            self.log.setPlainText(f"Catalog contains {len(result)} source files. Metadata only; no retargeting verified.")
        else:
            self.log.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:100000])
        self.statusBar().showMessage("Local operation completed; review results above")

    def _job_error(self, error: str) -> None:
        self._error(error)

    def inspect_animation(self, file: str) -> None:
        if not file:
            self._error("Select an animation source file first")
            return
        self._submit("animation", lambda: inspect_animation_file(Path(file)).to_dict())

    def index_animation(self, file: str, asset_id: str, provider: str,
                        license_name: str, uri: str) -> None:
        if not file or not asset_id.strip() or not provider.strip() or not uri.strip():
            self._error("Choose a source and enter an asset ID, provider and actual source URI")
            return
        def job() -> dict:
            # Always unreviewed; GUI cannot grant cross-engine/NoAI permissions.
            policy = LicensePolicy(provider, license_name, uri, reviewed=False)
            with AnimationCatalog(self._catalog_path()) as catalog:
                return catalog.index_file(asset_id, Path(file), policy).to_dict()
        self._submit("index", job)

    def refresh_catalog(self) -> None:
        def job() -> list[dict]:
            with AnimationCatalog(self._catalog_path()) as catalog:
                return [item.to_dict() for item in catalog.list_sources()]
        self._submit("catalog", job)

    def inspect_glb_file(self, file: str) -> None:
        self._submit("glb", lambda: inspect_glb(Path(file)).to_dict())

    def probe_ai(self) -> None:
        self._submit("ai", lambda: [probe_comfyui().to_dict(), probe_webui().to_dict()])

    def pack_atlas(self, frames: str, output: str, clip: str, count: int,
                   directions: int, resolution: int, fps: int) -> None:
        if not frames or not output or not clip.strip():
            self._error("Choose existing PNG frames, an output folder and a clip ID")
            return
        def job() -> dict:
            plan = build_plan({clip: count}, CameraProfile(directions=directions),
                              width=resolution, height=resolution, fps=fps)
            result = pack_frames(plan, Path(frames), Path(output))
            return {"status": "PNG_ATLAS_CREATED", "frames": result.frame_count,
                    "sheets": list(result.sheet_files), "manifest": result.manifest,
                    "engine_import_verified": False}
        self._submit("atlas", job)

    def about(self) -> None:
        QMessageBox.information(self, "Development desktop",
            "Functional: project editing, atomic metadata saves, undo/redo, private animation "
            "catalog, local AI API probes, GLB structural inspection and PNG atlas generation.\n\n"
            "Not yet delivered: embedded 3D viewport, MPFB mesh deformation, rig retargeting "
            "and real Godot/Unity/Unreal import verification.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.jobs.busy:
            self._error("A local task is in progress. Finish the task before closing to preserve output consistency.")
            event.ignore()
            return
        if not self._confirm_discard():
            event.ignore()
            return
        event.accept()
