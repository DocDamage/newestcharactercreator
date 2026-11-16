"""Explicit private destination and per-source, per-use engine permission."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QCheckBox,
    QTableWidget,QTableWidgetItem,QHeaderView,QDialogButtonBox,QFileDialog)
from ucc.library.provenance import LicensePolicy
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.static_godot_contract import StaticGodotRequest


class GodotExportDialog(QDialog):
    def __init__(self,review,parent=None):
        super().__init__(parent);self.review=review;self.setWindowTitle('Export private Godot character');self.resize(1000,560)
        layout=QVBoxLayout(self)
        text=QLabel('Create a new local Godot 4.7 package with the saved character, rig, facial shapes, UVs and skin material. '
            'No animation clips or body-animation corrective runtime are included. Animation quality and public distribution rights need separate review.')
        text.setWordWrap(True);layout.addWidget(text)
        self.table=QTableWidget(len(review.sources),3);self.table.setHorizontalHeaderLabels(['Input','Content SHA-256','Authorize Godot use'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.checks=[]
        for row,source in enumerate(review.sources):
            for column,value in [(0,source.label),(1,source.sha256)]:
                item=QTableWidgetItem(value);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);item.setToolTip(source.asset_id+'\n'+source.sha256)
                self.table.setItem(row,column,item)
            check=QCheckBox('Reviewed');check.setChecked(False);check.toggled.connect(self.refresh);self.table.setCellWidget(row,2,check);self.checks.append(check)
        layout.addWidget(self.table)
        layout.addWidget(QLabel('Confirm only rights you reviewed for these exact inputs. NoAI remains enabled; original-source redistribution stays forbidden.'))
        self.note=QLineEdit();self.note.setMaxLength(1024);self.note.setPlaceholderText('Reviewed license or authorization for this private Godot use')
        self.note.textChanged.connect(self.refresh);layout.addWidget(self.note)
        row=QHBoxLayout();self.destination=QLineEdit();self.destination.setPlaceholderText('New package folder (must not exist)')
        self.destination.textChanged.connect(self.refresh);browse=QPushButton('Choose parent folder…');browse.clicked.connect(self.browse)
        row.addWidget(self.destination,1);row.addWidget(browse);layout.addLayout(row)
        self.status=QLabel('Review every listed input and choose a new destination.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Verify and export')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons);self.refresh()

    def browse(self):
        parent=QFileDialog.getExistingDirectory(self,'Choose the parent of a new Godot package')
        if parent:self.destination.setText(str(Path(parent)/'character-godot'))

    def refresh(self,*_):
        if not hasattr(self,'buttons'):return
        ready=all(c.isChecked() for c in self.checks) and bool(self.note.text().strip()) and bool(self.destination.text().strip())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ready)
        self.status.setText('Export verifies fresh Blender and Godot copies before creating the new folder. Existing folders are never replaced.' if ready else
            'Review every listed input, record its reviewed authorization and choose a new destination.')

    def request(self) -> StaticGodotRequest:
        permissions=[]
        for source,check in zip(self.review.sources,self.checks):
            policy=LicensePolicy(provider='Explicit per-use project review',license_name=self.note.text().strip(),
                source_uri='ucc-project://'+self.review.project_id+'/'+source.asset_id+'/'+source.sha256,
                reviewed=check.isChecked(),no_ai=True,can_use_non_unreal=check.isChecked(),ai_input_allowed=False,
                redistribute_source_allowed=False)
            permissions.append(EngineInputPermission(source.asset_id,source.sha256,policy,source_only=False))
        return StaticGodotRequest(str(uuid4()),self.review.project_id,self.review.revision,self.review.project_sha256,
            tuple((s.asset_id,s.sha256) for s in self.review.sources),tuple(permissions))
