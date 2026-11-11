"""Deterministic sprite camera/frame plan, without pretending to render art."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Mapping

from ucc.core.errors import ValidationError
from ucc.core.models import finite_number

MAX_TOTAL_FRAMES = 4096


@dataclass(frozen=True, slots=True)
class CameraProfile:
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    orthographic_scale: float = 2.3
    roll_deg: float = 0.0
    directions: int = 8
    custom_yaws: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        for name in ("yaw_deg", "pitch_deg", "roll_deg"):
            finite_number(getattr(self, name), name, -360, 360)
        finite_number(self.orthographic_scale, "orthographic_scale", .1, 100.0)
        if type(self.directions) is not int or self.directions < 1 or self.directions > 64:
            raise ValidationError("directions must be 1–64")
        if self.custom_yaws is not None:
            if len(self.custom_yaws) != self.directions:
                raise ValidationError("custom_yaws count must equal directions")
            for y in self.custom_yaws:
                finite_number(y, "custom yaw", -360, 360)

    def angles(self) -> tuple[float, ...]:
        if self.custom_yaws is not None:
            return self.custom_yaws
        return tuple(round((self.yaw_deg + i * 360 / self.directions) % 360, 6)
                     for i in range(self.directions))


@dataclass(frozen=True, slots=True)
class PlannedFrame:
    clip: str
    direction_index: int
    yaw_deg: float
    frame_index: int
    timestamp_s: float
    file_name: str

    def to_dict(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class RenderPlan:
    width: int
    height: int
    fps: int
    camera: CameraProfile
    frames: tuple[PlannedFrame, ...]

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": 1, "resolution": {"width": self.width, "height": self.height},
                "fps": self.fps,
                "camera": {"yaw_deg": self.camera.yaw_deg, "pitch_deg": self.camera.pitch_deg,
                           "roll_deg": self.camera.roll_deg, "orthographic_scale": self.camera.orthographic_scale,
                           "angles": list(self.camera.angles())},
                "rendered": False, "frames": [x.to_dict() for x in self.frames]}


def build_plan(clips: Mapping[str, int], camera: CameraProfile, *, width: int = 128,
               height: int = 128, fps: int = 12) -> RenderPlan:
    """Create a reproducible frame sequence; no image output is generated."""
    if not isinstance(clips, Mapping) or not clips:
        raise ValidationError("A sprite plan needs one or more real clip identifiers")
    for label, num in (("width", width), ("height", height)):
        if type(num) is not int or num < 16 or num > 2048:
            raise ValidationError(f"{label} must be 16–2048")
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValidationError("fps must be 1–120")
    count = 0
    for clip, total in clips.items():
        if not isinstance(clip, str) or not clip or len(clip) > 96 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in clip):
            raise ValidationError("clip IDs must be safe ASCII identifiers")
        if type(total) is not int or total < 1 or total > 1000:
            raise ValidationError("clip frame counts must be 1–1000")
        count += total * camera.directions
        if count > MAX_TOTAL_FRAMES:
            raise ValidationError("Sprite frame budget exceeded")
    frames = []
    for clip, total in sorted(clips.items()):
        for direction, yaw in enumerate(camera.angles()):
            for i in range(total):
                frames.append(PlannedFrame(clip, direction, yaw, i, round(i / fps, 7),
                                           f"{clip}/dir-{direction:02d}/frame-{i:04d}.png"))
    return RenderPlan(width, height, fps, camera, tuple(frames))
