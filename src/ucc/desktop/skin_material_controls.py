"""Explicit local drafts; widget changes never rewrite saved appearance proofs."""
import re
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGroupBox,QFormLayout,QLineEdit,QPushButton,QDoubleSpinBox,QLabel,QColorDialog
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.errors import ValidationError


class SkinMaterialControls(QGroupBox):
    apply_requested=Signal(object)

    def __init__(self):
        super().__init__('Skin color and surface')
        layout=QFormLayout(self);self.color=QLineEdit();self.color.setPlaceholderText('#RRGGBB');self.color.setMaxLength(16)
        self.choose=QPushButton('Choose color…');self.choose.clicked.connect(self._choose)
        self.roughness=QDoubleSpinBox();self.roughness.setRange(0.,1.);self.roughness.setDecimals(3);self.roughness.setSingleStep(.05);self.roughness.setValue(.5)
        self.status=QLabel('Choose a color, then Apply to save it.');self.status.setWordWrap(True)
        self.apply=QPushButton('Apply skin color and roughness…');self.apply.setEnabled(False)
        layout.addRow('Color (sRGB)',self.color);layout.addRow('',self.choose);layout.addRow('Roughness',self.roughness)
        layout.addRow(self.status);layout.addRow(self.apply)
        self._token=None;self._saved=None;self._shown_color='';self._shown_roughness=.5;self._eligible=False;self._clean=False
        self.color.textChanged.connect(self._refresh);self.roughness.valueChanged.connect(self._refresh)
        self.apply.clicked.connect(self._apply);self.setEnabled(False)

    def _choose(self):
        color=QColorDialog.getColor(QColor(self.color.text()) if QColor.isValidColor(self.color.text()) else QColor('white'),self,'Choose skin color')
        if color.isValid():self.color.setText(color.name())

    def draft_spec(self) -> SkinMaterialSpec:
        text=self.color.text().strip()
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',text):raise ValidationError('Enter a six-digit color such as #946040')
        rgb=(self._saved.base_color_srgb if self._saved is not None and text.lower()==self._shown_color.lower()
            else tuple(int(text[i:i+2],16)/255. for i in (1,3,5)))
        rough=(self._saved.roughness if self._saved is not None and self.roughness.value()==self._shown_roughness else self.roughness.value())
        return SkinMaterialSpec(rgb,rough)

    def display(self,project_id: str,spec: SkinMaterialSpec | None,*,eligible: bool,clean: bool,error: str=''):
        if error and self._token is not None and self._token[0]==project_id:
            self._eligible=False;self._clean=False;self.setEnabled(False);self.apply.setEnabled(False);self.status.setText(error)
            return
        token=(project_id,None if spec is None else spec.sha256)
        if token!=self._token:
            self._token=token;self._saved=spec
            self._shown_color='' if spec is None else '#'+''.join(f'{round(v*255):02x}' for v in spec.base_color_srgb)
            self.color.blockSignals(True);self.roughness.blockSignals(True)
            self.color.setText(self._shown_color);self.roughness.setValue(.5 if spec is None else spec.roughness)
            self._shown_roughness=self.roughness.value()
            self.color.blockSignals(False);self.roughness.blockSignals(False)
        self._eligible=eligible and not error;self._clean=clean;self.setEnabled(self._eligible)
        self._refresh()
        if error:self.status.setText(error)
        elif not eligible:self.status.setText('Prepare a compatible saved character before assigning a skin material.')

    def _refresh(self,*_):
        try:spec=self.draft_spec()
        except ValidationError:
            self.apply.setEnabled(False);self.status.setText('Choose a color in #RRGGBB format. Changes are saved by Apply.');return
        self.apply.setEnabled(self._eligible and self._clean)
        self.status.setText('Save other character settings before applying this material.' if not self._clean else
            ('Matches the saved material. Apply verifies it without a new revision.' if spec==self._saved else 'Apply saves this color and roughness to a new character master.'))

    def _apply(self):self.apply_requested.emit(self.draft_spec())
