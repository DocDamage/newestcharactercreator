"""An explicit human observation about a private authored-idle preview."""

from dataclasses import dataclass
from typing import Literal

from .errors import ValidationError
from .target_action_format import checked_text


@dataclass(frozen=True, slots=True)
class AuthoredIdleVisualDecision:
    decision: Literal['approve', 'rework']
    reviewer: str
    note: str
    personally_reviewed: bool

    def __post_init__(self) -> None:
        if type(self.decision) is not str or self.decision not in {'approve', 'rework'}:
            raise ValidationError('Choose Approve or Needs rework for this visual review')
        checked_text(self.reviewer, 160)
        if (type(self.note) is not str or not 0 < len(self.note) <= 2000 or self.note != self.note.strip()
                or any(not (character.isprintable() or character == '\n') for character in self.note)):
            raise ValidationError('Enter a visual review note of 1–2,000 characters')
        if self.personally_reviewed is not True:
            raise ValidationError('Confirm that you personally reviewed this exact private preview')

    def to_dict(self) -> dict:
        return {'decision': self.decision, 'reviewer': self.reviewer, 'note': self.note,
                'personally_reviewed': self.personally_reviewed}
