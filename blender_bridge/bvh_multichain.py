"""Strict two-to-four-bone direct-name BVH chain with explicit axis/rest checks.

This probes actual MPFB skin movement in Blender. It only accepts source bones
with exact target names, the same parent chain, and aligned *rest directions*
under a fixed axis conversion. It does NOT correct bone roll, solve rotations
in world space, import root motion, handle arbitrary skeletons, or certify
retargeting. Master and source BVH are never saved by this code.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
from typing import Any

from blender_bridge.bvh_clip_probe import _file_digest
from blender_bridge.bvh_motion import LocalBvhError, LocalBvhMotion, read_local_bvh
from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.refit_revision import rig_fingerprint

AXIS_PROFILES = frozenset({"Y_UP_TO_Z_UP", "Z_UP_IDENTITY"})
MIN_SOURCE_BONES = 2
MAX_SOURCE_BONES = 4
MIN_WEIGHTED_VERTICES = 16
MIN_ALIGNMENT_COS = 0.90
MAX_RATIO_SPREAD = 0.25
MAX_ANGLE_DELTA = 45.0
PROBE_DEGREES = 12.0


class MultiBvhError(RuntimeError):
    """An animation source/rig chain cannot be mapped without guessing."""


def _convert_offset(source: tuple[float, float, float],
                    profile: str) -> tuple[float, float, float]:
    if profile not in AXIS_PROFILES:
        raise MultiBvhError("Unknown BVH source up-axis; explicit profile required")
    x, y, z = source
    return (x, -z, y) if profile == "Y_UP_TO_Z_UP" else (x, y, z)


def _unit(vec: tuple[float, float, float]) -> tuple[tuple[float, float, float], float]:
    size = math.sqrt(sum(x * x for x in vec))
    if not math.isfinite(size) or not 1e-7 < size < 1e6:
        raise MultiBvhError("BVH chain has a missing/extreme rest-direction vector")
    return tuple(v / size for v in vec), size


def select_explicit_chain(
    motion: LocalBvhMotion, human: Any, rig: Any, axis_profile: str,
    reviewed_mapping: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Old direct-name chain or explicitly reviewed, ordered source/target names.

    The reviewed mode does not guess aliases or infer whole-body transforms.
    It additionally requires the separate two-landmark SO(3) calibration.
    """
    if axis_profile not in AXIS_PROFILES:
        raise MultiBvhError("Choose a supported explicit BVH up-axis preset")
    if reviewed_mapping is None:
        names = motion.source_bones
        if not MIN_SOURCE_BONES <= len(names) <= MAX_SOURCE_BONES:
            raise MultiBvhError("Only explicit 2–4-joint BVH chains are supported")
        destination = {name.casefold(): name for name in names}
    else:
        if (type(reviewed_mapping) is not list or
                not 3 <= len(reviewed_mapping) <= 8):
            raise MultiBvhError("Reviewed mapping requires 3–8 ordered bone pairs")
        names = tuple(row.get("source") if isinstance(row, dict) else None
                      for row in reviewed_mapping)
        targets = tuple(row.get("target") if isinstance(row, dict) else None
                        for row in reviewed_mapping)
        import re
        valid = re.compile(r"[A-Za-z0-9_.:-]{1,128}\\Z", re.ASCII)
        if (any(type(n) is not str or not valid.fullmatch(n)
                for n in (*names, *targets)) or
                len({n.casefold() for n in names}) != len(names) or
                len({n.casefold() for n in targets}) != len(targets)):
            raise MultiBvhError("Reviewed map has missing, unsafe or duplicate bone names")
        if any(name.casefold() not in {x.casefold() for x in motion.source_bones}
               for name in names):
            raise MultiBvhError("Explicitly mapped source bone does not exist in BVH")
        destination = {src.casefold(): dst for src, dst in zip(names, targets)}
    if len({n.casefold() for n in names}) != len(names):
        raise MultiBvhError("Ambiguous case-insensitive BVH joint names")
    target_map: dict[str, Any] = {}
    for obj in rig.data.bones:
        key = obj.name.casefold()
        if key in target_map:
            raise MultiBvhError("Target rig has ambiguous case-insensitive bone names")
        target_map[key] = obj
    pose_map = {bone.name.casefold(): bone for bone in rig.pose.bones}
    weights = {group.index: group.name.casefold() for group in human.vertex_groups}
    coverage = {name.casefold(): 0 for name in destination.values()}
    for vertex in human.data.vertices:
        for value in vertex.groups:
            name = weights.get(value.group)
            if name in coverage and value.weight >= 0.1:
                coverage[name] += 1
    selected = []
    scaling = []
    for name in names:
        key = name.casefold()
        target_key = destination[key].casefold()
        actual = target_map.get(target_key)
        pose = pose_map.get(target_key)
        if (actual is None or pose is None or not actual.use_deform
                or coverage.get(target_key, 0) < MIN_WEIGHTED_VERTICES):
            raise MultiBvhError("BVH joint has no exact, substantially weighted MPFB deform bone: " + name)
        declared = motion.channel_orders.get(key, ())
        order = tuple(x for x in declared if x.endswith("rotation"))
        if order != ("Xrotation", "Yrotation", "Zrotation"):
            raise MultiBvhError("Multi-bone BVH requires explicit XYZ Euler channel order")
        angles = motion.rotations.get(key)
        if angles is None or len(angles) != motion.frames:
            raise MultiBvhError("BVH chain member has no full XYZ motion")
        base = angles[0]
        maximum = max(abs(value[i] - base[i])
                      for value in angles for i in range(3))
        if not 1.0 <= maximum <= MAX_ANGLE_DELTA:
            raise MultiBvhError("Each BVH joint must have safe 1–45 degree source motion")
        parent_name = motion.parents.get(key)
        if selected:
            if parent_name != selected[-1]["source"].casefold():
                raise MultiBvhError(
                    "BVH source must form a directly connected, non-branching joint chain"
                )
        elif parent_name is not None:
            raise MultiBvhError("First selected BVH joint must be the source root")
        if parent_name is not None:
            target_parent = destination.get(parent_name)
            parent = target_map.get(target_parent.casefold()) if target_parent else None
            if parent is None or actual.parent != parent:
                raise MultiBvhError("Source/target bone parents differ; do not guess rest mapping")
            source_vec = _convert_offset(motion.offsets[key], axis_profile)
            src_unit, src_len = _unit(source_vec)
            target_vec = tuple(
                float(a - b)
                for a, b in zip(actual.head_local, parent.head_local)
            )
            target_unit, target_len = _unit(target_vec)
            cos = sum(a * b for a, b in zip(src_unit, target_unit))
            if reviewed_mapping is None and cos < MIN_ALIGNMENT_COS:
                raise MultiBvhError(
                    "BVH rest offset does not align with target bone "
                    "under selected axis conversion"
                )
            scaling.append(target_len / src_len)
        selected.append({
            "source": name, "target": actual.name,
            "weighted_vertices": coverage[target_key],
            "parent": parent_name, "target_parent": actual.parent.name if actual.parent else None,
            "max_delta_degrees": maximum,
            "rest_alignment_cos": cos if parent_name is not None else None,
            "angles": angles,
            "pose": pose,
        })
    if len(scaling) != len(names) - 1:
        raise MultiBvhError("BVH chain requires one root and connected children")
    scale = sum(scaling) / len(scaling)
    if not 1e-5 < scale < 1e5 or any(
        abs(value - scale) / scale > MAX_RATIO_SPREAD for value in scaling
    ):
        raise MultiBvhError("BVH and MPFB chain rest lengths have inconsistent scales")
    return selected, {
        "axis_profile": axis_profile,
        "rest_direction_alignment_verified": True,
        "rest_length_scale_measured": True,
        "rest_scale_consistency_verified": len(scaling) > 1,
        "relative_rest_length_scale": scale,
        "bone_roll_calibrated": False,
        "mapping_method": ("EXPLICIT_USER_REVIEWED_PAIRS"
                           if reviewed_mapping is not None else "DIRECT_EXACT_NAMES"),
        "retargeting_verified": False,
    }


