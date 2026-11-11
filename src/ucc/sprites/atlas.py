"""Production-oriented RGBA sprite atlas assembly from *existing* PNG frames.

This is a real image operation, not an art-generation or Blender renderer.
Requires the optional free Pillow package. No placeholder art is provided.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from ucc.core.errors import UCCError, ValidationError
from .plan import RenderPlan


class AtlasError(UCCError):
    pass


@dataclass(frozen=True, slots=True)
class AtlasResult:
    sheet_files: tuple[str, ...]
    manifest: str
    frame_count: int


def _read_image(path: Path, width: int, height: int, allow_blank: bool):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise AtlasError("Pillow is required for atlas packing; install the optional 'sprites' extra") from exc
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise AtlasError(f"Not a PNG frame: {path.name}")
            if image.size != (width, height):
                raise AtlasError(f"Wrong size for {path.name}: {image.size} expected {(width, height)}")
            if image.mode == "RGB" or (image.mode == "P" and "transparency" not in image.info):
                raise AtlasError(f"Frame {path.name} has no alpha channel")
            if image.mode not in {"RGBA", "LA", "P"}:
                raise AtlasError(f"Unsupported PNG color mode {image.mode}")
            rgba = image.convert("RGBA")
            rgba.load()
            if not allow_blank and rgba.getchannel("A").getbbox() is None:
                raise AtlasError(f"Fully transparent frame: {path.name}")
            return rgba.copy()
    except (OSError, UnidentifiedImageError) as exc:
        raise AtlasError(f"Could not decode frame {path.name}: {exc}") from exc


def pack_frames(plan: RenderPlan, frame_root: Path, output_root: Path, *,
                max_sheet_side: int = 2048, allow_blank: bool = False,
                pivot_x: float = .5, pivot_y: float = .92) -> AtlasResult:
    """Pack existing PNGs to non-overwriting sprite sheets and JSON metadata.

    Source frames are never modified. All frames must match the plan dimensions.
    Incomplete exports fail before publishing any finished files.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise AtlasError("Pillow not installed; optional dependency required") from exc
    if not isinstance(plan, RenderPlan) or not plan.frames:
        raise ValidationError("Need a real nonempty RenderPlan")
    for label, value in (("pivot_x", pivot_x), ("pivot_y", pivot_y)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValidationError(f"{label} must be 0..1")
    if type(max_sheet_side) is not int or not 256 <= max_sheet_side <= 4096:
        raise ValidationError("max_sheet_side must be an integer between 256 and 4096")
    if plan.width > max_sheet_side or plan.height > max_sheet_side:
        raise AtlasError("A frame exceeds requested atlas dimensions")
    source_root = Path(frame_root).expanduser()
    target_root = Path(output_root).expanduser()
    if not source_root.is_dir() or source_root.is_symlink():
        raise AtlasError("Source frames directory missing or redirected")
    if target_root.is_symlink():
        raise AtlasError("Atlas output directory cannot be a symlink")
    source_root = source_root.resolve(strict=True)
    target_root.mkdir(parents=True, exist_ok=True)
    target_root = target_root.resolve(strict=True)
    columns = max_sheet_side // plan.width
    rows_per_page = max_sheet_side // plan.height
    capacity = columns * rows_per_page
    pages = math.ceil(len(plan.frames) / capacity)
    page_names = [f"sprite_sheet_{i:03d}.png" for i in range(pages)]
    manifest_name = "sprite_atlas.json"
    for name in (*page_names, manifest_name):
        if (target_root / name).exists():
            raise AtlasError(f"Destination already exists; refusing to overwrite: {name}")
    temp_dir = Path(tempfile.mkdtemp(prefix=".ucc-atlas-staging-", dir=target_root))
    records: list[dict[str, Any]] = []
    try:
        for page in range(pages):
            selected = plan.frames[page*capacity:(page+1)*capacity]
            page_rows = math.ceil(len(selected) / columns)
            atlas = Image.new("RGBA", (columns*plan.width, page_rows*plan.height), (0,0,0,0))
            for index, frame in enumerate(selected):
                relative = Path(frame.file_name)
                if relative.is_absolute() or ".." in relative.parts or "\\" in frame.file_name or ":" in frame.file_name:
                    raise AtlasError(f"Unsafe frame location: {frame.file_name}")
                src = source_root / relative
                # Reject symlinks in every component; do not chase out of source root.
                if src.is_symlink() or not src.resolve(strict=False).is_relative_to(source_root):
                    raise AtlasError(f"Source frame escaped authorized directory: {frame.file_name}")
                if not src.is_file():
                    raise AtlasError(f"Missing source frame: {frame.file_name}")
                rgba = _read_image(src, plan.width, plan.height, allow_blank)
                col, row = index % columns, index // columns
                x, y = col * plan.width, row * plan.height
                atlas.paste(rgba, (x, y))
                with src.open("rb") as source_bytes:
                    checksum = hashlib.file_digest(source_bytes, "sha256").hexdigest()
                records.append({
                    "clip": frame.clip, "direction_index": frame.direction_index,
                    "yaw_deg": frame.yaw_deg, "frame_index": frame.frame_index,
                    "timestamp_s": frame.timestamp_s, "sheet": page_names[page],
                    "rect": {"x": x, "y": y, "width": plan.width, "height": plan.height},
                    "pivot": {"x": round(pivot_x*plan.width, 4), "y": round(pivot_y*plan.height, 4)},
                    "source_frame": frame.file_name, "source_sha256": checksum,
                })
            atlas.save(temp_dir / page_names[page], format="PNG", compress_level=9)
            atlas.close()
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "source_geometry_verified": False,  # Only Blender + engine tests can claim this.
            "frame_count": len(records),
            "fps": plan.fps,
            "frame_resolution": {"width": plan.width, "height": plan.height},
            "angle_degrees": list(plan.camera.angles()),
            "alpha": "straight_rgba",
            "sheets": [{"file": f, "size_bytes": (temp_dir/f).stat().st_size}
                       for f in page_names],
            "frames": records,
        }
        (temp_dir / manifest_name).write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        promoted: list[Path] = []
        try:
            for name in (*page_names, manifest_name):
                dest = target_root / name
                if dest.exists():
                    raise AtlasError("Conflicting atlas output created during packing")
                os.replace(temp_dir / name, dest)
                promoted.append(dest)
        except Exception:
            for path in promoted:
                path.unlink(missing_ok=True)
            raise
        return AtlasResult(tuple(page_names), manifest_name, len(records))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
