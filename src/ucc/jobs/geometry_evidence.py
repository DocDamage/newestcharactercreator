"""Checks from two *real* Blender worker results, not proof of deformation.

These structural criteria are shared by the production project transaction
and Linux smoke. Synthetic fixtures may exercise rejections, but only a real
Blender create/reopen run establishes that an actual asset passed the gate.
"""
from __future__ import annotations

from typing import Any


class EvidenceError(RuntimeError):
    """A staged humanoid was not proven to survive a new Blender process."""


def _positive_int(value: object, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def verify_geometry(created: dict[str, Any], reopened: dict[str, Any]) -> dict[str, Any]:
    """Require substantial MPFB geometry, a rig, and independent reopen parity."""
    if created.get("method") != "HumanService" or created.get("rig_choice") != "default":
        raise EvidenceError("Created master did not use the pinned MPFB HumanService rig")

    meshes = created.get("created_meshes")
    rigs = created.get("rigs")
    if not isinstance(meshes, list) or not meshes or not all(
        isinstance(mesh, dict) and _positive_int(mesh.get("vertex_count"), 101)
        for mesh in meshes
    ):
        raise EvidenceError("Production creation returned no substantial new human meshes")
    if not isinstance(rigs, list) or not rigs or not any(
        isinstance(rig, dict) and _positive_int(rig.get("bone_count"), 5)
        for rig in rigs
    ):
        raise EvidenceError("Production creation returned no populated new armature")

    armatures = reopened.get("armatures")
    if not _positive_int(reopened.get("mesh_count"), 1) or not _positive_int(
        reopened.get("vertex_count"), 101
    ):
        raise EvidenceError("Fresh-process Blender inspection found no substantial mesh")
    if not isinstance(armatures, list) or not any(
        isinstance(arm, dict) and _positive_int(arm.get("bone_count"), 5)
        for arm in armatures
    ):
        raise EvidenceError("Fresh-process Blender inspection found no populated armature")

    original_vertices = sum(m["vertex_count"] for m in meshes)
    original_bones = sum(r["bone_count"] for r in rigs)
    reopened_bones = sum(a["bone_count"] for a in armatures)
    if reopened["vertex_count"] < original_vertices or reopened_bones < original_bones:
        raise EvidenceError("Reopened master lost generated vertices or rig bones")
    if not created.get("blender_version") or (
        reopened.get("blender_version") != created["blender_version"]
    ):
        raise EvidenceError("Creation and reopen Blender versions differ or are missing")
    return {
        "created_mesh_count": len(meshes),
        "created_vertex_count": original_vertices,
        "created_armature_count": len(rigs),
        "reopened_mesh_count": reopened["mesh_count"],
        "reopened_vertex_count": reopened["vertex_count"],
        "reopened_armature_count": len(armatures),
        "reopened_bone_count": reopened_bones,
        "blender_version": reopened["blender_version"],
    }