def verify_multibone_source(bpy: Any, master: Path, source_bvh: Path,
                            axis_profile: str) -> dict[str, Any]:
    """Move 2–4 existing weighted MPFB bones from a single source BVH Action."""
    motion = read_local_bvh(source_bvh)
    source_digest = _file_digest(source_bvh)
    if master.is_symlink() or not master.is_file() or master.suffix.lower() != ".blend":
        raise MultiBvhError("Expected private staged Blender master")
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    humans = [obj for obj in bpy.data.objects
              if obj.type == "MESH" and len(obj.data.vertices) > 100]
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(humans) != 1 or len(rigs) != 1:
        raise MultiBvhError("Expected one substantial MPFB basemesh and armature")
    human, rig = humans[0], rigs[0]
    bound = rig_fingerprint(bpy, human)
    if rig.animation_data and (rig.animation_data.action or len(rig.animation_data.nla_tracks)):
        raise MultiBvhError("Existing saved animation cannot be overwritten")
    members, rest_evidence = select_explicit_chain(motion, human, rig, axis_profile)
    scene = bpy.context.scene
    saved_frame = scene.frame_current
    saved_fps, saved_base = scene.render.fps, scene.render.fps_base
    saved_position = rig.data.pose_position
    originals = [(entry["pose"], entry["pose"].matrix_basis.copy(),
                  entry["pose"].rotation_mode) for entry in members]
    action = None
    try:
        rig.data.pose_position = "POSE"
        for entry in members:
            entry["pose"].rotation_mode = "XYZ"
        baseline, neutral_hash = _evaluated_vertices(bpy, human)
        per_bone = []
        for entry in members:
            bone = entry["pose"]
            base = bone.matrix_basis.copy()
            try:
                bone.rotation_euler[0] += math.radians(PROBE_DEGREES)
                moved_mesh, moved_hash = _evaluated_vertices(bpy, human)
            finally:
                bone.matrix_basis = base
                bpy.context.view_layer.update()
            count, maximum = _movement(baseline, moved_mesh)
            restored, restored_hash = _evaluated_vertices(bpy, human)
            if (count < MIN_WEIGHTED_VERTICES or maximum <= 1e-5
                    or moved_hash == neutral_hash
                    or restored_hash != neutral_hash):
                raise MultiBvhError("Individual exact-match bone failed real skin movement probe")
            per_bone.append({
                "bone": entry["target"], "moved_vertices": count,
                "max_displacement_local": maximum,
            })
        original_angles = {
            entry["target"]: tuple(float(v) for v in entry["pose"].rotation_euler)
            for entry in members
        }
        scene.render.fps = min(120, max(1, round(1 / motion.frame_time)))
        scene.render.fps_base = 1.0
        for frame in range(motion.frames):
            for entry in members:
                bone = entry["pose"]
                first = entry["angles"][0]
                for axis in range(3):
                    bone.rotation_euler[axis] = (
                        original_angles[entry["target"]][axis]
                        + math.radians(entry["angles"][frame][axis] - first[axis])
                    )
                if bone.keyframe_insert(
                    data_path="rotation_euler", frame=frame + 1,
                    group="UCC_PRIVATE_MULTIBONE_BVH",
                ) is not True:
                    raise MultiBvhError("Blender did not key all source joint rotations")
        action = rig.animation_data.action if rig.animation_data else None
        if action is None:
            raise MultiBvhError("No assigned Blender Action from multi-bone source")
        frame_ids = sorted(set((
            1, 1 + (motion.frames - 1) // 4, 1 + (motion.frames - 1) // 2,
            1 + 3 * (motion.frames - 1) // 4, motion.frames,
        )))
        if len(frame_ids) != 5:
            raise MultiBvhError("Cannot sample five distinct multi-bone motion frames")
        base_mesh = None
        samples = []
        geometry_hashes = set()
        for frame in frame_ids:
            scene.frame_set(frame)
            mesh, digest = _evaluated_vertices(bpy, human)
            if base_mesh is None:
                base_mesh = mesh
            moved, distance = _movement(base_mesh, mesh)
            samples.append({
                "frame": frame,
                "evaluated_sha256": digest,
                "evaluated_vertex_count": len(mesh),
                "moved_vertices": moved,
                "max_displacement_local": distance,
            })
            geometry_hashes.add(digest)
        if (len(geometry_hashes) < 3 or
                sum(item["moved_vertices"] >= 16 for item in samples[1:]) < 2):
            raise MultiBvhError("Actual multi-bone action did not produce changing skinned frames")
        if rig_fingerprint(bpy, human) != bound:
            raise MultiBvhError("Multi-bone motion damaged MPFB rest rig/weight data")
        if _file_digest(source_bvh) != source_digest:
            raise MultiBvhError("Source BVH changed during source motion evaluation")
        return {
            "status": "REAL_MPFB_MULTIBONE_BVH_CHAIN_GEOMETRY_MEASURED",
            "source_sha256": source_digest,
            "source_frame_count": motion.frames,
            "source_frame_time": motion.frame_time,
            "mapped_bone_count": len(members),
            "mapped_bones": [
                {k: v for k, v in entry.items() if k in (
                    "source", "target", "weighted_vertices", "parent",
                    "max_delta_degrees", "rest_alignment_cos"
                )} for entry in members
            ],
            "per_bone_deformation": per_bone,
            "sampled_frames": samples,
            "frame_sample_count": len(samples),
            "distinct_geometry_states": len(geometry_hashes),
            "keyframes_inserted": len(members) * motion.frames,
            "rig_bone_count": bound["bone_count"],
            "rig_weight_sha256": bound["weight_sha256"],
            "rig_rest_sha256": bound["rig_rest_sha256"],
            "blender_version": bpy.app.version_string,
            **rest_evidence,
            "source_translation_ignored": True,
            "source_orientation_calibrated": False,
            "user_clip_evaluated_in_blender": True,
            "animation_visual_quality_verified": False,
            "engine_import_verified": False,
            "source_master_saved": False,
            "source_bvh_modified": False,
        }
    finally:
        if rig.animation_data and action is not None:
            rig.animation_data_clear()
            bpy.data.actions.remove(action, do_unlink=True)
        for bone, basis, mode in originals:
            bone.rotation_mode = mode
            bone.matrix_basis = basis
        rig.data.pose_position = saved_position
        scene.render.fps, scene.render.fps_base = saved_fps, saved_base
        scene.frame_set(saved_frame)
        bpy.context.view_layer.update()
