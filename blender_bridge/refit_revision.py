"""Apply normalized MPFB phenotype to a staged *copy* of an existing master.

Runs exclusively inside the isolated Blender subprocess. It refuses ambiguous
human/armature structures, lost bone links/weights, a no-op body shape, and
non-reopenable output. A later independent worker must still inspect this file.
Neither this method nor its tests certify animation deformation or game import.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
import struct
from typing import Any

from blender_bridge.morphs import check_macro_values, inspect_applied_macro


class RefitError(RuntimeError):
    """Existing Blender master cannot safely be morphed/refitted."""


def rig_fingerprint(bpy: Any, human: Any) -> dict[str, Any]:
    """Capture actual Blender rig binding, bone names and per-vertex weights."""
    rigs = [obj for obj in bpy.data.objects
            if getattr(obj, "type", "") == "ARMATURE"]
    if len(rigs) != 1 or len(rigs[0].data.bones) < 5:
        raise RefitError("Exactly one substantial armature is required")
    rig = rigs[0]
    modifiers = [mod for mod in human.modifiers
                 if mod.type == "ARMATURE" and mod.object == rig]
    if not modifiers:
        raise RefitError("Humanoid has no armature modifier linked to its rig")
    if human.parent is not None and human.parent != rig:
        raise RefitError("Humanoid has an unexpected non-rig parent")

    groups = {g.index: g.name for g in human.vertex_groups}
    bones = tuple(sorted(b.name for b in rig.data.bones))
    linked = sorted(set(groups.values()).intersection(bones))
    if len(linked) < 5:
        raise RefitError("Too few bone-matching weight groups")
    hasher = sha256()
    weighted_vertices = 0
    for vert in human.data.vertices:
        memberships = sorted(vert.groups, key=lambda item: item.group)
        if any(group.group not in groups for group in memberships):
            raise RefitError("Mesh contains an unknown vertex group index")
        influences = [(groups[g.group], float(g.weight)) for g in memberships
                      if g.weight > 0.000001 and groups[g.group] in bones]
        if influences:
            weighted_vertices += 1
        for name, weight in sorted(influences):
            if not math.isfinite(weight) or not 0.0 <= weight <= 1.00001:
                raise RefitError("Invalid nonfinite or negative bone weight")
            hasher.update(struct.pack("<I", vert.index))
            hasher.update(name.encode("utf-8") + b"\x00")
            hasher.update(struct.pack("<I", round(weight * 1_000_000)))
    if weighted_vertices <= 100:
        raise RefitError("No substantial vertex skin weights were detected")

    rest_hasher = sha256()
    for bone in sorted(rig.data.bones, key=lambda b: b.name):
        rest_hasher.update(bone.name.encode("utf-8") + b"\x00")
        for vertex in (bone.head_local, bone.tail_local):
            for pos in vertex:
                num = float(pos)
                if not math.isfinite(num):
                    raise RefitError("Rig rest pose contains nonfinite bone coordinates")
                rest_hasher.update(struct.pack("<q", round(num * 1_000_000)))
    return {
        "bone_count": len(bones),
        "bone_names": list(bones),
        "bone_weight_groups": linked,
        "weighted_vertices": weighted_vertices,
        "weight_sha256": hasher.hexdigest(),
        "rig_rest_sha256": rest_hasher.hexdigest(),
        "armature_modifier_count": len(modifiers),
        "rig_binding_verified": True,
        "animation_deformation_verified": False,
    }


def apply_body_revision(
    bpy: Any, source: Path, destination: Path, requested: object,
    human_service: Any, target_service: Any, properties: Any,
) -> dict[str, Any]:
    """Open, mutate only in memory, refit existing rig, and save a NEW .blend."""
    values = check_macro_values(requested)
    if (source.is_symlink() or not source.is_file() or
            source.suffix.lower() != ".blend" or
            destination.exists() or destination.is_symlink() or
            destination.suffix.lower() != ".blend"):
        raise RefitError("Expected a source .blend and a new, unused .blend destination")
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    large = [obj for obj in bpy.data.objects
             if obj.type == "MESH" and len(obj.data.vertices) > 100]
    if len(large) != 1:
        raise RefitError("Existing master requires exactly one substantial MPFB basemesh")
    human = large[0]
    if properties.get_value("is_human_project", entity_reference=human) is not True:
        raise RefitError("Existing Blender mesh is not a registered MPFB human")
    before_macro = target_service.get_macro_info_dict_from_basemesh(human)
    before_values = check_macro_values({k: before_macro.get(k) for k in values})
    if all(abs(values[k] - before_values[k]) < 0.0001 for k in values):
        raise RefitError("Saved body controls already match the existing master")
    before = inspect_applied_macro(bpy, human, target_service, before_values)
    rig_before = rig_fingerprint(bpy, human)
    original_vertex_count = len(human.data.vertices)

    for name, value in values.items():
        properties.set_value(name, value, entity_reference=human)
    target_service.reapply_macro_details(human)
    human_service.refit(human)
    after = inspect_applied_macro(bpy, human, target_service, values)
    rig_after = rig_fingerprint(bpy, human)
    if len(human.data.vertices) != original_vertex_count:
        raise RefitError("Macro update unexpectedly changed source mesh topology")
    if after["macro_evaluated_vertices"] != before["macro_evaluated_vertices"]:
        raise RefitError("Macro update unexpectedly changed evaluated vertex count")
    if after["macro_evaluated_sha256"] == before["macro_evaluated_sha256"]:
        raise RefitError("MPFB macro reapplication did not change evaluated geometry")
    for name in ("bone_count", "bone_names", "bone_weight_groups",
                 "weighted_vertices", "weight_sha256", "armature_modifier_count"):
        if rig_after[name] != rig_before[name]:
            raise RefitError("Existing humanoid rig weights/binding changed after refit: " + name)

    bpy.ops.wm.save_as_mainfile(filepath=str(destination), compress=False)
    if destination.is_symlink() or not destination.is_file() or destination.stat().st_size < 1024:
        raise RefitError("Refitted Blender master did not save successfully")
    with destination.open("rb") as stream:
        if stream.read(7) != b"BLENDER":
            raise RefitError("Refitted master is not an uncompressed Blender file")
    return {
        "staged_blend": destination.name,
        "refit_method": "MPFB TargetService.reapply_macro_details + HumanService.refit",
        "previous_macros": before_values,
        "previous_evaluated_sha256": before["macro_evaluated_sha256"],
        "previous_rig": rig_before,
        "updated_rig": rig_after,
        **after,
        "refit_saved": True,
        "animation_deformation_verified": False,
        "engine_import_verified": False,
    }
