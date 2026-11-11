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
