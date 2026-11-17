"""Explicit private debug draw selection; no delivery or appearance grant."""
from dataclasses import dataclass
from hashlib import sha256

from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_sha, checked_text, checked_uuid
from .godot_candidate_contract import canonical_bytes
from .godot_registered_body_runtime import FALSE_FLAGS

POLICY = 'UCC_PRIVATE_REGISTERED_BODY300_DEBUG_DRAW_V1'
PROFILE = 'GODOT_4_7_1_MOBILE_VULKAN_BODY300_DEBUG_DRAW_V1'
STATUS = 'REGISTERED_BODY300_DEBUG_DRAW_VERIFIED'
FRAMES = (1, 150, 300)


@dataclass(frozen=True, slots=True)
class RegisteredBodyDrawSelection:
    draw_id: str
    diagnostic_receipt_sha256: str
    godot_executable_sha256: str
    godot_main_sha256: str
    purpose: str
    private_local_draw_confirmed: bool

    def __post_init__(self) -> None:
        checked_uuid(self.draw_id)
        checked_text(self.purpose, 500)
        for value in (self.diagnostic_receipt_sha256,
                      self.godot_executable_sha256, self.godot_main_sha256):
            checked_sha(value)
        if self.private_local_draw_confirmed is not True:
            raise ValidationError('Require explicit private local diagnostic drawing')

    def to_dict(self) -> dict:
        return dict(schema_version=1, policy=POLICY, profile=PROFILE,
                    draw_id=self.draw_id,
                    diagnostic_receipt_sha256=self.diagnostic_receipt_sha256,
                    godot_executable_sha256=self.godot_executable_sha256,
                    godot_main_sha256=self.godot_main_sha256,
                    purpose=self.purpose, private_local_draw_confirmed=True,
                    **{name: False for name in FALSE_FLAGS})

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()
