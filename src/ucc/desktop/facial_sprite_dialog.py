"""Explicit animated use review with saved strengths and a fixed timeline."""
from PySide6.QtWidgets import QLabel
from ucc.core.facial_sprites import FacialSpriteRequest
from ucc.core.sprite_render import canonical
from ucc.core.expression_clip import validate_expression_clip
from .sprite_dialog import SpriteRenderDialog


class FacialSpriteDialog(SpriteRenderDialog):
    def __init__(self,review,clip: dict,parent=None):
        super().__init__(review,parent);self.clip_json=canonical(validate_expression_clip(clip))
        self.setWindowTitle('Render animated facial sprites')
        self.description.setText('Render the saved facial expression as a 25-frame loop per direction: neutral → expression → neutral at 24 fps. '
            'Saved skin material and compatible hand are retained. Each direction has a 5 × 5 sheet. Artist/pixel-art quality requires separate review.')
        summary=QLabel('Saved expression strengths: '+', '.join(f'{k.replace("_"," ")}: {v:g}' for k,v in clip['parameters'].items())
            +'. Change and save strengths in the Character tab before this review.');summary.setWordWrap(True);self.layout().insertWidget(1,summary)
        self.note.setPlaceholderText('Reviewed license or authorization for this private animated sprite render')
        self.destination.setPlaceholderText('New animated sprite package folder (must not exist)')

    def request(self) -> FacialSpriteRequest:
        return FacialSpriteRequest(super().request(),self.clip_json)
