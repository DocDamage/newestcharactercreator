"""Versioned, immutable character metadata and strict boundary validation.

The authoritative 3D mesh is a separate Blender .blend file. This module does
not synthesize geometry and does not declare a model export-ready by itself.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from .anatomy import get_slot
from .errors import CompatibilityError, ValidationError
from .facial import validate_face_parameters

SCHEMA_VERSION = 1
MORPH_LIMITS = {"height": (0.0, 1.0), "muscle": (0.0, 1.0), "weight": (0.0, 1.0)}
KINDS = {"rigid_mesh", "skinned_mesh"}
PART_STATES = {"proposed", "geometry_validated"}
GEOMETRY_STATES = {"not_generated", "generated_unverified", "validated"}


def _text(value: Any, label: str, max_length: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValidationError(f"{label} must be nonempty text (max {max_length} chars)")
    if any(ord(c) < 32 for c in value):
        raise ValidationError(f"{label} has control characters")
    return value.strip()


def safe_relative_path(value: str, label: str) -> str:
    _text(value, label, 1024)
    if "\\" in value or ":" in value or value.startswith("/") or value.startswith("~"):
        raise ValidationError(f"{label} must be a relative POSIX-style project path")
    posix = PurePosixPath(value)
    if posix.is_absolute() or any(p in ("..", ".") for p in value.split("/")) or "//" in value:
        raise ValidationError(f"{label} cannot traverse directories")
    if PureWindowsPath(value).drive or not posix.name:
        raise ValidationError(f"{label} is not a safe file path")
    return str(posix)


def finite_number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValidationError(f"{label} must be a finite number")
    if not low <= value <= high:
        raise ValidationError(f"{label} must be between {low} and {high}")
    return float(value)


def _keys(raw: dict[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(raw, dict):
        raise ValidationError("Expected a JSON object")
    missing = required - raw.keys()
    extras = raw.keys() - (required | optional)
    if missing or extras:
        raise ValidationError(f"Invalid fields: missing={sorted(missing)}, unknown={sorted(extras)}")


@dataclass(frozen=True, slots=True)
class PartAsset:
    asset_id: str
    family_compatibility: tuple[str, ...]
    kind: str
    slot: str
    socket: str
    license_asset_id: str
    mesh: str
    rig_profile: str | None = None
    bind_pose_fingerprint: str | None = None
    source_verified: bool = False

    def __post_init__(self) -> None:
        _text(self.asset_id, "asset_id")
        _text(self.slot, "slot")
        _text(self.socket, "socket")
        _text(self.license_asset_id, "license_asset_id")
        if not self.family_compatibility or not isinstance(self.family_compatibility, tuple):
            raise ValidationError("family_compatibility requires a nonempty tuple")
        for family in self.family_compatibility:
            _text(family, "family")
            get_slot(family, self.slot)
        if self.kind not in KINDS:
            raise ValidationError(f"Invalid part kind {self.kind!r}")
        safe_relative_path(self.mesh, "mesh")
        if type(self.source_verified) is not bool:
            raise ValidationError("source_verified must be bool")
        if self.kind == "skinned_mesh" and not self.rig_profile:
            raise ValidationError("skinned part needs explicit rig_profile")
        if self.kind == "skinned_mesh" and not self.bind_pose_fingerprint:
            raise ValidationError("skinned part needs bind-pose fingerprint")

    def to_dict(self) -> dict[str, Any]:
        return {"asset_id": self.asset_id, "family_compatibility": list(self.family_compatibility),
                "kind": self.kind, "slot": self.slot, "socket": self.socket,
                "license_asset_id": self.license_asset_id, "mesh": self.mesh,
                "rig_profile": self.rig_profile, "bind_pose_fingerprint": self.bind_pose_fingerprint,
                "source_verified": self.source_verified}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PartAsset":
        fields = {"asset_id", "family_compatibility", "kind", "slot", "socket",
                  "license_asset_id", "mesh"}
        optional = {"rig_profile", "bind_pose_fingerprint", "source_verified"}
        _keys(data, fields, optional)
        if not isinstance(data["family_compatibility"], list):
            raise ValidationError("family_compatibility must be array")
        return cls(**(data | {"family_compatibility": tuple(data["family_compatibility"])}))


@dataclass(frozen=True, slots=True)
class PartInstance:
    part_id: str
    part_asset_id: str
    slot: str
    visible: bool = True
    status: str = "proposed"

    def __post_init__(self) -> None:
        for key in ("part_id", "part_asset_id", "slot"):
            _text(getattr(self, key), key)
        if type(self.visible) is not bool or self.status not in PART_STATES:
            raise ValidationError("Part visibility or verification state invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.part_id, "part_asset_id": self.part_asset_id,
                "slot": self.slot, "visible": self.visible, "status": self.status}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PartInstance":
        _keys(raw, {"id", "part_asset_id", "slot", "visible", "status"})
        return cls(part_id=raw["id"], part_asset_id=raw["part_asset_id"],
                   slot=raw["slot"], visible=raw["visible"], status=raw["status"])


@dataclass(frozen=True, slots=True)
class CharacterProject:
    project_id: str
    name: str
    family: str = "humanoid.v1"
    base_provider: str = "mpfb"
    master_blend: str | None = None
    geometry_state: str = "not_generated"
    rig_profile: str | None = None
    height_m: float = 1.75
    parameters: tuple[tuple[str, float], ...] = (("height", 0.5), ("muscle", 0.5), ("weight", 0.5))
    parts: tuple[PartInstance, ...] = ()
    animations: tuple[str, ...] = ()
    appearance: tuple[tuple[str, str], ...] = ()
    revision: int = 0
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = SCHEMA_VERSION
    facial_parameters: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in (1, 2):
            raise ValidationError("Unsupported schema version; do not overwrite this project")
        if (type(self.facial_parameters) is not tuple or any(
                type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
                for row in self.facial_parameters)):
            raise ValidationError("Facial parameters require immutable named values")
        if len(dict(self.facial_parameters)) != len(self.facial_parameters):
            raise ValidationError("Duplicate facial parameter")
        validate_face_parameters(dict(self.facial_parameters))
        if self.schema_version == 1 and self.facial_parameters:
            raise ValidationError("Facial parameters require an explicit version 2 project")
        _text(self.project_id, "project_id")
        _text(self.name, "name", 200)
        if self.family != "humanoid.v1":
            raise ValidationError("Only humanoid.v1 has a registered adapter at this stage")
        if self.base_provider != "mpfb":
            raise ValidationError("Only mpfb is currently a supported humanoid base provider")
        if self.geometry_state not in GEOMETRY_STATES:
            raise ValidationError("Unknown geometry_state")
        if self.geometry_state != "not_generated" and not self.master_blend:
            raise ValidationError("Generated geometry requires a master_blend reference")
        if self.master_blend is not None:
            if not self.master_blend.lower().endswith(".blend"):
                raise ValidationError("master_blend must end in .blend")
            safe_relative_path(self.master_blend, "master_blend")
        if self.geometry_state == "not_generated" and self.master_blend is not None:
            raise ValidationError("Not-generated project cannot claim a master model")
        if self.rig_profile is not None:
            _text(self.rig_profile, "rig_profile")
        finite_number(self.height_m, "height_m", 0.2, 5.0)
        if type(self.revision) is not int or self.revision < 0:
            raise ValidationError("revision must be nonnegative integer")
        _text(self.created_utc, "created_utc")
        seen: set[str] = set()
        for key, value in self.parameters:
            if key in seen or key not in MORPH_LIMITS:
                raise ValidationError(f"Duplicate or unsupported morph {key!r}")
            seen.add(key)
            finite_number(value, key, *MORPH_LIMITS[key])
        for part in self.parts:
            get_slot(self.family, part.slot)
        slot_names = [x.slot for x in self.parts]
        part_ids = [x.part_id for x in self.parts]
        if len(set(slot_names)) != len(slot_names) or len(set(part_ids)) != len(part_ids):
            raise ValidationError("Duplicate part slot or part ID")
        if any(x.status == "geometry_validated" for x in self.parts) and self.geometry_state != "validated":
            raise ValidationError("Cannot mark part geometry validated without validated master")
        if len(set(self.animations)) != len(self.animations) or any(not isinstance(x, str) or not x for x in self.animations):
            raise ValidationError("Animation identifiers must be distinct and nonempty")
        for k, v in self.appearance:
            _text(k, "appearance key")
            _text(v, "appearance value")

    @classmethod
    def new(cls, name: str) -> "CharacterProject":
        return cls(project_id=str(uuid4()), name=name)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version, "project_id": self.project_id, "name": self.name,
            "family": self.family, "base_provider": {"kind": self.base_provider},
            "master_blend": self.master_blend, "geometry_state": self.geometry_state,
            "rig_profile": self.rig_profile, "scale": {"unit": "meter", "height_m": self.height_m},
            "parameters": dict(self.parameters), "parts": [x.to_dict() for x in self.parts],
            "animations": list(self.animations), "appearance": dict(self.appearance),
            "revision": self.revision, "created_utc": self.created_utc,
        }
        if self.schema_version == 2:
            result["facial_parameters"] = dict(self.facial_parameters)
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CharacterProject":
        if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
                or raw["schema_version"] not in (1, 2)):
            raise ValidationError("Unsupported schema version; do not overwrite this project")
        version = raw["schema_version"]
        required = {"schema_version", "project_id", "name", "family", "base_provider",
                    "master_blend", "geometry_state", "rig_profile", "scale", "parameters",
                    "parts", "animations", "appearance", "revision", "created_utc"}
        if version == 2:
            required.add("facial_parameters")
        _keys(raw, required)
        face = validate_face_parameters(raw["facial_parameters"]) if version == 2 else {}
        provider = raw["base_provider"]
        scale = raw["scale"]
        _keys(provider, {"kind"})
        _keys(scale, {"unit", "height_m"})
        if scale["unit"] != "meter":
            raise ValidationError("Only meters supported by humanoid.v1")
        if not isinstance(raw["parameters"], dict) or not isinstance(raw["appearance"], dict):
            raise ValidationError("parameters/appearance must be objects")
        if not isinstance(raw["parts"], list) or not isinstance(raw["animations"], list):
            raise ValidationError("parts/animations must be arrays")
        return cls(project_id=raw["project_id"], name=raw["name"], family=raw["family"],
                   base_provider=provider["kind"], master_blend=raw["master_blend"],
                   geometry_state=raw["geometry_state"], rig_profile=raw["rig_profile"],
                   height_m=scale["height_m"], parameters=tuple(sorted(raw["parameters"].items())),
                   parts=tuple(PartInstance.from_dict(p) for p in raw["parts"]),
                   animations=tuple(raw["animations"]),
                   appearance=tuple(sorted(raw["appearance"].items())),
                   revision=raw["revision"], created_utc=raw["created_utc"], schema_version=version,
                   facial_parameters=tuple(sorted(face.items())))

    def export_readiness(self) -> tuple[str, ...]:
        """Metadata checks only; engine import must additionally be tested."""
        errors: list[str] = []
        if self.geometry_state != "validated":
            errors.append("Master geometry has not passed a real Blender inspection")
        if not self.rig_profile:
            errors.append("Rig profile not validated")
        if any(p.status != "geometry_validated" for p in self.parts):
            errors.append("At least one attached part is only a proposal")
        if not self.animations:
            errors.append("No verified animation references")
        return tuple(errors)
