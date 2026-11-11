"""Measure real mesh deformation from a temporary Blender pose-bone rotation.

This diagnostic runs in an isolated Blender subprocess on an unsaved copy of
a content-addressed UCC master. It does not play animation clips, save poses,
alter project files, enable scripts from blends, or certify engine imports.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import math
from pathlib import Path
import struct
from typing import Any

from blender_bridge.refit_revision import rig_fingerprint

MAX_MESH_VERTICES = 250_000
MAX_BONE_ATTEMPTS = 16
ANGLE_DEGREES = 20.0
MOVE_TOLERANCE = 1e-5
RESTORE_TOLERANCE = 2e-6


class PoseProbeError(RuntimeError):
    """A bound humanoid failed the actual deforming-bone pose test."""


def _evaluated_vertices(bpy: Any, human: Any) -> tuple[tuple[tuple[float, float, float], ...], str]:
    """Read evaluated mesh coordinates, not custom properties or undeformed data."""
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = human.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    if mesh is None:
        raise PoseProbeError("Blender could not evaluate skinned human vertices")
    try:
        if not 100 < len(mesh.vertices) <= MAX_MESH_VERTICES:
            raise PoseProbeError("Evaluated human mesh vertex count is outside safe limits")
        digest = sha256()
        points = []
        for vertex in mesh.vertices:
            xyz = tuple(float(v) for v in vertex.co)
            if any(not math.isfinite(v) or abs(v) > 1e6 for v in xyz):
                raise PoseProbeError("Evaluated skin geometry contains invalid coordinates")
            points.append(xyz)
            digest.update(struct.pack("<qqq", *(round(v * 1_000_000) for v in xyz)))
        return tuple(points), digest.hexdigest()
    finally:
        evaluated.to_mesh_clear()


def _pose_candidates(human: Any, rig: Any) -> list[str]:
    """Choose actual deforming non-root bones having substantial mesh skin weights."""
    names = {group.index: group.name for group in human.vertex_groups}
    eligible = {
        bone.name for bone in rig.data.bones
        if getattr(bone, "use_deform", False) and bone.parent is not None
    }
    # bpy_prop_collection and a dict both expose pose bone names via keys().
    eligible.intersection_update(set(rig.pose.bones.keys()))
    counts: dict[str, int] = defaultdict(int)
    for vertex in human.data.vertices:
        for assignment in vertex.groups:
            name = names.get(assignment.group)
            if name in eligible and assignment.weight >= 0.1:
                counts[name] += 1
    ordered = sorted((name for name in eligible if counts[name] >= 16),
                     key=lambda name: (-counts[name], name))
    if not ordered:
        raise PoseProbeError("No non-root deform bones have enough real mesh weights")
    return ordered[:MAX_BONE_ATTEMPTS]


def _movement(
    baseline: tuple[tuple[float, float, float], ...],
    posed: tuple[tuple[float, float, float], ...],
) -> tuple[int, float]:
    if len(baseline) != len(posed):
        raise PoseProbeError("Mesh topology changed during transient bone pose")
    moved = 0
    maximum = 0.0
    for before, after in zip(baseline, posed):
        displacement = math.sqrt(sum((a - b) ** 2 for a, b in zip(before, after)))
        if displacement > MOVE_TOLERANCE:
            moved += 1
        maximum = max(maximum, displacement)
    return moved, maximum


def probe_pose_deformation(bpy: Any, source: Path) -> dict[str, Any]:
    """Probe one fixed 20-degree rotation, restore pose, and report real movement."""
    if (source.is_symlink() or not source.is_file() or
            source.suffix.lower() != ".blend"):
        raise PoseProbeError("Select a regular staged Blender master")
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    large = [obj for obj in bpy.data.objects
             if obj.type == "MESH" and len(obj.data.vertices) > 100]
    if len(large) != 1:
        raise PoseProbeError("Expected exactly one substantial saved human basemesh")
    human = large[0]
    bound = rig_fingerprint(bpy, human)
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    rig = rigs[0]
    candidates = _pose_candidates(human, rig)

    prior_pose_position = rig.data.pose_position
    try:
        rig.data.pose_position = "POSE"
        neutral, neutral_hash = _evaluated_vertices(bpy, human)
        for name in candidates:
            bone = rig.pose.bones[name]
            for axis in range(3):
                original_basis = bone.matrix_basis.copy()
                original_mode = bone.rotation_mode
                try:
                    bone.rotation_mode = "XYZ"
                    bone.rotation_euler[axis] += math.radians(ANGLE_DEGREES)
                    posed, posed_hash = _evaluated_vertices(bpy, human)
                finally:
                    bone.rotation_mode = original_mode
                    bone.matrix_basis = original_basis
                    bpy.context.view_layer.update()
                restored, restored_hash = _evaluated_vertices(bpy, human)
                _, restore_max = _movement(neutral, restored)
                if restore_max > RESTORE_TOLERANCE or restored_hash != neutral_hash:
                    raise PoseProbeError("The diagnostic failed to restore the original pose")
                count, maximum = _movement(neutral, posed)
                if count >= 16 and maximum > MOVE_TOLERANCE and posed_hash != neutral_hash:
                    if rig_fingerprint(bpy, human) != bound:
                        raise PoseProbeError("The transient pose changed saved rig weights")
                    return {
                        "status": "REAL_STATIC_SKIN_POSE_MOVEMENT_MEASURED",
                        "selected_deform_bone": name,
                        "rotation_axis_index": axis,
                        "rotation_degrees": ANGLE_DEGREES,
                        "moved_vertex_count": count,
                        "max_vertex_displacement_local": maximum,
                        "evaluated_vertex_count": len(neutral),
                        "neutral_evaluated_sha256": neutral_hash,
                        "posed_evaluated_sha256": posed_hash,
                        "restored_evaluated_sha256": restored_hash,
                        "rig_bone_count": bound["bone_count"],
                        "rig_weight_sha256": bound["weight_sha256"],
                        "rig_rest_sha256": bound["rig_rest_sha256"],
                        "rig_binding_verified": True,
                        "source_master_saved": False,
                        "animation_clip_playback_verified": False,
                        "retargeting_verified": False,
                        "engine_import_verified": False,
                        "blender_version": bpy.app.version_string,
                    }
        raise PoseProbeError("No weighted deform bone moved the real mesh under a test pose")
    finally:
        rig.data.pose_position = prior_pose_position
        bpy.context.view_layer.update()
