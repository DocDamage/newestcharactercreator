"""Exact, fail-closed normalized MPFB body controls for worker JSON.

These are the three UCC macro sliders already persisted in project v1.
No claimed physical dimensions: height is a normalized MakeHuman phenotype
weight, not a height in meters. Rig/engine compatibility needs other checks.
"""
from __future__ import annotations

from typing import Mapping, Any

from ucc.core.errors import ValidationError
from ucc.core.models import MORPH_LIMITS, finite_number

MACRO_NAMES = frozenset({"height", "muscle", "weight"})
MACRO_TOLERANCE = 0.0001


def validate_macro_parameters(raw: object) -> dict[str, float]:
    """Require all three explicit safe macro values (no defaults or extra keys)."""
    if not isinstance(raw, dict) or set(raw) != MACRO_NAMES:
        raise ValidationError("Macro parameters require exactly height, muscle and weight")
    result = {}
    for key in sorted(MACRO_NAMES):
        result[key] = finite_number(raw[key], key, *MORPH_LIMITS[key])
    return result


def from_saved_parameters(parameters: tuple[tuple[str, float], ...]) -> dict[str, float]:
    """Read the already-saved project parameters; never infer dirty UI values."""
    return validate_macro_parameters(dict(parameters))


def verify_macro_report(expected: Mapping[str, float], report: Any, label: str) -> None:
    """Assert that Blender's TargetService read-back matches stored slider intent."""
    if not isinstance(report, dict) or set(report) != MACRO_NAMES:
        raise ValidationError(f"{label}: missing MPFB macro read-back")
    for name in MACRO_NAMES:
        actual = report[name]
        if isinstance(actual, bool) or not isinstance(actual, (float, int)):
            raise ValidationError(f"{label}: invalid {name} read-back")
        value = finite_number(actual, name, *MORPH_LIMITS[name])
        if abs(value - expected[name]) > MACRO_TOLERANCE:
            raise ValidationError(f"{label}: MPFB {name} does not match saved project")

def verify_evaluated_shape(
    expected: Mapping[str, float], created: dict[str, Any], reopened: dict[str, Any],
) -> dict[str, Any]:
    """Require matching actual MPFB macro read-backs AND evaluated geometry hashes.

    Success establishes that Blender created/reopened the requested body shape,
    not that the rig deforms correctly in animation or any engine importer works.
    """
    for label, details in (("creation", created), ("independent reopen", reopened)):
        if not isinstance(details, dict):
            raise ValidationError(f"{label}: missing Blender geometry evidence")
        verify_macro_report(expected, details.get("macro_parameters_observed"), label)
        count = details.get("macro_evaluated_vertices")
        active = details.get("macro_active_shape_keys")
        digest = details.get("macro_evaluated_sha256")
        if (type(count) is not int or count <= 100 or
                type(active) is not int or active < 1 or
                not isinstance(digest, str) or len(digest) != 64 or
                any(c not in "0123456789abcdef" for c in digest) or
                details.get("macro_shape_evaluated") is not True):
            raise ValidationError(f"{label}: missing evaluated Blender shape-key evidence")
        if details.get("visual_deformation_verified") is not False:
            raise ValidationError(f"{label}: unsupported deformation certification")
    if (created["macro_evaluated_vertices"] != reopened["macro_evaluated_vertices"] or
            created["macro_evaluated_sha256"] != reopened["macro_evaluated_sha256"]):
        raise ValidationError("Saved MPFB evaluated body shape changed during Blender reopen")
    return {
        "macro_parameters_observed": dict(expected),
        "macro_evaluated_vertices": reopened["macro_evaluated_vertices"],
        "macro_evaluated_sha256": reopened["macro_evaluated_sha256"],
        "macro_active_shape_keys": reopened["macro_active_shape_keys"],
        "morph_save_reopen_verified": True,
        "visual_deformation_verified": False,
        "engine_import_verified": False,
    }
