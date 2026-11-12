"""Bounded private render verification using stdlib PNG decoding; no Qt/Pillow."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import struct
from typing import Any
import zlib

from ucc.core.errors import ValidationError

WIDTH, HEIGHT = 256, 384
VIEWS = ("front", "side", "quarter")


def png_measurements(data: bytes) -> dict[str, Any]:
    if not 50 < len(data) <= 2*1024*1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValidationError("Invalid bounded private PNG")
    offset, compressed, header, ended = 8, bytearray(), False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValidationError("Truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset+4:offset+8]
        end = offset + 12 + length
        if end > len(data):
            raise ValidationError("PNG chunk exceeds file")
        payload = data[offset+8:offset+8+length]
        crc = struct.unpack_from(">I", data, offset+8+length)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValidationError("PNG checksum mismatch")
        if kind == b"IHDR":
            if header or offset != 8 or length != 13 or struct.unpack(">IIBBBBB", payload) != (WIDTH, HEIGHT, 8, 6, 0, 0, 0):
                raise ValidationError("Expected fixed-size noninterlaced RGBA8 render")
            header = True
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or end != len(data):
                raise ValidationError("Invalid PNG ending")
            ended = True
        offset = end
    if not header or not ended or not compressed:
        raise ValidationError("Incomplete private PNG")
    stride = WIDTH * 4
    expected = HEIGHT * (stride + 1)
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ValidationError("Invalid PNG compressed pixels") from exc
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValidationError("PNG decoded size/stream mismatch")
    previous, count = bytearray(stride), 0
    xmin, ymin, xmax, ymax = WIDTH, HEIGHT, -1, -1
    color_min, color_max = 255, 0
    for y in range(HEIGHT):
        start = y * (stride + 1)
        method = raw[start]
        row = bytearray(raw[start+1:start+1+stride])
        if method not in range(5):
            raise ValidationError("Unknown PNG filter")
        for i in range(stride):
            left, up, corner = row[i-4] if i >= 4 else 0, previous[i], previous[i-4] if i >= 4 else 0
            if method == 1: predictor = left
            elif method == 2: predictor = up
            elif method == 3: predictor = (left + up) // 2
            elif method == 4:
                p = left + up - corner
                distances = (abs(p-left), abs(p-up), abs(p-corner))
                predictor = (left, up, corner)[distances.index(min(distances))]
            else: predictor = 0
            row[i] = (row[i] + predictor) & 255
        for x in range(WIDTH):
            i = x*4
            if row[i+3] >= 128:
                count += 1
                xmin, xmax, ymin, ymax = min(xmin, x), max(xmax, x), min(ymin, y), max(ymax, y)
                brightness = sum(row[i:i+3]) // 3
                color_min, color_max = min(color_min, brightness), max(color_max, brightness)
        previous = row
    if (not 64 <= count < WIDTH*HEIGHT*.95 or color_max-color_min < 4 or
            xmin < 4 or ymin < 4 or xmax >= WIDTH-4 or ymax >= HEIGHT-4):
        raise ValidationError("Private image is blank, clipped or has insufficient surface contrast")
    return {"opaque_pixels": count, "opaque_bounds": [xmin, ymin, xmax, ymax]}


def verify_private_renders(folder: Path, raw: dict[str, Any], *, source_sha: str,
                            profile_sha: str, master_sha: str) -> str:
    summary = raw.get("private_review_renders")
    if (type(summary) is not dict or type(summary.get("image_count")) is not int or
            summary.get("image_count") != 15 or summary.get("animation_visual_quality_verified") is not False):
        raise ValidationError("Missing unapproved private render evidence")
    root = folder / "review_frames"
    if root.is_symlink() or not root.is_dir() or root.resolve().parent != folder.resolve():
        raise ValidationError("Private render directory is redirected")
    def read_record(record: Any, name: str, maximum: int) -> bytes:
        path = root / name
        if (type(record) is not dict or record.get("name") != name or path.is_symlink() or
                not path.is_file() or not 0 < path.stat().st_size <= maximum):
            raise ValidationError("Missing/redirected private render artifact")
        with path.open("rb") as stream:
            data = stream.read(maximum + 1)
        if (len(data) > maximum or type(record.get("bytes")) is not int or
                record["bytes"] != len(data) or record.get("sha256") != sha256(data).hexdigest()):
            raise ValidationError("Private render artifact SHA mismatch")
        return data
    payload = read_record(summary.get("manifest"), "manifest.json", 64*1024)
    read_record(summary.get("index"), "index.html", 64*1024)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate render manifest key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("Nonfinite render manifest number")
    try:
        manifest = json.loads(payload, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Invalid render manifest") from exc
    frames = raw["source_frame_count"]
    samples = [1, 1+(frames-1)//4, 1+(frames-1)//2, 1+3*(frames-1)//4, frames]
    if (type(manifest) is not dict or type(manifest.get("schema_version")) is not int or
            manifest["schema_version"] != 1 or manifest.get("method") != "CYCLES_CPU_EVALUATED_SKIN_CLAY_V1" or
            manifest.get("source_bvh_sha256") != source_sha or manifest.get("source_rest_profile_sha256") != profile_sha or
            manifest.get("source_master_sha256") != master_sha or
            manifest.get("review_action_sha256") != raw["visual_review_blend"]["sha256"] or
            manifest.get("conversion_convention") != "BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1" or
            type(manifest.get("source_frame_count")) is not int or manifest.get("source_frame_count") != frames or
            type(manifest.get("rendered_frames")) is not list or
            any(type(f) is not int for f in manifest["rendered_frames"]) or manifest["rendered_frames"] != samples or
            manifest.get("animation_visual_quality_verified") is not False):
        raise ValidationError("Private render provenance or sample coverage mismatch")
    records = manifest.get("images")
    if type(records) is not list or len(records) != 15:
        raise ValidationError("Incomplete private image set")
    signatures = {r["frame"]: r["evaluated_sha256"] for r in raw["full_timeline_frames"]}
    for record, (frame, view) in zip(records, ((f, v) for f in samples for v in VIEWS)):
        if (type(record) is not dict or type(record.get("frame")) is not int or
                record.get("frame") != frame or record.get("view") != view or
                record.get("width") != WIDTH or record.get("height") != HEIGHT or
                record.get("evaluated_sha256") != signatures[frame]):
            raise ValidationError("Render does not match measured frame/view/skin")
        data = read_record(record, f"frame_{frame:04}_{view}.png", 2*1024*1024)
        measured = png_measurements(data)
        if any(record.get(key) != value for key, value in measured.items()):
            raise ValidationError("Private PNG pixel evidence disagrees")
    if any(len({r["sha256"] for r in records if r["view"] == view}) < 2 for view in VIEWS):
        raise ValidationError("Rendered views do not show changing samples")
    return str(root / "index.html")
