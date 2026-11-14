"""Explicit SHA-bound native body map; no aliases or inferred anatomical roles."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from ucc.core.errors import ValidationError
from .source_rest_frames import is_sha256

CONVENTION = "NATIVE_ANATOMICAL_REFERENCE_V1"
ROOT_POLICIES = {"ARMATURE_ORIGIN_DISPLACEMENT_V1", "SOURCE_HIP_MIDPOINT_V1"}
SKIN_POLICIES = {"MASTER_MODIFIERS_V1", "BOUND_CORRECTIVE_SMOOTH_V1"}
LANDMARKS = {"left_hip","right_hip","head","left_hand","right_hand","left_foot","right_foot"}
MAX_PROFILE_BYTES = 64*1024


def validate_native_profile(data: Any, source_sha: str, snapshot_sha: str, master_sha: str) -> dict:
    if (type(data) is not dict or set(data)-{"root_motion_policy","skin_deformation_policy"} != {"schema_version","convention","source_sha256",
            "snapshot_sha256","master_sha256","landmarks","pairs"} or
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or
            data["convention"] != CONVENTION):
        raise ValidationError("Invalid native body map schema/convention")
    if "root_motion_policy" in data and (type(data["root_motion_policy"]) is not str or data["root_motion_policy"] not in ROOT_POLICIES):
        raise ValidationError("Invalid explicit native root-motion policy")
    if "skin_deformation_policy" in data and (type(data["skin_deformation_policy"]) is not str or data["skin_deformation_policy"] not in SKIN_POLICIES):
        raise ValidationError("Invalid explicit native skin-deformation policy")
    for key,value in (("source_sha256",source_sha),("snapshot_sha256",snapshot_sha),("master_sha256",master_sha)):
        if not is_sha256(value) or data[key] != value:
            raise ValidationError("Native body map source/snapshot/master SHA binding differs")
    def name(v):
        return type(v) is str and 0 < len(v) <= 128 and all(c.isprintable() for c in v)
    pairs = data["pairs"]
    if type(pairs) is not list or not 15 <= len(pairs) <= 64:
        raise ValidationError("Explicit native body mapping needs 15–64 joints")
    sources,targets = set(),set()
    exact = {}
    for index,row in enumerate(pairs):
        if (type(row) is not dict or set(row) != {"source","target","source_tip","target_tip","secondary"} or
                not name(row["source"]) or not name(row["target"]) or row["target"].startswith("@") or
                row["source"].casefold() in sources or row["target"].casefold() in targets or
                any(v is not None and not name(v) for v in (row["source_tip"],row["target_tip"]))):
            raise ValidationError("Native map names/tips must be explicit and unique")
        if index == 0:
            if row["source"] != "@ARMATURE" or row["secondary"] != "BODY" or row["source_tip"] is not None or row["target_tip"] is not None:
                raise ValidationError("First native mapping must be the armature-object root")
        elif row["source"].startswith("@") or type(row["secondary"]) is not str or row["secondary"] not in {"FORWARD","UP"}:
            raise ValidationError("Native body map requires explicit anatomical secondary axes")
        sources.add(row["source"].casefold());targets.add(row["target"].casefold())
        exact[row["source"]] = row["target"]
    landmarks = data["landmarks"]
    if type(landmarks) is not dict or set(landmarks) != LANDMARKS:
        raise ValidationError("Native body map needs all seven explicit anatomical landmarks")
    for row in landmarks.values():
        if (type(row) is not dict or set(row) != {"source","target"} or
                not name(row["source"]) or not name(row["target"]) or row["source"] == "@ARMATURE" or
                exact.get(row["source"]) != row["target"]):
            raise ValidationError("Native anatomical landmark differs from explicit pairs")
    if len({r["source"] for r in landmarks.values()}) != len(LANDMARKS):
        raise ValidationError("Native anatomical landmarks must be distinct")
    return data


def read_native_profile(path: Path, source_sha: str, snapshot_sha: str, master_sha: str) -> tuple[dict,str]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_PROFILE_BYTES:
        raise ValidationError("Choose a bounded regular native body mapping JSON")
    with path.open("rb") as stream:
        payload = stream.read(MAX_PROFILE_BYTES+1)
    if len(payload) > MAX_PROFILE_BYTES:
        raise ValidationError("Native body map exceeds size limit")
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result: raise ValueError("Duplicate native body map key")
            result[key] = value
        return result
    def nonfinite(value): raise ValueError("Nonfinite native map value")
    try:
        data = json.loads(payload,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ValidationError("Invalid native body map JSON") from exc
    return validate_native_profile(data,source_sha,snapshot_sha,master_sha),sha256(payload).hexdigest()
