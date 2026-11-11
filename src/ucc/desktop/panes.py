"""Real, deliberately limited editing tools: no simulated viewport or fabricated assets."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QFileDialog,
)

from ucc.core.anatomy import slot_catalog
from ucc.core.models import MORPH_LIMITS
from .controller import ProjectView


class CharacterPane(QWidget):
    name_requested = Signal(str)
    morph_requested = Signal(str, float)
    open_master_requested = Signal()
    generate_human_requested = Signal()
    preview_master_requested = Signal()
    refit_human_requested = Signal()
    pose_check_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.heading = QLabel("Open or create a character project to begin")
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.heading)
        mode_line = QHBoxLayout()
        mode_line.addWidget(QLabel("Editor mode"))
        self.mode = QComboBox()
        self.mode.addItems(["Create", "Advanced"])
        mode_line.addWidget(self.mode)
        mode_line.addStretch()
        layout.addLayout(mode_line)

        self.identity = QGroupBox("Character metadata")
        identity_form = QFormLayout(self.identity)
        self.name = QLineEdit()
        self.name.setMaxLength(200)
        self.name.setPlaceholderText("Character name")
        self.name.editingFinished.connect(lambda: self.name_requested.emit(self.name.text()))
        identity_form.addRow("Name", self.name)
        self.revision = QLabel("—")
        identity_form.addRow("Saved revision", self.revision)
        self.geometry = QLabel("Not generated")
        identity_form.addRow("3D master", self.geometry)
        layout.addWidget(self.identity)

        self.morph_box = QGroupBox("Body phenotype controls (normalized MPFB macros)")
        morph_form = QFormLayout(self.morph_box)
        self.sliders: dict[str, QSlider] = {}
        self.morph_values: dict[str, QLabel] = {}
        for key in MORPH_LIMITS:
            line = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1000)
            slider.setSingleStep(10)
            slider.setObjectName(f"morph_{key}")
            output = QLabel("0.500")
            output.setMinimumWidth(42)
            slider.valueChanged.connect(lambda value, o=output: o.setText(f"{value / 1000:.3f}"))
            slider.sliderReleased.connect(lambda k=key, s=slider: self.morph_requested.emit(k, s.value() / 1000))
            line.addWidget(slider, 1)
            line.addWidget(output)
            morph_form.addRow(key.title(), line)
            self.sliders[key] = slider
            self.morph_values[key] = output
        layout.addWidget(self.morph_box)
        self.note = QLabel(
            "Save Height/Muscle/Weight first. Generate a new master, or apply "
            "saved values to the existing master through a reversible MPFB refit. "
            "No live updates; values are normalized, not meters or kilograms."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.advanced = QGroupBox("Anatomy sockets and export status")
        adv_layout = QVBoxLayout(self.advanced)
        self.slot_table = QTableWidget(0, 3)
        self.slot_table.setHorizontalHeaderLabels(["Slot", "Socket", "Permitted part types"])
        self.slot_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.slot_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        slots = slot_catalog()
        self.slot_table.setRowCount(len(slots))
        for row, item in enumerate(slots):
            for col, text in enumerate((item.name, item.socket, ", ".join(sorted(item.allowed_kinds)))):
                self.slot_table.setItem(row, col, QTableWidgetItem(text))
        self.slot_table.horizontalHeader().setStretchLastSection(True)
        adv_layout.addWidget(self.slot_table)
        self.blockers = QTextEdit()
        self.blockers.setReadOnly(True)
        self.blockers.setMaximumHeight(110)
        adv_layout.addWidget(self.blockers)
        layout.addWidget(self.advanced, 1)
        self.mode.currentIndexChanged.connect(lambda index: self.advanced.setVisible(index == 1))
        self.advanced.hide()

        generation = QGroupBox("MPFB humanoid generation (requires installed Blender + MPFB)")
        generate_layout = QVBoxLayout(generation)
        self.generate = QPushButton("Generate humanoid using saved body controls...")
        self.generate.setToolTip(
            "Runs MPFB's real macro-target system using saved Height, Muscle and Weight, "
            "creates a new Blender master, independently reopens and validates geometry."
        )
        self.generate.clicked.connect(self.generate_human_requested.emit)
        self.generate.setEnabled(False)
        generate_layout.addWidget(self.generate)
        generation_note = QLabel(
            "Save slider changes first. Generating again creates a new immutable master "
            "and preserves older revisions; previously edited mesh parts are not carried "
            "forward. Animation skinning and game-engine export remain unverified."
        )
        generation_note.setWordWrap(True)
        generate_layout.addWidget(generation_note)
        layout.addWidget(generation)

        self.apply_body = QPushButton("Apply saved body controls to existing master...")
        self.apply_body.setToolTip(
            "Uses real MPFB targets and refits the existing rig on a staged copy. "
            "Preserves the original master and independently checks bone weights."
        )
        self.apply_body.setEnabled(False)
        self.apply_body.clicked.connect(self.refit_human_requested.emit)
        layout.addWidget(self.apply_body)

        self.check_rig_pose = QPushButton("Test saved rig deformation in Blender...")
        self.check_rig_pose.setToolTip(
            "Uses a temporary Blender pose to measure real skinned vertex movement; "
            "restores pose, never saves the .blend, and does not certify animations."
        )
        self.check_rig_pose.setEnabled(False)
        self.check_rig_pose.clicked.connect(self.pose_check_requested.emit)
        layout.addWidget(self.check_rig_pose)

        self.preview_master = QPushButton("Preview saved master in UCC...")
        self.preview_master.setToolTip(
            "Uses your installed Blender to export a temporary untextured static GLB "
            "from the saved .blend; shows actual triangles with orbit/pan/zoom. "
            "No skinning, motion or engine certification."
        )
        self.preview_master.clicked.connect(self.preview_master_requested.emit)
        self.preview_master.setEnabled(False)
        layout.addWidget(self.preview_master)

        self.open_master = QPushButton("Open saved master in Blender...")
        self.open_master.setToolTip("Launches your installed Blender with the existing project file; never generates fake geometry")
        self.open_master.clicked.connect(self.open_master_requested.emit)
        self.open_master.setEnabled(False)
        layout.addWidget(self.open_master)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.identity.setEnabled(active)
        self.morph_box.setEnabled(active)
        self.generate.setEnabled(active)
        self.apply_body.setEnabled(False)
        self.check_rig_pose.setEnabled(False)
        self.preview_master.setEnabled(False)
        self.open_master.setEnabled(False)
        if not active:
            self.heading.setText("Open or create a character project to begin")
            self.geometry.setText("Not generated")
            self.blockers.clear()

    def display(self, view: ProjectView) -> None:
        self.set_active(True)
        self.heading.setText(view.name + ("  •  unsaved edits" if view.dirty else ""))
        if self.name.text() != view.name:
            self.name.blockSignals(True)
            self.name.setText(view.name)
            self.name.blockSignals(False)
        self.revision.setText(f"{view.revision} ({'unsaved' if view.dirty else 'on disk'})")
        self.geometry.setText(view.geometry_state.replace("_", " ").title())
        self.open_master.setEnabled(view.master_blend is not None)
        self.preview_master.setEnabled(view.master_blend is not None)
        self.check_rig_pose.setEnabled(view.master_blend is not None)
        self.apply_body.setEnabled(view.master_blend is not None and
                                   view.geometry_state != "not_generated")
        for key, value in view.morphs:
            if key in self.sliders:
                slider = self.sliders[key]
                slider.blockSignals(True)
                slider.setValue(round(value * 1000))
                slider.blockSignals(False)
                self.morph_values[key].setText(f"{value:.3f}")
        self.blockers.setPlainText(
            "EXPORT NOT CERTIFIED\n" + "\n".join(f"• {x}" for x in view.blockers)
            + "\nReal Godot/Unity/Unreal import tests are still required."
        )


class AnimationPane(QWidget):
    inspect_requested = Signal(str)
    index_requested = Signal(str, str, str, str, str)
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("Local animation catalog • indexing is not retargeting or a license grant")
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        self.selected = QLineEdit()
        self.selected.setReadOnly(True)
        choose = QPushButton("Select file...")
        choose.clicked.connect(self.choose_animation)
        source_row = QHBoxLayout()
        source_row.addWidget(self.selected, 1)
        source_row.addWidget(choose)
        form.addRow("Source file", source_row)
        self.asset_id = QLineEdit()
        self.asset_id.setPlaceholderText("A unique private asset ID")
        self.provider = QLineEdit()
        self.provider.setPlaceholderText("e.g. Fab, purchased directly, original")
        self.license = QLineEdit("unreviewed")
        self.uri = QLineEdit()
        self.uri.setPlaceholderText("Actual source or license listing URL")
        for title, field in (("Asset ID", self.asset_id), ("Provider", self.provider),
                             ("License", self.license), ("Source URL", self.uri)):
            form.addRow(title, field)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.inspect = QPushButton("Inspect selected file")
        self.inspect.clicked.connect(lambda: self.inspect_requested.emit(self.selected.text()))
        self.index = QPushButton("Index as unreviewed")
        self.index.clicked.connect(lambda: self.index_requested.emit(
            self.selected.text(), self.asset_id.text(), self.provider.text(),
            self.license.text(), self.uri.text()))
        self.refresh = QPushButton("Refresh catalog")
        self.refresh.clicked.connect(self.refresh_requested.emit)
        for button in (self.inspect, self.index, self.refresh):
            row.addWidget(button)
        layout.addLayout(row)
        self.catalog = QTableWidget(0, 4)
        self.catalog.setHorizontalHeaderLabels(["Asset ID", "Format", "Declared clips", "Status"])
        self.catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.catalog.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.catalog, 1)

    def choose_animation(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select your animation source", "",
            "Animation sources (*.bvh *.glb *.gltf *.fbx *.uasset)")
        if path:
            self.selected.setText(path)
            if not self.asset_id.text():
                self.asset_id.setText(Path(path).stem[:100])

    def display_catalog(self, items: list[dict]) -> None:
        self.catalog.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (item["asset_id"], item["format"], str(len(item["clips"])), item["status"])
            for col, value in enumerate(values):
                self.catalog.setItem(row, col, QTableWidgetItem(value))


class ToolsPane(QWidget):
    glb_requested = Signal(str)
    ai_requested = Signal()
    atlas_requested = Signal(str, str, str, int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.glb = QPushButton("Inspect GLB structure...")
        self.glb.clicked.connect(self.select_glb)
        layout.addWidget(self.glb)
        self.ai = QPushButton("Check local ComfyUI and Stable Diffusion WebUI (read-only)")
        self.ai.clicked.connect(self.ai_requested.emit)
        layout.addWidget(self.ai)

        atlas = QGroupBox("Build sprite atlas from existing PNG frames")
        form = QFormLayout(atlas)
        self.frames = QLineEdit()
        self.frames.setReadOnly(True)
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        for title, field in (("PNG source folder", self.frames), ("Output folder", self.output)):
            button = QPushButton("Browse...")
            button.clicked.connect(lambda _=False, target=field: self.select_folder(target))
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(button)
            form.addRow(title, row)
        self.clip = QLineEdit("idle")
        form.addRow("Clip ID", self.clip)
        self.frames_count = QSpinBox()
        self.frames_count.setRange(1, 256)
        self.frames_count.setValue(8)
        form.addRow("Frames / direction", self.frames_count)
        self.directions = QComboBox()
        self.directions.addItems(["4", "8", "16"])
        self.directions.setCurrentText("8")
        form.addRow("Directions", self.directions)
        self.resolution = QComboBox()
        self.resolution.addItems(["32", "64", "128", "256", "512"])
        self.resolution.setCurrentText("128")
        form.addRow("Frame size (square)", self.resolution)
        self.pack = QPushButton("Validate and pack real PNG frames")
        self.pack.clicked.connect(lambda: self.atlas_requested.emit(
            self.frames.text(), self.output.text(), self.clip.text(),
            self.frames_count.value(), int(self.directions.currentText()),
            int(self.resolution.currentText()), 12))
        form.addRow(self.pack)
        layout.addWidget(atlas)
        self.info = QLabel("No fake assets: source PNGs must exist and match the render plan. "
                           "A GLB structure check does not certify engine import.")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        layout.addStretch()

    def select_glb(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Inspect GLB", "", "Binary glTF (*.glb)")
        if path:
            self.glb_requested.emit(path)

    def select_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select local folder")
        if folder:
            target.setText(folder)
