"""SHA-bound source BONE rest metadata intake; never BVH channel-axis inference.

The descriptor is validated and retained as diagnostic evidence only. Its bone
axes must not silently replace the axes of standard BVH rotation channels.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import struct
from typing import Any

from ucc.core.errors import ValidationError
from .review_mapping import validate_review_mapping

MAX_PROFILE_BYTES = 128 * 1024
FRAME_SEMANTICS = "BONE_REST_AXES_ONLY"
MATRIX_LAYOUT = "ROW_MAJOR_LOCAL_TO_BVH_REST"
CONVERSION_CONVENTION = "BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1"


class SourceRestProfileError(ValidationError):
    """Selected descriptor is unsafe, inconsistent, or bound to another BVH."""


def is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def rotation_sha256(rotation: list[list[float]]) -> str:
    digest = sha256()
    for row in rotation:
        for value in row:
            digest.update(struct.pack("<q", round(value * 1_000_000)))
    return digest.hexdigest()


def _vector(value: Any) -> list[float]:
    if (type(value) is not list or len(value) != 3 or
            any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6 for v in value)):
        raise SourceRestProfileError("Rest coordinates must be three finite source-unit numbers")
    return [float(v) for v in value]


def validate_source_rest_profile(raw: Any, source_sha: str, axis: str,
                                 mapping: object) -> dict[str, Any]:
    pairs = validate_review_mapping(mapping)
    keys = {"schema_version", "source_bvh_sha256", "axis_profile", "frame_semantics",
            "matrix_layout", "provenance", "joint_frames"}
    if type(raw) is not dict or set(raw) != keys:
        raise SourceRestProfileError("Source rest profile fields do not match schema v1")
    if (type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or
            raw["frame_semantics"] != FRAME_SEMANTICS or raw["matrix_layout"] != MATRIX_LAYOUT):
        raise SourceRestProfileError("Unsupported source rest-frame version or convention")
    if (not is_sha256(source_sha) or raw["source_bvh_sha256"] != source_sha or
            axis not in {"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"} or raw["axis_profile"] != axis):
        raise SourceRestProfileError("Source rest profile BVH SHA-256 or axis binding mismatch")
    provenance = raw["provenance"]
    if (type(provenance) is not dict or set(provenance) != {"provider", "method", "reference"} or
            any(type(v) is not str or not v.strip() or len(v) > 512 or
                any(ord(c) < 32 for c in v) for v in provenance.values())):
        raise SourceRestProfileError("Rest metadata needs explicit provider, method and reference")
    frames = raw["joint_frames"]
    if type(frames) is not list or len(frames) != len(pairs):
        raise SourceRestProfileError("Exactly one source rest frame per reviewed pair is required")
    previous: set[str] = set()
    normalized = []
    for i, (frame, pair) in enumerate(zip(frames, pairs)):
        if type(frame) is not dict or set(frame) != {"source", "parent", "head", "tail", "rotation"}:
            raise SourceRestProfileError("Per-joint rest frame has unsupported fields")
        name, parent = frame["source"], frame["parent"]
        if (name != pair["source"] or
                (parent is not None if i == 0 else type(parent) is not str or parent not in previous)):
            raise SourceRestProfileError("Rest names/order/parents differ from reviewed source mapping")
        head, tail = _vector(frame["head"]), _vector(frame["tail"])
        matrix = frame["rotation"]
        if type(matrix) is not list or len(matrix) != 3:
            raise SourceRestProfileError("Rest rotation must be a row-major 3x3 matrix")
        matrix = [_vector(row) for row in matrix]
        columns = [[matrix[r][c] for r in range(3)] for c in range(3)]
        if any(abs(sum(a*b for a, b in zip(columns[i], columns[j])) - float(i == j)) > 1e-5
               for i in range(3) for j in range(3)):
            raise SourceRestProfileError("Source rest axes are scaled, sheared or non-orthogonal")
        a, b, c = matrix
        determinant = (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0])
                       + a[2]*(b[0]*c[1]-b[1]*c[0]))
        if abs(determinant - 1) > 1e-5:
            raise SourceRestProfileError("Source rest axes must be right-handed proper rotations")
        direction = [t-h for t, h in zip(tail, head)]
        length = math.sqrt(sum(v*v for v in direction))
        if not 1e-7 < length < 1e6 or sum(v*y for v, y in zip(direction, columns[1])) / length < math.cos(math.radians(1)):
            raise SourceRestProfileError("Source rest local Y must follow its non-degenerate head-to-tail direction")
        previous.add(name)
        normalized.append({"source": name, "parent": parent, "head": head,
                           "tail": tail, "rotation": matrix})
    return {**raw, "joint_frames": normalized}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceRestProfileError("Duplicate source rest JSON key: " + key[:128])
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise SourceRestProfileError("Nonfinite JSON constant in source rest profile: " + value)


def read_source_rest_profile(path: Path, source_sha: str, axis: str,
                             mapping: object) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".json":
        raise SourceRestProfileError("Select a regular local source rest-frame JSON file")
    try:
        if not 0 < path.stat().st_size <= MAX_PROFILE_BYTES:
            raise SourceRestProfileError("Source rest profile exceeds the 128 KiB limit")
        with path.open("rb") as stream:
            payload = stream.read(MAX_PROFILE_BYTES + 1)
        if len(payload) > MAX_PROFILE_BYTES:
            raise SourceRestProfileError("Source rest profile grew beyond the 128 KiB limit")
        raw = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                         parse_constant=_invalid_constant)
        return validate_source_rest_profile(raw, source_sha, axis, mapping), sha256(payload).hexdigest()
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise SourceRestProfileError("Cannot read bounded source rest-frame JSON: " + str(exc)) from exc
