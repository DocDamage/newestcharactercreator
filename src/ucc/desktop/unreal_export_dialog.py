"""Explicit installed editor, exact-source rights review and new-folder destination."""
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.unreal_contract import ENGINE_VERSION, UnrealExportRequest
from ucc.library.provenance import LicensePolicy


class UnrealExportDialog(QDialog):
    def __init__(self, review, parent=None):
        super().__init__(parent)
        self.review = review
        self.setWindowTitle('Export private Unreal character')
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        description = QLabel(
            'Create a new private Unreal 5.9 project from this saved character. '
            'Includes the static rig, facial morphs, UVs, saved skin material and character scene. '
            'Fresh native checks include the published project. Animation clips, shader/GPU rendering, '
            'PIE, player builds, visual quality and public distribution need separate review. '
            'Uses your installed Editor and existing Windows build tools; nothing is installed.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.table = QTableWidget(len(review.sources), 3)
        self.table.setHorizontalHeaderLabels(['Input', 'Content SHA-256', 'Authorize private Unreal use'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.checks = []
        for row, source in enumerate(review.sources):
            for column, value in ((0, source.label), (1, source.sha256)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(source.asset_id+'\n'+source.sha256)
                self.table.setItem(row, column, item)
            check = QCheckBox('Reviewed')
            check.setChecked(False)
            check.toggled.connect(self.refresh)
            self.table.setCellWidget(row, 2, check)
            self.checks.append(check)
        layout.addWidget(self.table)
        privacy = QLabel('Confirm rights for these exact inputs. NoAI stays enabled. '
                         'Original Blender and purchased sources remain private. Nothing is sent to a cloud service.')
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self.note = QLineEdit()
        self.note.setMaxLength(1024)
        self.note.setPlaceholderText('License or authorization reviewed for this private Unreal use')
        self.note.textChanged.connect(self.refresh)
        layout.addWidget(self.note)
        self.editor = QLineEdit()
        self.editor.setPlaceholderText('Select the installed Unreal '+ENGINE_VERSION+' Editor executable')
        self.editor.textChanged.connect(self.refresh)
        editor_row = QHBoxLayout()
        editor_row.addWidget(self.editor, 1)
        editor_browse = QPushButton('Choose installed Unrealâ€¦')
        editor_browse.clicked.connect(self.browse_editor)
        editor_row.addWidget(editor_browse)
        layout.addLayout(editor_row)
        self.destination = QLineEdit()
        self.destination.setPlaceholderText('New package folder (must not exist)')
        self.destination.textChanged.connect(self.refresh)
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination, 1)
        destination_browse = QPushButton('Choose parent folderâ€¦')
        destination_browse.clicked.connect(self.browse_destination)
        destination_row.addWidget(destination_browse)
        layout.addLayout(destination_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Verify and export')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.refresh()

    def browse_editor(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, 'Choose installed Unreal '+ENGINE_VERSION+' Editor', '', 'Executable (*.exe);;All files (*)')
        if selected:
            self.editor.setText(selected)

    def browse_destination(self):
        parent = QFileDialog.getExistingDirectory(self, 'Choose the parent of a new Unreal project')
        if parent:
            self.destination.setText(str(Path(parent)/'character-unreal'))

    def refresh(self, *_):
        if not hasattr(self, 'buttons'):
            return
        ready = (all(check.isChecked() for check in self.checks) and bool(self.note.text().strip())
                 and bool(self.editor.text().strip()) and bool(self.destination.text().strip()))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ready)
        self.status.setText(
            'Fresh Blender and Unreal checks include the published project. Existing folders are never replaced.'
            if ready else 'Review every input, record its authorization, select installed Unreal and choose a new destination.')

    def permissions(self) -> tuple[EngineInputPermission, ...]:
        permissions = []
        for source, check in zip(self.review.sources, self.checks):
            policy = LicensePolicy(
                provider='Explicit per-use project review', license_name=self.note.text().strip(),
                source_uri='ucc-project://'+self.review.project_id+'/'+source.asset_id+'/'+source.sha256,
                reviewed=check.isChecked(), no_ai=True, can_use_unreal=check.isChecked(),
                ai_input_allowed=False, redistribute_source_allowed=False)
            permissions.append(EngineInputPermission(source.asset_id, source.sha256, policy, source_only=False))
        for permission in permissions:
            permission.require_engine('unreal')
        return tuple(permissions)

    def request(self, executable_sha256: str, build_version_sha256: str, toolchain_sha256: str) -> UnrealExportRequest:
        return UnrealExportRequest(
            str(uuid4()), self.review.project_id, self.review.revision, self.review.project_sha256,
            executable_sha256, build_version_sha256, toolchain_sha256, tuple((source.asset_id, source.sha256) for source in self.review.sources),
            self.permissions())
