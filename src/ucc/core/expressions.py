"""Bounded facial-preview intent and pinned existing MPFB expression data.

Metadata is never deformation evidence. A prepared library must be built and
independently verified by the Blender adapter before its identity is saved.
The editable master stays neutral; these values control a private preview.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import TYPE_CHECKING, Any

from .errors import CompatibilityError, ValidationError

if TYPE_CHECKING:
    from .models import PartInstance

POLICY = 'BOUNDED_MPFB_EXPRESSION_UNITS_V1'
MAX_STRENGTH = .5
DEFAULTS = {'eye_left_closure': 0., 'eye_right_closure': 0.,
            'mouth_corners': 0., 'mouth_open': 0.}
UNITS = {'eye_left_closure': 'eye-left-closure', 'eye_right_closure': 'eye-right-closure',
         'mouth_corners': 'mouth-corner-puller', 'mouth_open': 'mouth-open'}
FAMILIES = ('african', 'asian', 'caucasian')
KEY_PREFIX = 'UCC_EXPR_V1_'


def is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_expression_parameters(raw: object, *, partial: bool = False) -> dict[str, float]:
    if type(raw) is not dict or (set(raw) - DEFAULTS.keys()) or (not partial and set(raw) != DEFAULTS.keys()):
        raise ValidationError('Expression settings require the four supported named strengths')
    result = {}
    for name, value in raw.items():
        if type(value) not in (float, int) or not 0 <= value <= MAX_STRENGTH or not math.isfinite(value):
            raise ValidationError('Expression strength must be finite and between 0 and 0.5: '+name)
        result[name] = float(value)
    return result


@dataclass(frozen=True, slots=True)
class ExpressionState:
    """An immutable prepared-library reference and saved preview intent."""
    library_sha256: str
    parameters: tuple[tuple[str, float], ...] = tuple(DEFAULTS.items())

    def __post_init__(self) -> None:
        if not is_sha256(self.library_sha256):
            raise ValidationError('Prepared expressions require a content-addressed library identity')
        if (type(self.parameters) is not tuple or any(type(row) is not tuple or len(row) != 2
                or type(row[0]) is not str for row in self.parameters)
                or len(dict(self.parameters)) != len(self.parameters)):
            raise ValidationError('Expression parameters require distinct immutable named values')
        validate_expression_parameters(dict(self.parameters))

    @property
    def neutral(self) -> bool:
        return all(value == 0 for _, value in self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {'library_sha256': self.library_sha256, 'parameters': dict(self.parameters)}

    @classmethod
    def from_dict(cls, raw: object) -> ExpressionState:
        if type(raw) is not dict or set(raw) != {'library_sha256', 'parameters'}:
            raise ValidationError('Invalid closed expression state')
        values = validate_expression_parameters(raw['parameters'])
        return cls(raw['library_sha256'], tuple(sorted(values.items())))


@dataclass(frozen=True, slots=True)
class ExpressionTarget:
    role: str
    family: str
    unit: str
    sha256: str

    def __post_init__(self) -> None:
        if (type(self.role) is not str or self.role not in UNITS
                or self.unit != UNITS[self.role] or self.family not in FAMILIES
                or not is_sha256(self.sha256)):
            raise ValidationError('Expression target differs from the supported unit/family naming contract')

    @property
    def source_relative(self) -> str:
        return 'targets/expression/units/'+self.family+'/'+self.unit+'.target.gz'

    @property
    def staged_name(self) -> str:
        return 'expr-'+self.role+'-'+self.family+'.target.gz'

    @property
    def key_name(self) -> str:
        return KEY_PREFIX+self.role+'_'+self.family


TARGETS = (
    ExpressionTarget('eye_left_closure', 'african', 'eye-left-closure', '2d358745e955ead9d73f85ed224568a8d347f3f3b897c26cbd412faf2bfa9f3a'),
    ExpressionTarget('eye_left_closure', 'asian', 'eye-left-closure', '0d52fee2d66b933ece83f3c7aa48e85bfe85e8adbed0931dbd37025866a1a67d'),
    ExpressionTarget('eye_left_closure', 'caucasian', 'eye-left-closure', 'ff0d21ceb6da55fe51e03b48a7562a650924fea9bef0c686fcd7aa44d16422ed'),
    ExpressionTarget('eye_right_closure', 'african', 'eye-right-closure', 'c1b0c3609d9fb59a97dabe8ace10622da58969f4566125b38f47285afef320d5'),
    ExpressionTarget('eye_right_closure', 'asian', 'eye-right-closure', '0c99a5f559a1d67f630a329b9724fe3742a2c35709b8baa8a6d37903f35b9b77'),
    ExpressionTarget('eye_right_closure', 'caucasian', 'eye-right-closure', '2b7be6bc65845d77e5f83b7bf852090854747e448644997795fa59b6cf76122d'),
    ExpressionTarget('mouth_corners', 'african', 'mouth-corner-puller', '5560c685cd55ae6a00830e539ac54135cb4dcfec6a28be90510c931dcfdca478'),
    ExpressionTarget('mouth_corners', 'asian', 'mouth-corner-puller', 'd881bb8feda2637bdaef2c7d7c6bed12f0be5914949e5a2cb9b06a583af412c0'),
    ExpressionTarget('mouth_corners', 'caucasian', 'mouth-corner-puller', 'd881bb8feda2637bdaef2c7d7c6bed12f0be5914949e5a2cb9b06a583af412c0'),
    ExpressionTarget('mouth_open', 'african', 'mouth-open', 'd710d4ae1693e7278a5bbe620276970fb6e89de139b50aaaea2830c31146459a'),
    ExpressionTarget('mouth_open', 'asian', 'mouth-open', 'b52bbe631152844bb7b835c0f98d12ab0a1c0689e02e067b239d8349ccf9aab2'),
    ExpressionTarget('mouth_open', 'caucasian', 'mouth-open', 'dc1260a8728d93a9c52d6b35b5f55ad39ab8096090acd5ccad7f973c26e28818'),
)


def validate_expression_part_rebind(before: tuple[PartInstance, ...],
                                    after: tuple[PartInstance, ...]) -> None:
    """Check intent preservation, never substitute for real asset verification.

Adding keys changes the master identity. A selected hand must have a genuinely
new compatible library, retaining its variant and instance identity. The job
adapter still has to independently reconstruct that library and saved master.
"""
    from .models import PartInstance
    if any(type(parts) is not tuple or any(not isinstance(p, PartInstance) for p in parts)
           for parts in (before, after)):
        raise ValidationError('Expression part rebinding requires immutable validated part instances')
    if not before:
        if after:
            raise CompatibilityError('Expression preparation cannot introduce a new part selection')
        return
    if len(before) != 1 or len(after) != 1:
        raise CompatibilityError('Expression preparation supports one registered left hand only')
    old, new = before[0], after[0]
    pattern = r'ucc-hand-v1-([0-9a-f]{64})-(shorter|longer)'
    old_id, new_id = re.fullmatch(pattern, old.part_asset_id), re.fullmatch(pattern, new.part_asset_id)
    if (old_id is None or new_id is None or old_id[1] == new_id[1] or old_id[2] != new_id[2]
            or old.slot != 'hand.L' or new.slot != old.slot or old.part_id != new.part_id
            or old.visible is not True or new.visible is not True
            or old.status != 'proposed' or new.status != 'proposed'):
        raise CompatibilityError('Expression preparation must genuinely rebind and retain the selected hand')
