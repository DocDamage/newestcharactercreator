"""Bounded, read-only inspection of BVH and glTF animation metadata.

This module cannot certify retargeting, visual playback, motion quality, or
license suitability for particular engines. No external URLs or buffers load.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from ucc.core.errors import UCCError
from ucc.export.inspect_glb import GLBInspectionError, _parse_glb, inspect_glb

MAX_BVH_BYTES = 64 * 1024 * 1024
MAX_GLTF_JSON_BYTES = 16 * 1024 * 1024
MAX_FRAME_CHANNEL_VALUES = 5_000_000
MAX_MOTION_FRAMES = 100_000
MAX_CHANNELS = 1024
MAX_NODES = 20_000
MAX_ANIMATIONS = 10_000
BVH_CHANNELS = {f"{axis}{suffix}" for axis in "XYZ" for suffix in ("position", "rotation")}
FRAME_HEADER = re.compile(r"^Frames:\s*(\d+)\s*$", re.I)
FRAME_TIME_HEADER = re.compile(r"^Frame\s+Time:\s*(\S+)\s*$", re.I)


class AnimationMetadataError(UCCError):
    """An animation source was malformed, unsafe, or too expensive to inspect."""


@dataclass(frozen=True, slots=True)
class ClipMetadata:
    ordinal: int
    name: str
    duration_seconds: float | None
    frame_count: int | None
    fps: float | None
    track_count: int
    animated_bones: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {field: list(value) if isinstance(value, tuple) else value
                for field, value in ((key, getattr(self, key)) for key in self.__dataclass_fields__)}


@dataclass(frozen=True, slots=True)
class AnimationInspection:
    format: str
    status: str  # METADATA_EXTRACTED or REQUIRES_CONVERSION; never RETARGETED
    skeleton_fingerprint: str | None
    bone_names: tuple[str, ...]
    clips: tuple[ClipMetadata, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "format": self.format, "status": self.status,
                "skeleton_fingerprint": self.skeleton_fingerprint,
                "bone_names": list(self.bone_names),
                "clips": [clip.to_dict() for clip in self.clips], "warnings": list(self.warnings),
                "preview_verified": False, "retarget_verified": False,
                "engine_validated": False}


def _regular_bounded(path: Path, maximum: int) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise AnimationMetadataError("Select an existing non-symlink file")
    resolved = source.resolve(strict=True)
    size = resolved.stat().st_size
    if not 0 < size <= maximum:
        raise AnimationMetadataError("Source is empty or exceeds metadata inspection size limit")
    return resolved


def _finite_number(text: str, name: str, *, positive: bool = False) -> float:
    try:
        value = float(text)
    except (ValueError, OverflowError) as exc:
        raise AnimationMetadataError(f"Invalid {name}: not numeric") from exc
    if not math.isfinite(value) or (positive and value <= 0):
        raise AnimationMetadataError(f"Invalid {name}: must be finite" + (" and > 0" if positive else ""))
    return value


def _signature(bone_hierarchy: list[tuple[str, str | None, tuple[str, ...]]]) -> str | None:
    if not bone_hierarchy:
        return None
    encoded = json.dumps(bone_hierarchy, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inspect_bvh(path: Path) -> AnimationInspection:
    """Verify BVH channel declarations and all frame values without storing motion frames."""
    source = _regular_bounded(path, MAX_BVH_BYTES)
    stack: list[str] = []
    pending: str | None = None
    bones: list[tuple[str, str | None, tuple[str, ...]]] = []
    declared_channels = 0
    frames: int | None = None
    frame_time: float | None = None
    motion_started = False
    frame_rows = 0
    next_header = "frames"
    original_size = source.stat().st_size
    original_mtime = source.stat().st_mtime_ns
    with source.open("r", encoding="utf-8-sig", errors="strict", newline=None) as stream:
        first = ""
        for line in stream:
            if line.strip():
                first = line.strip()
                break
        if first.upper() != "HIERARCHY":
            raise AnimationMetadataError("BVH file must begin with HIERARCHY")
        for raw in stream:
            line = raw.strip()
            if not line:
                continue
            if not motion_started:
                if line == "MOTION":
                    if stack or pending is not None or not bones or declared_channels == 0:
                        raise AnimationMetadataError("BVH motion header before closed valid skeleton")
                    motion_started = True
                    continue
                if line == "{":
                    if pending is None:
                        raise AnimationMetadataError("Unexpected BVH opening brace")
                    stack.append(pending)
                    pending = None
                    if len(stack) > 128:
                        raise AnimationMetadataError("Excessive BVH hierarchy nesting")
                    continue
                if line == "}":
                    if not stack or pending is not None:
                        raise AnimationMetadataError("Unexpected BVH closing brace")
                    stack.pop()
                    continue
                if line.startswith(("ROOT ", "JOINT ")):
                    kind, name = line.split(maxsplit=1)
                    if pending is not None or (kind == "ROOT" and (stack or bones)) or (kind == "JOINT" and not stack):
                        raise AnimationMetadataError("Invalid BVH ROOT/JOINT declaration")
                    if not name or len(name) > 128 or name in {item[0] for item in bones}:
                        raise AnimationMetadataError("Invalid or duplicate BVH bone name")
                    bones.append((name, stack[-1] if stack else None, ()))
                    if len(bones) > MAX_NODES:
                        raise AnimationMetadataError("Too many BVH bones")
                    pending = name
                    continue
                if line == "End Site":
                    if pending is not None or not stack:
                        raise AnimationMetadataError("BVH End Site without parent")
                    pending = "#end_site"
                    continue
                if line.startswith("OFFSET "):
                    if not stack or len(line.split()) != 4:
                        raise AnimationMetadataError("Invalid BVH OFFSET")
                    for number in line.split()[1:]:
                        _finite_number(number, "BVH offset")
                    continue
                if line.startswith("CHANNELS "):
                    if not stack or stack[-1] == "#end_site":
                        raise AnimationMetadataError("BVH CHANNELS without bone")
                    tokens = line.split()
                    if len(tokens) < 3 or not tokens[1].isdigit():
                        raise AnimationMetadataError("Invalid BVH CHANNELS")
                    count = int(tokens[1])
                    declared = tokens[2:]
                    if not 1 <= count <= 9 or count != len(declared) or any(x not in BVH_CHANNELS for x in declared):
                        raise AnimationMetadataError("Unsupported BVH channel declaration")
                    if len(set(declared)) != len(declared):
                        raise AnimationMetadataError("Duplicate BVH channel")
                    if bones[-1][0] != stack[-1] or bones[-1][2]:
                        raise AnimationMetadataError("Duplicate or misplaced BVH CHANNELS")
                    bones[-1] = (bones[-1][0], bones[-1][1], tuple(declared))
                    declared_channels += count
                    if declared_channels > MAX_CHANNELS:
                        raise AnimationMetadataError("Too many BVH motion channels")
                    continue
                raise AnimationMetadataError("Unsupported or malformed BVH hierarchy line")
            else:
                if next_header == "frames":
                    match = FRAME_HEADER.fullmatch(line)
                    if match is None:
                        raise AnimationMetadataError("Expected BVH Frames header")
                    frames = int(match.group(1))
                    if not 1 <= frames <= MAX_MOTION_FRAMES or frames * declared_channels > MAX_FRAME_CHANNEL_VALUES:
                        raise AnimationMetadataError("BVH animation exceeds safe motion inspection limit")
                    next_header = "time"
                    continue
                if next_header == "time":
                    match = FRAME_TIME_HEADER.fullmatch(line)
                    if match is None:
                        raise AnimationMetadataError("Expected BVH Frame Time header")
                    frame_time = _finite_number(match.group(1), "frame time", positive=True)
                    next_header = "motion"
                    continue
                if frame_rows >= frames:  # type: ignore[operator]
                    raise AnimationMetadataError("Extra BVH motion frames")
                values = line.split()
                if len(values) != declared_channels:
                    raise AnimationMetadataError(f"BVH frame {frame_rows} has {len(values)} channels, expected {declared_channels}")
                for value in values:
                    _finite_number(value, f"frame {frame_rows} channel")
                frame_rows += 1
    if not motion_started or frame_time is None or frames is None or frame_rows != frames:
        raise AnimationMetadataError("BVH motion frames are missing or incomplete")
    if any(not channels for _, _, channels in bones):
        raise AnimationMetadataError("BVH skeleton bone missing CHANNELS")
    final_stat = source.stat()
    if final_stat.st_size != original_size or final_stat.st_mtime_ns != original_mtime:
        raise AnimationMetadataError("BVH source changed during metadata inspection")
    names = tuple(bone[0] for bone in bones)
    return AnimationInspection("bvh", "METADATA_EXTRACTED", _signature(bones), names,
                               (ClipMetadata(0, source.stem[:128], round(frames * frame_time, 6), frames,
                                             round(1 / frame_time, 6), declared_channels, names),), ())


def _int_index(value: Any, count: int, label: str) -> int:
    if type(value) is not int or value < 0 or value >= count:
        raise AnimationMetadataError(f"Invalid {label} index")
    return value


def _bounded_array(doc: dict, name: str) -> list:
    value = doc.get(name, [])
    if not isinstance(value, list) or len(value) > MAX_NODES:
        raise AnimationMetadataError(f"Invalid glTF {name} array")
    return value


def inspect_gltf_animations(doc: dict, source_format: str, warnings: tuple[str, ...] = ()) -> AnimationInspection:
    if not isinstance(doc, dict) or not isinstance(doc.get("asset"), dict) or doc["asset"].get("version") != "2.0":
        raise AnimationMetadataError("Expected glTF 2.0 JSON document")
    nodes = _bounded_array(doc, "nodes")
    accessors = _bounded_array(doc, "accessors")
    skins = _bounded_array(doc, "skins")
    animations = _bounded_array(doc, "animations")
    if len(animations) > MAX_ANIMATIONS:
        raise AnimationMetadataError("Too many animations")
    bone_indexes: list[int] = []
    for skin in skins:
        if not isinstance(skin, dict) or not isinstance(skin.get("joints"), list):
            raise AnimationMetadataError("Invalid glTF skin")
        for index in skin["joints"]:
            _int_index(index, len(nodes), "skin bone")
            if index not in bone_indexes:
                bone_indexes.append(index)
    parents: dict[int, int] = {}
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise AnimationMetadataError("Invalid glTF node")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise AnimationMetadataError("Invalid glTF children")
        for child in children:
            _int_index(child, len(nodes), "child")
            if child == idx:
                raise AnimationMetadataError("glTF skeleton node contains a self-cycle")
            if child in parents and parents[child] != idx:
                raise AnimationMetadataError("glTF node has multiple parents")
            parents[child] = idx
    for idx in range(len(nodes)):
        seen: set[int] = set()
        cursor = idx
        while cursor in parents:
            if cursor in seen:
                raise AnimationMetadataError("Cycle in glTF node hierarchy")
            seen.add(cursor)
            cursor = parents[cursor]
    names = tuple(str(nodes[idx].get("name") or f"node-{idx}")[:128] for idx in bone_indexes)
    structure = [(f"{idx}:{names[pos]}", str(parents[idx]) if idx in parents else None, ())
                 for pos, idx in enumerate(bone_indexes)]
    clips: list[ClipMetadata] = []
    extra_warnings = list(warnings)
    if not bone_indexes:
        extra_warnings.append("No declared skin joints; animation could be object or morph tracks")
    for ordinal, animation in enumerate(animations):
        if not isinstance(animation, dict):
            raise AnimationMetadataError("Invalid glTF animation")
        samplers = animation.get("samplers", [])
        channels = animation.get("channels", [])
        if not isinstance(samplers, list) or not isinstance(channels, list):
            raise AnimationMetadataError("Invalid glTF animation channels/samplers")
        earliest: float | None = None
        latest: float | None = None
        targets: set[str] = set()
        notes: list[str] = []
        for channel in channels:
            if not isinstance(channel, dict) or not isinstance(channel.get("target"), dict):
                raise AnimationMetadataError("Invalid glTF channel target")
            sampler = samplers[_int_index(channel.get("sampler"), len(samplers), "sampler")]
            if not isinstance(sampler, dict):
                raise AnimationMetadataError("Invalid glTF sampler")
            accessor = accessors[_int_index(sampler.get("input"), len(accessors), "sampler input")]
            _int_index(sampler.get("output"), len(accessors), "sampler output")
            if not isinstance(accessor, dict):
                raise AnimationMetadataError("Invalid glTF time accessor")
            target = channel["target"]
            if "node" in target:
                idx = _int_index(target["node"], len(nodes), "target node")
                targets.add(str(nodes[idx].get("name") or f"node-{idx}")[:128])
            else:
                notes.append("Animation channel without explicit target node")
            if target.get("path") not in {"translation", "rotation", "scale", "weights"}:
                raise AnimationMetadataError("Unsupported glTF animation path")
            mins, maxs = accessor.get("min"), accessor.get("max")
            if isinstance(mins, list) and isinstance(maxs, list) and len(mins) == len(maxs) == 1:
                minimum = _finite_number(str(mins[0]), "minimum animation time")
                maximum = _finite_number(str(maxs[0]), "maximum animation time")
                if maximum < minimum:
                    raise AnimationMetadataError("glTF animation time minimum exceeds maximum")
                earliest = minimum if earliest is None else min(earliest, minimum)
                latest = maximum if latest is None else max(latest, maximum)
            else:
                notes.append("Missing sampler time bounds; duration unknown")
        duration = round(max(0.0, latest - earliest), 6) if earliest is not None and latest is not None else None
        title = animation.get("name")
        if not isinstance(title, str) or not title.strip():
            title = f"animation-{ordinal:03d}"
        clips.append(ClipMetadata(ordinal, title[:128], duration, None, None, len(channels),
                                  tuple(sorted(targets)), tuple(sorted(set(notes)))))
    if not clips:
        extra_warnings.append("No animation clips declared")
    return AnimationInspection(source_format, "METADATA_EXTRACTED", _signature(structure), names,
                               tuple(clips), tuple(extra_warnings))


def inspect_animation_file(path: Path) -> AnimationInspection:
    """Read a single explicitly chosen file; never scan directories or resolve external URIs."""
    source = Path(path)
    ext = source.suffix.lower()
    if ext == ".bvh":
        return inspect_bvh(source)
    if ext == ".glb":
        try:
            report = inspect_glb(source)
            doc, _ = _parse_glb(source)
        except GLBInspectionError as exc:
            raise AnimationMetadataError(str(exc)) from exc
        return inspect_gltf_animations(doc, "glb", report.warnings)
    if ext == ".gltf":
        source = _regular_bounded(source, MAX_GLTF_JSON_BYTES)
        try:
            doc = json.loads(source.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError, OSError) as exc:
            raise AnimationMetadataError("Invalid glTF JSON") from exc
        return inspect_gltf_animations(doc, "gltf", ("External glTF buffers not loaded or verified",))
    if ext in {".fbx", ".uasset"}:
        _regular_bounded(source, MAX_BVH_BYTES * 8)
        reason = ("FBX content requires verified Blender import to extract reliable clips and skeletons"
                  if ext == ".fbx" else
                  "Unreal .uasset requires a supported Unreal import/export workflow and license review")
        return AnimationInspection(ext[1:], "REQUIRES_CONVERSION", None, (), (), (reason,))
    raise AnimationMetadataError("Unsupported animation source; choose BVH, GLB, glTF, FBX or uasset")
