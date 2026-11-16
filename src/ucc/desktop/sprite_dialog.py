"""Explicit private render review and bounded camera/canvas selection."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QCheckBox,QLineEdit,
    QDialogButtonBox,QPushButton,QHBoxLayout,QComboBox,QDoubleSpinBox,QFormLayout,QFileDialog)
from ucc.core.sprite_render import SpriteSettings,SpritePermission,SpriteRenderRequest
from ucc.jobs.static_export_sources import ExportReview


class SpriteRenderDialog(QDialog):
    def __init__(self,review: ExportReview,parent=None):
        super().__init__(parent);self.review=review;self.setWindowTitle('Render character sprite sample');self.resize(1000,650)
        layout=QVBoxLayout(self)
        text=QLabel('Render the saved neutral character into four or eight transparent RGBA directions and an atlas. '
            'Saved skin color, roughness and compatible hand are retained. Animation clips and artist quality need separate work.');self.description=text;text.setWordWrap(True);layout.addWidget(text)
        form=QFormLayout();self.resolution=QComboBox();self.directions=QComboBox()
        for n in (128,256):self.resolution.addItem(f'{n} × {n}',n)
        self.resolution.setCurrentIndex(1)
        for n in (4,8):self.directions.addItem(str(n),n)
        self.yaw=QDoubleSpinBox();self.yaw.setRange(-180,180);self.yaw.setSingleStep(15);self.yaw.setSuffix('°')
        self.pitch=QDoubleSpinBox();self.pitch.setRange(-30,30);self.pitch.setSingleStep(5);self.pitch.setSuffix('°')
        for label,widget in (('Pixels per direction',self.resolution),('Directions',self.directions),('Starting yaw (0° front)',self.yaw),('Elevation',self.pitch)):form.addRow(label,widget)
        layout.addLayout(form);layout.addWidget(QLabel('Orthographic camera; automatic whole-character framing with a transparent margin.'))
        self.table=QTableWidget(len(review.sources),3);self.table.setHorizontalHeaderLabels(['Input','Content SHA-256','Authorize private sprite rendering']);self.checks=[]
        for i,source in enumerate(review.sources):
            self.table.setItem(i,0,QTableWidgetItem(source.label));self.table.setItem(i,1,QTableWidgetItem(source.sha256))
            check=QCheckBox('Reviewed');self.table.setCellWidget(i,2,check);self.checks.append(check);check.toggled.connect(self.refresh)
        self.table.resizeColumnsToContents();layout.addWidget(self.table)
        note=QLabel('Review each exact input for this render use. NoAI remains enabled; original-source redistribution stays forbidden.');note.setWordWrap(True);layout.addWidget(note)
        self.note=QLineEdit();self.note.setPlaceholderText('Reviewed license or authorization for this private sprite render');layout.addWidget(self.note)
        row=QHBoxLayout();self.destination=QLineEdit();self.destination.setPlaceholderText('New sprite package folder (must not exist)')
        browse=QPushButton('Choose parent folder…');browse.clicked.connect(self.browse);row.addWidget(self.destination);row.addWidget(browse);layout.addLayout(row)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Verify and render');self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.note.textChanged.connect(self.refresh);self.destination.textChanged.connect(self.refresh);self.refresh()

    def refresh(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(all(c.isChecked() for c in self.checks) and bool(self.note.text().strip()) and bool(self.destination.text().strip()))

    def browse(self):
        path=QFileDialog.getExistingDirectory(self,'Choose an existing parent for the new sprite folder')
        if path:self.destination.setText(str(Path(path)/'character-sprites'))

    def request(self) -> SpriteRenderRequest:
        settings=SpriteSettings(self.resolution.currentData(),self.directions.currentData(),self.yaw.value(),self.pitch.value())
        permissions=tuple(SpritePermission(s.asset_id,s.sha256,self.note.text().strip(),c.isChecked(),c.isChecked()) for s,c in zip(self.review.sources,self.checks))
        r=self.review
        return SpriteRenderRequest(str(uuid4()),r.project_id,r.revision,r.project_sha256,tuple((s.asset_id,s.sha256) for s in r.sources),permissions,settings)
