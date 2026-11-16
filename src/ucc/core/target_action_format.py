"""Closed metadata format for private registered target previews.

Metadata alone never admits an Action or cache. Host validators must bind the
current registered source and independently validate every retained proof.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import UUID

from .errors import ValidationError

POLICY = "UCC_TARGET_ACTION_BINDING_V1"
REQUEST_POLICY = "UCC_TARGET_ACTION_PREPARATION_V1"
PROFILE = "UCC_MPFB_REGISTERED_TARGET_PREVIEW_V1"
MAX_BYTES = 256 * 1024
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
ROOT_POLICIES = frozenset({"ARMATURE_ORIGIN_DISPLACEMENT_V1", "SOURCE_HIP_MIDPOINT_V1"})
SKIN_POLICY = "BOUND_CORRECTIVE_SMOOTH_V1"
CLOCK = (("source_first_frame", 2), ("source_last_frame", 301),
         ("target_first_frame", 1), ("target_last_frame", 300),
         ("fps_numerator", 30), ("fps_denominator", 1),
         ("playback_policy", "ONCE_HOLD_LAST"))
ADMISSION = (("local_preview_only", True), ("saved_target_action_verified", True),
             ("engine_import_verified", False), ("retargeting_verified", False),
             ("editing_authorized", False), ("usable_action_approved", False),
             ("visual_quality_approved", False), ("loop_quality_approved", False),
             ("distribution_license_review_complete", False),
             ("source_redistribution_authorized", False),
             ("cloud_transmission_authorized", False), ("ai_input_authorized", False))
RETAINED_FILES = frozenset({
    "preparation_request.json", "source_snapshot.json", "native_mapping.json",
    "neutral/first_request.json", "neutral/first_result.json",
    "neutral/second_request.json", "neutral/second_result.json",
    "source_intake_first/request.json", "source_intake_first/result.json",
    "source_intake_second/request.json", "source_intake_second/result.json",
    "body_first/request.json", "body_first/result.json",
    "body_first/target_timeline.json", "body_first/review_motion.blend",
    "body_second/request.json", "body_second/result.json",
    "body_second/target_timeline.json", "body_second/review_motion.blend",
    "body_reopen/request.json", "body_reopen/result.json",
    "playback/request.json", "playback/result.json", "playback/motion_skin.json",
    "playback/motion_skin.bin", "playback/motion_contacts.json",
    "surface_verify/request.json", "surface_verify/result.json",
    "body_first/review_frames/manifest.json", "body_first/review_frames/index.html",
    *(f"body_first/review_frames/frame_{frame:04d}_{view}.png"
      for frame in (1, 75, 150, 225, 300) for view in ("front", "side", "quarter")),
})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def checked_text(value: object, maximum: int = 200) -> str:
    require(type(value) is str and 0 < len(value) <= maximum
            and value == value.strip() and all(character.isprintable() for character in value),
            "Target preview metadata contains invalid text")
    return value


def checked_sha(value: object) -> str:
    require(type(value) is str and len(value) == 64
            and all(character in "0123456789abcdef" for character in value),
            "Target preview metadata requires a lowercase SHA-256")
    return value


def checked_uuid(value: object) -> str:
    try:
        require(type(value) is str and str(UUID(value)) == value,
                "Target preview metadata requires a canonical job UUID")
    except (ValueError, AttributeError, TypeError) as error:
        raise ValidationError("Malformed target preview job UUID") from error
    return value


def checked_pair(value: object) -> tuple[str, str]:
    require(type(value) is tuple and len(value) == 2,
            "Target preview requires two actual worker identities")
    return checked_uuid(value[0]), checked_uuid(value[1])


def closed(value: object, fields: set[str]) -> dict:
    require(type(value) is dict and set(value) == fields,
            "Target preview metadata has missing or unknown fields")
    return value


def canonical_bytes(value: object) -> bytes:
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValidationError("Invalid target preview JSON values") from error
    require(len(result) <= MAX_BYTES, "Target preview metadata exceeds its byte limit")
    return result


def read_document(payload: bytes) -> dict:
    require(type(payload) is bytes and 0 < len(payload) <= MAX_BYTES,
            "Target preview metadata must be bounded JSON bytes")

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate metadata key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite metadata number")

    try:
        value = json.loads(payload, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValidationError("Malformed target preview JSON") from error
    require(type(value) is dict and canonical_bytes(value) == payload,
            "Target preview metadata is not canonical JSON")
    return value


def checked_fixed(value: object, expected: tuple) -> None:
    closed(value, {key for key, _ in expected})
    require(all(type(value[key]) is type(item) and value[key] == item
                for key, item in expected), "Target preview profile or readiness flags differ")


@dataclass(frozen=True, slots=True)
class TargetActionFile:
    name: str
    sha256: str
    bytes: int

    def __post_init__(self):
        require(type(self.name) is str and self.name in RETAINED_FILES,
                "Unexpected retained target preview file")
        checked_sha(self.sha256)
        require(type(self.bytes) is int and 0 < self.bytes <= MAX_FILE_BYTES,
                "Retained target preview file exceeds its byte bound")

    def to_dict(self) -> dict:
        return {"sha256": self.sha256, "bytes": self.bytes}

    @classmethod
    def from_dict(cls, name: str, raw: object) -> "TargetActionFile":
        value = closed(raw, {"sha256", "bytes"})
        return cls(name, value["sha256"], value["bytes"])


def document_sha256(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()
