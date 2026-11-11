"""Reversible metadata edits. No operation mutates the Blender master."""
from __future__ import annotations
from dataclasses import replace
from typing import Mapping
from uuid import uuid4

from .anatomy import get_slot
from .errors import CompatibilityError, ValidationError
from .models import CharacterProject, MORPH_LIMITS, PartAsset, PartInstance, finite_number


class CharacterSession:
    """A bounded in-memory undo/redo stack for metadata editing.

    Each committed edit advances its metadata revision. Undo/redo also advance
    revisions so optimistic concurrency cannot accept an old snapshot.
    """
    def __init__(self, project: CharacterProject, assets: Mapping[str, PartAsset] | None = None,
                 history_limit: int = 100):
        if history_limit < 1:
            raise ValidationError("history_limit must be >= 1")
        self._project = project
        self._assets = dict(assets or {})
        self._undo: list[CharacterProject] = []
        self._redo: list[CharacterProject] = []
        self._history_limit = history_limit

    @property
    def project(self) -> CharacterProject:
        return self._project

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def register_asset(self, asset: PartAsset) -> None:
        current = self._assets.get(asset.asset_id)
        if current is not None and current != asset:
            raise ValidationError(f"Asset ID collision: {asset.asset_id}")
        self._assets[asset.asset_id] = asset

    def _commit(self, changed: CharacterProject) -> CharacterProject:
        if changed == self._project:
            return self._project
        self._undo.append(self._project)
        self._undo = self._undo[-self._history_limit:]
        self._redo.clear()
        self._project = replace(changed, revision=self._project.revision + 1)
        return self._project

    def set_morph(self, name: str, value: float) -> CharacterProject:
        if name not in MORPH_LIMITS:
            raise ValidationError(f"Unsupported morph {name!r}; verify MPFB mapping first")
        value = finite_number(value, name, *MORPH_LIMITS[name])
        values = dict(self._project.parameters)
        values[name] = value
        return self._commit(replace(self._project, parameters=tuple(sorted(values.items()))))

    def rename(self, value: str) -> CharacterProject:
        return self._commit(replace(self._project, name=value))

    def propose_part(self, asset_id: str) -> CharacterProject:
        asset = self._assets.get(asset_id)
        if asset is None:
            raise CompatibilityError(f"Unknown asset: {asset_id}")
        if self._project.family not in asset.family_compatibility:
            raise CompatibilityError("Asset does not support this character family")
        slot = get_slot(self._project.family, asset.slot)
        if asset.kind not in slot.allowed_kinds or asset.socket != slot.socket:
            raise CompatibilityError("Declared attachment kind/socket does not match slot")
        if asset.kind == "skinned_mesh" and asset.rig_profile != self._project.rig_profile:
            raise CompatibilityError("Skin rig/rest profile mismatch")
        if not asset.source_verified:
            raise CompatibilityError("Asset source not verified; cannot propose attachment")
        proposal = PartInstance(part_id=str(uuid4()), part_asset_id=asset.asset_id,
                                slot=asset.slot, visible=True, status="proposed")
        replaced = tuple(p for p in self._project.parts if p.slot != asset.slot) + (proposal,)
        return self._commit(replace(self._project, parts=tuple(sorted(replaced, key=lambda p: p.slot))))

    def remove_part(self, slot: str) -> CharacterProject:
        get_slot(self._project.family, slot)
        remaining = tuple(p for p in self._project.parts if p.slot != slot)
        if len(remaining) == len(self._project.parts):
            raise ValidationError(f"No part at slot {slot}")
        return self._commit(replace(self._project, parts=remaining))

    def undo(self) -> CharacterProject:
        if not self._undo:
            raise ValidationError("Nothing to undo")
        previous = self._undo.pop()
        self._redo.append(self._project)
        self._project = replace(previous, revision=self._project.revision + 1)
        return self._project

    def redo(self) -> CharacterProject:
        if not self._redo:
            raise ValidationError("Nothing to redo")
        next_snapshot = self._redo.pop()
        self._undo.append(self._project)
        self._project = replace(next_snapshot, revision=self._project.revision + 1)
        return self._project
