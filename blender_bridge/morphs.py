"""MPFB macro detail application and real evaluated-mesh evidence.

Blender-only calculations are run in subprocesses. No addon downloads, arbitrary
target files, mesh replacement, code injection, or invented geometry. The
normalized controls refer to MPFB's macro phenotype, NOT meters/kg.
"""
from __future__ import annotations

from hashlib import sha256
import math
import struct
from typing import Any

MACRO_KEYS = frozenset({"height", "muscle", "weight"})


class MorphEvidenceError(RuntimeError):
    """No trustworthy Blender/MPFB macro geometry evidence was produced."""


def check_macro_values(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != MACRO_KEYS:
        raise MorphEvidenceError("Exactly height, muscle and weight are required")
    out: dict[str, float] = {}
    for name in sorted(MACRO_KEYS):
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MorphEvidenceError(f"Invalid {name} macro control")
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise MorphEvidenceError(f"{name} macro value must be finite and within 0..1")
        out[name] = float(value)
    return out


def build_macro_info(target_service: Any, values: object) -> dict[str, Any]:
    requested = check_macro_values(values)
    default = target_service.get_default_macro_info_dict()
    if not isinstance(default, dict) or not MACRO_KEYS.issubset(default):
        raise MorphEvidenceError("TargetService did not supply MPFB macro defaults")
    # Preserve all other documented MPFB phenotype dimensions at their default.
    macro = dict(default)
    macro.update(requested)
    return macro


def inspect_applied_macro(bpy: Any, basemesh: Any, target_service: Any,
                          expected: object) -> dict[str, Any]:
    """Read real MPFB properties and evaluated mesh vertices (not fake metadata)."""
    values = check_macro_values(expected)
    if getattr(basemesh, "type", None) != "MESH" or len(basemesh.data.vertices) <= 100:
        raise MorphEvidenceError("Expected a substantial MPFB human basemesh")
    actual = target_service.get_macro_info_dict_from_basemesh(basemesh)
    if not isinstance(actual, dict):
        raise MorphEvidenceError("TargetService did not read phenotype from basemesh")
    observed = check_macro_values({k: actual.get(k) for k in MACRO_KEYS})
    for name, expected_value in values.items():
        if abs(observed[name] - expected_value) > 0.0001:
            raise MorphEvidenceError(f"MPFB {name} phenotype differed from saved slider")

    key_collection = getattr(basemesh.data, "shape_keys", None)
    keys = (getattr(key_collection, "key_blocks", ()) if key_collection else ())
    active = sum(1 for k in keys if getattr(k, "name", "") != "Basis"
                 and float(getattr(k, "value", 0)) > 0.0001)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    evaluated = basemesh.evaluated_get(dg)
    real_mesh = evaluated.to_mesh()
    if real_mesh is None:
        raise MorphEvidenceError("Blender did not evaluate MPFB body geometry")
    digest = sha256()
    count = 0
    try:
        for vertex in real_mesh.vertices:
            pos = tuple(float(v) for v in vertex.co)
            if any(not math.isfinite(v) or abs(v) > 1000000 for v in pos):
                raise MorphEvidenceError("Non-finite or extreme evaluated Blender geometry")
            # Quantization removes insignificant floating serialization noise.
            digest.update(struct.pack("<qqq", *(int(round(v * 10000)) for v in pos)))
            count += 1
    finally:
        evaluated.to_mesh_clear()
    if count <= 100:
        raise MorphEvidenceError("Insufficient evaluated mesh vertices")
    if active == 0:
        raise MorphEvidenceError("MPFB macro targets did not create active shape keys")
    return {
        "macro_parameters_observed": observed,
        "macro_evaluated_vertices": count,
        "macro_evaluated_sha256": digest.hexdigest(),
        "macro_active_shape_keys": active,
        "macro_shape_evaluated": True,
        "visual_deformation_verified": False,
        "engine_import_verified": False,
    }
