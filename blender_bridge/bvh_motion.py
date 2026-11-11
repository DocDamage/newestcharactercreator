"""Parse bounded user-selected BVH motion for a narrow, non-retargeted Blender test.

No remote buffers, add-ons, scripts, arbitrary file paths or bone mapping guesses.
Only direct, unambiguous source/MPFB bone names and rotation deltas are tried.
This is NOT general BVH rest-orientation retargeting, source-clip editing or engine
certification. The original BVH is only read, never rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024
MAX_FRAMES = 240
MAX_CHANNELS = 512
MAX_SOURCE_BONES = 512


class LocalBvhError(RuntimeError):
    """Selected local BVH is unsafe or outside the narrow preview compatibility gate."""


@dataclass(frozen=True, slots=True)
class LocalBvhMotion:
    frame_time: float
    frames: int
    rotations: dict[str, tuple[tuple[float, float, float], ...]]
    source_bones: tuple[str, ...]

    def eligible_rotation(self, preferred_names: list[str]) -> tuple[str, str, tuple[tuple[float, float, float], ...]]:
        """Return one explicit matching MPFB bone, not inferred Mixamo/UE aliases."""
        if len({name.casefold() for name in preferred_names}) != len(preferred_names):
            raise LocalBvhError("Destination armature has ambiguous case-insensitive bone names")
        for target in preferred_names:
            match = self.rotations.get(target.casefold())
            if match is None:
                continue
            base = match[0]
            maximum = max(
                abs(rotation[axis] - base[axis])
                for rotation in match for axis in range(3)
            )
            if not 1 <= maximum <= 45:
                continue
            actual = next(name for name in self.source_bones if name.casefold() == target.casefold())
            return actual, target, match
        raise LocalBvhError(
            "No directly named, substantially weighted MPFB deform bone has "
            "safe 1–45 degree rotation differences in this BVH; no automatic retarget"
        )


def read_local_bvh(source: Path) -> LocalBvhMotion:
    path = Path(source)
    if path.suffix.lower() != ".bvh" or path.is_symlink() or not path.is_file():
        raise LocalBvhError("Local animation must be an explicitly staged regular BVH file")
    size = path.stat().st_size
    if not 50 < size <= MAX_BYTES:
        raise LocalBvhError("BVH file is empty or exceeds the 64 MiB limit")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise LocalBvhError("BVH must have valid UTF-8 text") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "HIERARCHY":
        raise LocalBvhError("BVH must begin with a HIERARCHY")
    try:
        motion_at = lines.index("MOTION")
    except ValueError as exc:
        raise LocalBvhError("BVH does not contain motion frames") from exc
    if motion_at < 5 or len(lines) < motion_at + 4:
        raise LocalBvhError("BVH has incomplete hierarchy or motion headers")

    # A narrow hierarchy reader: use the explicit order of CHANNELS declarations
    # to locate rotations in each numeric motion row. The full original file is
    # also inspected by UCC's independent strict metadata parser before staging.
    stack: list[str] = []
    pending: str | None = None
    bones: list[str] = []
    channels: list[tuple[str, tuple[str, ...], int]] = []
    offset = 0
    for line in lines[1:motion_at]:
        if line.startswith(("ROOT ", "JOINT ")):
            tokens = line.split(maxsplit=1)
            name = tokens[1]
            if pending is not None or not name or len(name) > 128 or ":" in name:
                raise LocalBvhError("Unsupported or ambiguously named BVH joint")
            if name.casefold() in {item.casefold() for item in bones}:
                raise LocalBvhError("Duplicate BVH joint names are not permitted")
            bones.append(name)
            if len(bones) > MAX_SOURCE_BONES:
                raise LocalBvhError("Too many source BVH joints")
            pending = name
        elif line == "End Site":
            pending = "#end_site"
        elif line == "{":
            if pending is None:
                raise LocalBvhError("Unexpected BVH hierarchy brace")
            stack.append(pending)
            pending = None
        elif line == "}":
            if not stack:
                raise LocalBvhError("Unexpected BVH closing brace")
            stack.pop()
        elif line.startswith("CHANNELS "):
            if not stack or stack[-1] == "#end_site":
                raise LocalBvhError("Channels are not associated with a joint")
            cells = line.split()
            if len(cells) < 3 or not cells[1].isdigit():
                raise LocalBvhError("Invalid BVH channel declaration")
            names = tuple(cells[2:])
            if len(names) != int(cells[1]) or not 1 <= len(names) <= 9:
                raise LocalBvhError("BVH channel count mismatch")
            if len(set(names)) != len(names):
                raise LocalBvhError("Duplicate BVH motion channel")
            if any(name not in {
                "Xrotation", "Yrotation", "Zrotation",
                "Xposition", "Yposition", "Zposition",
            } for name in names):
                raise LocalBvhError("Unsupported BVH channel type")
            channels.append((stack[-1], names, offset))
            offset += len(names)
            if offset > MAX_CHANNELS:
                raise LocalBvhError("Too many BVH animation channels")
        elif line.startswith("OFFSET "):
            if len(line.split()) != 4:
                raise LocalBvhError("Malformed BVH bone offset")
        else:
            raise LocalBvhError("Unknown BVH hierarchy element")
    if stack or pending is not None or not bones or not channels:
        raise LocalBvhError("BVH hierarchy is not fully closed")
    if any(name not in {row[0] for row in channels} for name in bones):
        raise LocalBvhError("BVH joint missing its channel declaration")
    frame_line = lines[motion_at + 1]
    time_line = lines[motion_at + 2]
    if not frame_line.startswith("Frames:") or not time_line.startswith("Frame Time:"):
        raise LocalBvhError("BVH frame count or time declaration is missing")
    try:
        frames = int(frame_line.partition(":")[2].strip())
        dt = float(time_line.partition(":")[2].strip())
    except ValueError as exc:
        raise LocalBvhError("Invalid BVH frame count or frame time") from exc
    if not 5 <= frames <= MAX_FRAMES or not math.isfinite(dt) or not 0.005 <= dt <= 0.5:
        raise LocalBvhError("Local BVH preview supports 5–240 frames with finite timing")
    motion_rows = lines[motion_at + 3:]
    if len(motion_rows) != frames or frames * offset > 5_000_000:
        raise LocalBvhError("BVH motion rows do not match declared frame count")

    rotation_channels = [
        (name, start, tuple(names.index(axis) for axis in ("Xrotation", "Yrotation", "Zrotation")))
        for name, names, start in channels
        if all(axis in names for axis in ("Xrotation", "Yrotation", "Zrotation"))
    ]
    if not rotation_channels:
        raise LocalBvhError("BVH has no complete XYZ bone rotation channels")
    collected: dict[str, list[tuple[float, float, float]]] = {
        name.casefold(): [] for name, _, _ in rotation_channels
    }
    for frame_idx, raw in enumerate(motion_rows):
        words = raw.split()
        if len(words) != offset:
            raise LocalBvhError(f"BVH frame {frame_idx + 1} channel count differs")
        try:
            values = [float(word) for word in words]
        except ValueError as exc:
            raise LocalBvhError("Non-numeric BVH motion channel") from exc
        if any(not math.isfinite(value) or abs(value) > 1e6 for value in values):
            raise LocalBvhError("BVH motion contains non-finite/extreme numbers")
        for name, start, indices in rotation_channels:
            angles = tuple(values[start + index] for index in indices)
            if any(abs(value) > 180 for value in angles):
                raise LocalBvhError("Selected BVH rotational channels exceed 180 degrees")
            collected[name.casefold()].append(angles)
    return LocalBvhMotion(
        dt, frames, {key: tuple(angles) for key, angles in collected.items()},
        tuple(bones),
    )
