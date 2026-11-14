"""Real, deliberately limited editing tools: no simulated viewport or fabricated assets."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QFileDialog, QScrollArea,
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
    timeline_check_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
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
        from .face_controls import FaceControls
        self.face = FaceControls()
        layout.addWidget(self.face)
        from .hand_controls import HandControls
        self.hands=HandControls()
        layout.addWidget(self.hands)
        from .expression_controls import ExpressionControls
        self.expressions = ExpressionControls()
        layout.addWidget(self.expressions)

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

        self.test_timeline = QPushButton("Validate one-second Blender keyframe timeline...")
        self.test_timeline.setToolTip(
            "Creates an original temporary three-keyframe motion and measures "
            "actual evaluated skin deformation on five frames in Blender. "
            "Does not import, save, retarget or play an external animation clip."
        )
        self.test_timeline.setEnabled(False)
        self.test_timeline.clicked.connect(self.timeline_check_requested.emit)
        layout.addWidget(self.test_timeline)

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
        self.face.setEnabled(active)
        self.hands.setEnabled(active)
        self.expressions.setEnabled(active)
        if not active:
            self.face.apply.setEnabled(False)
        self.generate.setEnabled(active)
        self.apply_body.setEnabled(False)
        self.check_rig_pose.setEnabled(False)
        self.test_timeline.setEnabled(False)
        self.preview_master.setEnabled(False)
        self.open_master.setEnabled(False)
        if not active:
            self.heading.setText("Open or create a character project to begin")
            self.geometry.setText("Not generated")
            self.blockers.clear()

    def display(self, view: ProjectView) -> None:
        self.set_active(True)
        self.face.display(view)
        self.expressions.display(view)
        self.morph_box.setEnabled(view.part_count==0)
        self.morph_box.setToolTip('Restore the original hand before changing body settings.' if view.part_count else '')
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
        self.test_timeline.setEnabled(view.master_blend is not None)
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
    local_bvh_requested = Signal(str, str, str, str, bool)
    multi_bvh_requested = Signal(str, str, str, str, bool, str)
    calibrated_bvh_requested = Signal(str, str, str, str, bool, str)
    reviewed_bvh_requested = Signal(str, str, str, str, bool, str, str, str, bool)
    native_body_requested = Signal()
    native_animation_open_requested = Signal()
    native_renders_open_requested = Signal()
    native_playback_requested = Signal()
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer=QVBoxLayout(self)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        content=QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
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
        self.local_preview_review = QCheckBox(
            "I reviewed the actual license: this animation and its metadata may be used locally in Blender.\n"
            "Not UE-only. No AI/cloud or export."
        )
        layout.addWidget(self.local_preview_review)
        for field in (self.selected, self.provider, self.license, self.uri):
            field.textChanged.connect(lambda _text: self.local_preview_review.setChecked(False))
        row = QHBoxLayout()
        self.inspect = QPushButton("Inspect selected file")
        self.inspect.clicked.connect(lambda: self.inspect_requested.emit(self.selected.text()))
        self.index = QPushButton("Index as unreviewed")
        self.index.clicked.connect(lambda: self.index_requested.emit(
            self.selected.text(), self.asset_id.text(), self.provider.text(),
            self.license.text(), self.uri.text()))
        self.refresh = QPushButton("Refresh catalog")
        self.refresh.clicked.connect(self.refresh_requested.emit)
        self.test_local_bvh = QPushButton("Test selected BVH motion on saved MPFB rig...")
        self.test_local_bvh.setToolTip(
            "Reads one locally selected BVH, applies limited direct-name rotation "
            "deltas on an immutable character copy, and measures real skinned "
            "Blender frames. Not general retargeting or an engine-ready export."
        )
        self.test_local_bvh.clicked.connect(lambda: self.local_bvh_requested.emit(
            self.selected.text(), self.provider.text(), self.license.text(),
            self.uri.text(), self.local_preview_review.isChecked()
        ))
        for button in (self.inspect, self.index, self.refresh):
            row.addWidget(button)
        layout.addLayout(row)
        native=QGroupBox("FBX body preview (experimental)")
        native_layout=QVBoxLayout(native)
        native_row=QHBoxLayout()
        self.native_body_profile=QLineEdit()
        self.native_body_profile.setPlaceholderText("Automatic for supported humanoids; optional reviewed body map")
        self.native_body_profile.setToolTip("Automatic mapping recognizes one measured Hips-object skeleton family. Other families require a reviewed source/character-bound JSON map.")
        self.native_body_profile.textChanged.connect(lambda _text:self.local_preview_review.setChecked(False))
        choose_native=QPushButton("Advanced body map...")
        def choose_map():
            path,_=QFileDialog.getOpenFileName(self,"Choose a reviewed native body map","","Native body map (*.json)")
            if path:self.native_body_profile.setText(path)
        choose_native.clicked.connect(choose_map)
        native_row.addWidget(self.native_body_profile,1);native_row.addWidget(choose_native)
        native_layout.addLayout(native_row)
        self.native_include_hands=QCheckBox("Include hand and finger poses (experimental)")
        self.native_include_hands.setToolTip("Adds 38 measured hand roles for the supported automatic skeleton family. Every joint and skin frame must pass the same checks. Explicit maps define their own joints.")
        def mapping_scope(text):
            if text.strip():self.native_include_hands.setChecked(False)
            self.native_include_hands.setEnabled(not bool(text.strip()))
        self.native_body_profile.textChanged.connect(mapping_scope)
        self.native_include_hands.toggled.connect(lambda _checked:self.local_preview_review.setChecked(False))
        native_layout.addWidget(self.native_include_hands)
        self.test_native_body=QPushButton("Test selected FBX on saved character...")
        self.test_native_body.setToolTip("Measures every frame on private Blender copies, applies bounded joint smoothing for supported automatic maps, checks skin/root motion and renders sampled views. Originals are preserved; visual/engine quality is not approved.")
        self.test_native_body.clicked.connect(self.native_body_requested.emit)
        native_layout.addWidget(self.test_native_body)
        native_open=QHBoxLayout()
        self.open_native_animation=QPushButton("Open private animation in Blender")
        self.open_native_renders=QPushButton("Open sampled views")
        self.open_native_animation.setEnabled(False);self.open_native_renders.setEnabled(False)
        self.open_native_animation.clicked.connect(self.native_animation_open_requested.emit)
        self.open_native_renders.clicked.connect(self.native_renders_open_requested.emit)
        native_open.addWidget(self.open_native_animation);native_open.addWidget(self.open_native_renders)
        native_layout.addLayout(native_open)
        self.load_native_motion=QPushButton("Load verified motion in UCC...")
        self.load_native_motion.setToolTip("Reopens and checks the saved corrected animation, then loads every evaluated skin frame into an interactive 3D player. Precomputed playback; originals unchanged.")
        self.load_native_motion.setEnabled(False)
        self.load_native_motion.clicked.connect(self.native_playback_requested.emit)
        native_layout.addWidget(self.load_native_motion)
        layout.addWidget(native)
        layout.addWidget(self.test_local_bvh)

        self.source_axes = QComboBox()
        self.source_axes.addItem(
            "Choose BVH source up-axis for multi-bone rest check...", ""
        )
        self.source_axes.addItem(
            "BVH Y-up → Blender Z-up", "Y_UP_TO_Z_UP"
        )
        self.source_axes.addItem(
            "BVH Z-up (same axes as Blender)", "Z_UP_IDENTITY"
        )
        self.source_axes.setToolTip(
            "Source coordinate preset must be selected explicitly. "
            "Direction and hierarchy must match; bone roll remains uncalibrated."
        )
        layout.addWidget(self.source_axes)
        self.source_axes.currentIndexChanged.connect(
            lambda _index: self.local_preview_review.setChecked(False)
        )
        self.test_multi_bvh = QPushButton(
            "Test 2–4 bone BVH chain against saved MPFB rig..."
        )
        self.test_multi_bvh.setToolTip(
            "Requires every BVH joint to match an existing weighted MPFB bone, "
            "direct parent links and aligned rest directions. Source motion "
            "is only local Euler deltas; not full retargeting or engine import."
        )
        self.test_multi_bvh.clicked.connect(lambda: self.multi_bvh_requested.emit(
            self.selected.text(), self.provider.text(), self.license.text(),
            self.uri.text(), self.local_preview_review.isChecked(),
            self.source_axes.currentData(),
        ))
        layout.addWidget(self.test_multi_bvh)
        self.test_calibrated_bvh = QPushButton(
            "Calibrate BVH rest axes and test 2–4 bone motion..."
        )
        self.test_calibrated_bvh.setToolTip(
            "Requires an additional independent terminal End Site rest direction; "
            "uses actual MPFB rest-bone matrices and quaternion conversion. "
            "Fails closed when bone axes remain ambiguous. Not full retargeting."
        )
        self.test_calibrated_bvh.clicked.connect(
            lambda: self.calibrated_bvh_requested.emit(
                self.selected.text(), self.provider.text(), self.license.text(),
                self.uri.text(), self.local_preview_review.isChecked(),
                self.source_axes.currentData(),
            )
        )
        layout.addWidget(self.test_calibrated_bvh)
        self.manual_bone_pairs = QTextEdit()
        self.manual_bone_pairs.setPlaceholderText(
            "One source -> MPFB target per line, each parent before its children. Example: SourceNeck -> neck02"
        )
        self.manual_bone_pairs.setFixedHeight(85)
        self.manual_bone_pairs.setToolTip(
            "3–64 reviewed pairs; branching allowed, each parent before its children. "
            "Exact names, deform weights, parent links and "
            "real rest matrices are checked. No automatic alias suggestions."
        )
        self.manual_bone_pairs.textChanged.connect(
            lambda: self.local_preview_review.setChecked(False)
        )
        layout.addWidget(self.manual_bone_pairs)
        self.source_rest_profile = QLineEdit()
        self.source_rest_profile.setPlaceholderText("Optional source rest-frame JSON (audit option below)")
        self.source_rest_profile.setToolTip(
            "Must match the selected BVH SHA-256, axes and exact source joints. "
            "Validates bone rest metadata; does not certify source roll or change BVH channel axes."
        )
        self.source_rest_profile.textChanged.connect(
            lambda _text: self.local_preview_review.setChecked(False)
        )
        self.choose_rest_profile = QPushButton("Choose rest frames...")
        self.choose_rest_profile.clicked.connect(self.choose_source_rest_profile)
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.source_rest_profile, 1)
        profile_row.addWidget(self.choose_rest_profile)
        layout.addLayout(profile_row)
        self.audit_and_render = QCheckBox("Audit channel-to-bone conversion and render private views")
        self.audit_and_render.setToolTip(
            "Requires the SHA-bound descriptor. Audits the existing XYZ first-frame delta basis change "
            "and creates 15 private CPU clay PNGs across five frames. Adds render time; no visual approval."
        )
        self.audit_and_render.toggled.connect(lambda _checked: self.local_preview_review.setChecked(False))
        layout.addWidget(self.audit_and_render)
        self.test_reviewed_bvh = QPushButton(
            "Review explicit 3–64 bone BVH hierarchy across full timeline..."
        )
        self.test_reviewed_bvh.setToolTip(
            "Measures every skinned frame and saves an animated private .blend "
            "copy to open in Blender. No engine export or visual quality approval."
        )
        self.test_reviewed_bvh.clicked.connect(lambda: self.reviewed_bvh_requested.emit(
            self.selected.text(), self.provider.text(), self.license.text(),
            self.uri.text(), self.local_preview_review.isChecked(),
            self.source_axes.currentData(), self.manual_bone_pairs.toPlainText(),
            self.source_rest_profile.text(),
            self.audit_and_render.isChecked(),
        ))
        layout.addWidget(self.test_reviewed_bvh)
        self.catalog = QTableWidget(0, 4)
        self.catalog.setHorizontalHeaderLabels(["Asset ID", "Format", "Declared clips", "Status"])
        self.catalog.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.catalog.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.catalog, 1)

    def choose_source_rest_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose SHA-bound source rest metadata", "", "Source rest frames (*.json)"
        )
        if path:
            self.source_rest_profile.setText(path)

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
