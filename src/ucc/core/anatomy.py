"""Semantic humanoid attachment slots, independent of MPFB bone names.

These are *metadata* contracts, not a claim that an MPFB mesh has these seams.
Additional character families will register their own definitions.
"""
from __future__ import annotations
from dataclasses import dataclass

from .errors import CompatibilityError


@dataclass(frozen=True, slots=True)
class Slot:
    name: str
    socket: str
    allowed_kinds: frozenset[str]
    parent: str | None = None
    family: str = "humanoid.v1"


def _build_humanoid() -> dict[str, Slot]:
    items: dict[str, Slot] = {}

    def put(name: str, parent: str | None, *kinds: str) -> None:
        if name in items:
            raise RuntimeError(f"Duplicate slot {name}")
        items[name] = Slot(name, name if parent is None else f"{parent}::{name}",
                           frozenset(kinds), parent)

    put("torso", None, "skinned_mesh")
    put("neck", "torso", "skinned_mesh", "rigid_mesh")
    put("head", "neck", "skinned_mesh", "rigid_mesh")
    for center in ("nose", "mouth", "jaw", "teeth", "hair", "brows"):
        put(center, "head", "rigid_mesh", "skinned_mesh")
    for side in ("L", "R"):
        for face in ("eye", "ear", "eyelash", "horn"):
            put(f"{face}.{side}", "head", "rigid_mesh", "skinned_mesh")
        previous = "torso"
        for arm in ("shoulder", "upper_arm", "forearm", "hand"):
            name = f"{arm}.{side}"
            put(name, previous, "skinned_mesh", "rigid_mesh")
            previous = name
        for finger in ("thumb", "index", "middle", "ring", "little"):
            put(f"finger.{finger}.{side}", f"hand.{side}", "skinned_mesh", "rigid_mesh")
        previous = "torso"
        for leg in ("hip", "thigh", "calf", "foot"):
            name = f"{leg}.{side}"
            put(name, previous, "skinned_mesh", "rigid_mesh")
            previous = name
        for toe in ("big", "second", "middle", "fourth", "little"):
            put(f"toe.{toe}.{side}", f"foot.{side}", "skinned_mesh", "rigid_mesh")
        put(f"wing.{side}", "torso", "rigid_mesh", "skinned_mesh")
        put(f"weapon.{side}", f"hand.{side}", "rigid_mesh")
        put(f"shoe.{side}", f"foot.{side}", "rigid_mesh", "skinned_mesh")
    for extra in ("cape", "tail", "backpack"):
        put(extra, "torso", "rigid_mesh", "skinned_mesh")
    return items


HUMANOID_SLOTS = _build_humanoid()


def get_slot(family: str, name: str) -> Slot:
    if family != "humanoid.v1":
        raise CompatibilityError(f"Character family {family!r} has no registered slot adapter")
    if name not in HUMANOID_SLOTS:
        raise CompatibilityError(f"Unknown {family} slot: {name!r}")
    return HUMANOID_SLOTS[name]


def slot_catalog(family: str = "humanoid.v1") -> tuple[Slot, ...]:
    if family != "humanoid.v1":
        raise CompatibilityError(f"Character family {family!r} is not implemented")
    return tuple(HUMANOID_SLOTS.values())
