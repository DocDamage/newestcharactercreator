"""Independent staged-sidecar validation against actual parsed BVH rest data.

Bone rest axes are retained as evidence only; they are NOT implicitly the axes
of BVH XYZ channels. This module never loads a source rig or executes metadata.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re
import struct
from typing import Any

from blender_bridge.rest_calibration import dot, unit, validate_rotation


class SourceRestIntakeError(RuntimeError):
    """The SHA-bound descriptor cannot establish consistent source rest metadata."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            raise SourceRestIntakeError("Duplicate rest JSON key: " + key[:128])
        output[key] = value
    return output


def _vector(value: Any) -> tuple[float, float, float]:
    if (type(value) is not list or len(value) != 3 or
            any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e6 for v in value)):
        raise SourceRestIntakeError("Source rest vectors require three finite source-unit values")
    return tuple(float(v) for v in value)


def _invalid_constant(value: str) -> Any:
    raise SourceRestIntakeError("Nonfinite source rest JSON constant: " + value)


def inspect_source_rest_profile(path: Path, expected_sha: str, motion: Any,
                                source_sha: str, axis: str,
                                pairs: list[dict[str, str]]) -> dict[str, Any]:
    if (path.is_symlink() or not path.is_file() or path.suffix.lower() != ".json" or
            not 0 < path.stat().st_size <= 128 * 1024):
        raise SourceRestIntakeError("Expected a bounded regular staged source rest JSON")
    with path.open("rb") as stream:
        payload = stream.read(128 * 1024 + 1)
    if len(payload) > 128 * 1024 or sha256(payload).hexdigest() != expected_sha:
        raise SourceRestIntakeError("Staged source rest profile SHA-256 mismatch")
    try:
        raw = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=_object,
                         parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SourceRestIntakeError("Invalid source rest JSON") from exc
    if type(raw) is not dict or set(raw) != {
        "schema_version", "source_bvh_sha256", "axis_profile", "frame_semantics",
        "matrix_layout", "provenance", "joint_frames"
    }:
        raise SourceRestIntakeError("Source rest schema fields differ from v1")
    if (type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or
            raw["source_bvh_sha256"] != source_sha or
            axis not in {"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"} or raw["axis_profile"] != axis or
            raw["frame_semantics"] != "BONE_REST_AXES_ONLY" or
            raw["matrix_layout"] != "ROW_MAJOR_LOCAL_TO_BVH_REST"):
        raise SourceRestIntakeError("Rest profile source SHA, version, axes or convention mismatch")
    provenance = raw["provenance"]
    if (type(provenance) is not dict or set(provenance) != {"provider", "method", "reference"} or
            any(type(v) is not str or not v.strip() or len(v) > 512 or
                any(ord(c) < 32 for c in v) for v in provenance.values())):
        raise SourceRestIntakeError("Missing source-rest provenance declaration")
    rows = raw["joint_frames"]
    if type(rows) is not list or not 3 <= len(rows) == len(pairs) <= 64:
        raise SourceRestIntakeError("One source rest frame is required per mapped bone")
    heads = {}
    for name in motion.source_bones:
        key = name.casefold()
        parent = motion.parents[key]
        origin = heads[parent] if parent is not None else (0., 0., 0.)
        heads[key] = tuple(a+b for a, b in zip(origin, motion.offsets[key]))
    evidence = []
    seen = set()
    actual_names = set(motion.source_bones)
    for index, (row, pair) in enumerate(zip(rows, pairs)):
        if type(row) is not dict or set(row) != {"source", "parent", "head", "tail", "rotation"}:
            raise SourceRestIntakeError("Malformed per-joint source rest record")
        name, parent = row["source"], row["parent"]
        if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name) is None or
                name != pair["source"] or name not in actual_names or name.casefold() in seen or
                (parent is not None if index == 0 else
                 type(parent) is not str or parent.casefold() not in seen) or
                motion.parents[name.casefold()] != (parent.casefold() if parent is not None else None)):
            raise SourceRestIntakeError("Source rest name or parent differs from actual BVH")
        head, tail = _vector(row["head"]), _vector(row["tail"])
        rotation = row["rotation"]
        if type(rotation) is not list or len(rotation) != 3:
            raise SourceRestIntakeError("Expected source rest 3x3 matrix")
        rotation = tuple(_vector(r) for r in rotation)
        validate_rotation(rotation)  # strict SO(3); no projection of supplied frames
        direction = unit(tuple(b-a for a, b in zip(head, tail)))
        local_y = unit(tuple(rotation[i][1] for i in range(3)))
        axis_error = math.degrees(math.acos(max(-1., min(1., dot(direction, local_y)))))
        if axis_error > 1.:
            raise SourceRestIntakeError("Source rest local Y disagrees with head-to-tail direction")
        head_error = math.dist(head, heads[name.casefold()])
        if head_error > 1e-5:
            raise SourceRestIntakeError("Source rest head differs from actual BVH zero-channel origin: " + name)
        end = motion.end_site_offsets.get(name.casefold())
        tail_error = math.dist(tail, tuple(a+b for a, b in zip(heads[name.casefold()], end))) if end else None
        if tail_error is not None and tail_error > 1e-5:
            raise SourceRestIntakeError("Source rest terminal tail differs from actual BVH End Site: " + name)
        digest = sha256()
        for line in rotation:
            for value in line:
                digest.update(struct.pack("<q", round(value * 1_000_000)))
        evidence.append({"source": name, "parent": parent,
                         "rest_rotation_sha256": digest.hexdigest(),
                         "rest_head_error_local": head_error,
                         "terminal_tail_error_local": tail_error,
                         "tail_axis_error_degrees": axis_error})
        seen.add(name.casefold())
    return {"schema_version": 1, "profile_sha256": expected_sha,
            "source_bvh_sha256": source_sha, "axis_profile": axis,
            "joint_count": len(rows), "joint_frames": evidence,
            "validation_only": True, "source_channel_interpretation_changed": False,
            "source_roll_independently_verified": False}
