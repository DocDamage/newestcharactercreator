"""Conservative, deterministic *name-only* candidate matching of humanoid rigs.

This does NOT calculate or apply bone rotations, rest-pose transforms, retargeted
motion, or animation validity. An exact named alias can still be physically
incompatible in orientation/scale; all reports require a future Blender review.

Supports Mixamo and common Unreal mannequin/Manny bone aliases. MPFB's
'game_engine' option is intentionally not assumed equivalent merely by name.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Sequence

SCHEMA_VERSION = 1
STATUS = "NAMING_CANDIDATES_ONLY_NOT_RETARGETED"


def _humanoid_profiles() -> dict[str, dict[str, str]]:
    base = ["hips", "spine.lower", "spine.mid", "spine.upper", "neck", "head"]
    mixamo = dict(zip(base, ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]))
    ue4 = dict(zip(base, ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head"]))
    ue5 = dict(zip(base, ["pelvis", "spine_01", "spine_03", "spine_05", "neck_01", "head"]))
    ue4["root"] = "root"
    ue5["root"] = "root"
    roles = ("clavicle", "upper_arm", "forearm", "hand", "thigh", "calf", "foot", "toe")
    mix_names = ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")
    ue_names = ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball")
    for side, full in (("L", "Left"), ("R", "Right")):
        for role, mix, ue in zip(roles, mix_names, ue_names):
            mixamo[f"{role}.{side}"] = f"{full}{mix}"
            ue4[f"{role}.{side}"] = f"{ue}_{side.lower()}"
            ue5[f"{role}.{side}"] = f"{ue}_{side.lower()}"
    return {"mixamo": mixamo, "unreal_ue4": ue4, "unreal_ue5": ue5}


PROFILES = _humanoid_profiles()
REQUIRED_ROLES = frozenset({"hips", "head", *(f"{role}.{side}" for side in "LR"
                                            for role in ("upper_arm", "forearm", "hand", "thigh", "calf", "foot"))})


class BoneMappingError(ValueError):
    """Input contains unsafe/ambiguous/unsupported bone names or profile hint."""


def _check_bones(names: Sequence[str]) -> tuple[str, ...]:
    if isinstance(names, (str, bytes)) or not isinstance(names, (tuple, list)):
        raise BoneMappingError("Bone names must be an explicit list")
    if not 1 <= len(names) <= 512:
        raise BoneMappingError("Expected 1..512 explicitly listed bones")
    output = []
    lowered = set()
    for name in names:
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise BoneMappingError("Bone name missing or too long")
        if any(ord(c) < 32 or c in "/\\" for c in name):
            raise BoneMappingError("Bone name contains unsafe control or path characters")
        key = name.casefold()
        if key in lowered:
            raise BoneMappingError("Duplicate bone names (case-insensitive)")
        output.append(name)
        lowered.add(key)
    return tuple(output)


def _normalize(name: str) -> str:
    """Strip only known Mixamo namespaces; never strip arbitrary prefixes."""
    first, sep, suffix = name.partition(":")
    if sep and first.casefold() in {"mixamorig", "mixamo"}:
        return suffix.casefold()
    return name.casefold()


def _role_names(names: tuple[str, ...], profile: str) -> dict[str, str]:
    lookup: dict[str, list[str]] = {}
    for name in names:
        lookup.setdefault(_normalize(name), []).append(name)
    # A bone listed with and without Mixamo's namespace is ambiguous.
    for alternatives in lookup.values():
        if len(alternatives) != 1:
            raise BoneMappingError("Ambiguous Mixamo aliases share one normalized bone name")
    matched: dict[str, str] = {}
    for role, canonical in PROFILES[profile].items():
        if canonical.casefold() in lookup:
            matched[role] = lookup[canonical.casefold()][0]
    return matched


def infer_profile(names: Sequence[str], *, hint: str | None = None) -> str | None:
    actual = _check_bones(names)
    if hint is not None:
        if hint not in PROFILES:
            raise BoneMappingError("Unknown rig profile hint")
        return hint
    normalized = {_normalize(x) for x in actual}
    # A 3-bone sample is insufficient to identify a rig family reliably.
    # Require bilateral arm names plus a substantial anatomy inventory.
    if {"hips", "head", "leftarm", "rightarm"}.issubset(normalized):
        if len(_role_names(actual, "mixamo")) >= 10:
            return "mixamo"
    if {"pelvis", "head", "upperarm_l", "upperarm_r"}.issubset(normalized):
        profile = "unreal_ue5" if "spine_05" in normalized else "unreal_ue4"
        if len(_role_names(actual, profile)) >= 10:
            return profile
    return None


def _fingerprint(names: tuple[str, ...]) -> str:
    # Fingerprint deliberately reflects the full supplied bone naming inventory.
    raw = json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class MappingCandidate:
    role: str
    source: str
    target: str
    evidence: str = "EXACT_DOCUMENTED_BONE_ALIAS_ONLY"

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "source": self.source, "target": self.target, "evidence": self.evidence}


@dataclass(frozen=True, slots=True)
class BoneMappingReport:
    source_profile: str | None
    target_profile: str | None
    source_fingerprint: str
    target_fingerprint: str
    candidates: tuple[MappingCandidate, ...]
    required_roles_unmapped: tuple[str, ...]
    ignored_source_bones: tuple[str, ...]
    ignored_target_bones: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": STATUS,
            "source_profile": self.source_profile,
            "target_profile": self.target_profile,
            "source_fingerprint": self.source_fingerprint,
            "target_fingerprint": self.target_fingerprint,
            "mapped_role_count": len(self.candidates),
            "required_roles_unmapped": list(self.required_roles_unmapped),
            "candidates": [c.to_dict() for c in self.candidates],
            "ignored_source_bones": list(self.ignored_source_bones),
            "ignored_target_bones": list(self.ignored_target_bones),
            "warnings": list(self.warnings),
            "retargeted": False,
            "preview_verified": False,
            "engine_validated": False,
            "can_execute_without_manual_review": False,
        }


def propose_mapping(source_names: Sequence[str], target_names: Sequence[str], *,
                    source_hint: str | None = None, target_hint: str | None = None) -> BoneMappingReport:
    """Suggest matching roles by exact profile aliases, with NO automatic retarget."""
    src = _check_bones(source_names)
    dst = _check_bones(target_names)
    source_profile = infer_profile(src, hint=source_hint)
    target_profile = infer_profile(dst, hint=target_hint)
    sr = _role_names(src, source_profile) if source_profile else {}
    dr = _role_names(dst, target_profile) if target_profile else {}
    roles = sorted(sr.keys() & dr.keys())
    mapped = tuple(MappingCandidate(role, sr[role], dr[role]) for role in roles)
    missing = tuple(sorted(REQUIRED_ROLES - set(roles)))
    warnings = ["Bone names alone do not establish compatible rest poses, bone axes, proportions, or motion quality",
                "Actual Blender retargeting, visual deformation review and destination-engine playback are required",
                "Asset-specific license must permit the intended engine export; this report does not evaluate licenses"]
    if source_profile is None:
        warnings.append("Source profile unidentified; no automatic name aliases applied")
    if target_profile is None:
        warnings.append("Target profile unidentified; no automatic name aliases applied")
    if missing:
        warnings.append("Required humanoid roles missing; manual mapping is required")
    if source_profile == target_profile and source_profile is not None:
        warnings.append("Even identically named skeletons can have incompatible transforms or bind poses")
    return BoneMappingReport(source_profile, target_profile, _fingerprint(src), _fingerprint(dst),
                             mapped, missing,
                             tuple(sorted(set(src) - {m.source for m in mapped})),
                             tuple(sorted(set(dst) - {m.target for m in mapped})),
                             tuple(warnings))
