"""Reviewed, explicit BVH source-to-target chain mappings (no fuzzy aliases).

This is input validation, not automatic retargeting. Ordered rows must follow
one directly connected source chain and one target deform chain in Blender.
"""
from __future__ import annotations

import hashlib
import json
import re

from ucc.core.errors import ValidationError

_BONE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z", re.ASCII)
MIN_BONES = 3
MAX_BONES = 8


def validate_review_mapping(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not MIN_BONES <= len(value) <= MAX_BONES:
        raise ValidationError("Reviewed mapping requires 3–8 explicitly ordered source → target pairs")
    output: list[dict[str, str]] = []
    sources: set[str] = set()
    targets: set[str] = set()
    for pair in value:
        if not isinstance(pair, dict) or set(pair) != {"source", "target"}:
            raise ValidationError("Each bone map needs only source and target")
        src, dst = pair["source"], pair["target"]
        if (type(src) is not str or type(dst) is not str or
                _BONE.fullmatch(src) is None or _BONE.fullmatch(dst) is None):
            raise ValidationError("Explicit bone names must be 1–128 safe ASCII characters")
        if src.casefold() in sources or dst.casefold() in targets:
            raise ValidationError("Explicit mapping cannot repeat source or target bones")
        sources.add(src.casefold())
        targets.add(dst.casefold())
        output.append({"source": src, "target": dst})
    return output


def parse_review_mapping(text: str) -> list[dict[str, str]]:
    """Accept one 'BVH_Bone -> MPFB_Bone' line per bone, top to leaf."""
    if type(text) is not str or len(text) > 2048:
        raise ValidationError("Explicit mapping text exceeds the permitted length")
    mapping = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("->")
        if len(fields) != 2:
            raise ValidationError("Use exactly 'source -> target' on each mapping line")
        mapping.append({"source": fields[0].strip(), "target": fields[1].strip()})
    return validate_review_mapping(mapping)


def review_mapping_sha256(value: object) -> str:
    pairs = validate_review_mapping(value)
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
