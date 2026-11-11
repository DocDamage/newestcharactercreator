"""Run one user-selected BVH rotation source on an existing MPFB weighted bone.

This is source-driven *direct-name local rotation preview*, not calibrated
source-to-target rest-space retargeting. Translation channels, unmatched
bones, bone-roll conversions, FBX/UE formats and engine export are unsupported.
All generated Blender keyframes are transient and never saved to project.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
from typing import Any

from blender_bridge.bvh_motion import read_local_bvh
from blender_bridge.pose_deformation import (
    _evaluated_vertices, _movement, _pose_candidates,
)
from blender_bridge.refit_revision import rig_fingerprint


class BvhClipProbeError(RuntimeError):
    """Real source motion cannot be applied safely to this exact-named bone."""


def _file_digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_motion_probe(bpy: Any, master: Path, source_bvh: Path) -> dict[str, Any]:
    motion = read_local_bvh(source_bvh)
    source_digest = _file_digest(source_bvh)
    if (master.is_symlink() or not master.is_file()
            or master.suffix.lower() != ".blend"):
        raise BvhClipProbeError("Missing regular staged Blender master")
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    humans = [obj for obj in bpy.data.objects
              if obj.type == "MESH" and len(obj.data.vertices) > 100]
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(humans) != 1 or len(rigs) != 1:
        raise BvhClipProbeError("Expected one substantial saved human and armature")
    human, rig = humans[0], rigs[0]
    bound = rig_fingerprint(bpy, human)
    if rig.animation_data and (
        rig.animation_data.action or len(rig.animation_data.nla_tracks)
    ):
        raise BvhClipProbeError("Cannot overwrite a saved armature Action/NLA track")
    candidates = _pose_candidates(human, rig)
    source_name, target_name, rotations = motion.eligible_rotation(candidates)

    scene = bpy.context.scene
    prior_frame = scene.frame_current
    prior_fps, prior_base = scene.render.fps, scene.render.fps_base
    prior_position = rig.data.pose_position
    bone = rig.pose.bones[target_name]
    prior_basis = bone.matrix_basis.copy()
    prior_mode = bone.rotation_mode
    created_action = None
    try:
        rig.data.pose_position = "POSE"
        bone.rotation_mode = "XYZ"
        start_xyz = tuple(float(v) for v in bone.rotation_euler)
        first = rotations[0]
        scene.render.fps = max(1, min(120, round(1.0 / motion.frame_time)))
        scene.render.fps_base = 1.0
        from math import radians
        for frame, source_angles in enumerate(rotations, start=1):
            for axis in range(3):
                bone.rotation_euler[axis] = (
                    start_xyz[axis] + radians(source_angles[axis] - first[axis])
                )
            if bone.keyframe_insert(
                data_path="rotation_euler", frame=frame,
                group="UCC_PRIVATE_BVH_PREVIEW",
            ) is not True:
                raise BvhClipProbeError("Failed to key selected source BVH rotation")
        action = rig.animation_data.action if rig.animation_data else None
        if action is None:
            raise BvhClipProbeError("No actual Blender Action from source BVH motion")
        created_action = action
        frame_ids = tuple(sorted(set((
            1, 1 + (motion.frames - 1) // 4,
            1 + (motion.frames - 1) // 2,
            1 + 3 * (motion.frames - 1) // 4,
            motion.frames,
        ))))
        if len(frame_ids) != 5:
            raise BvhClipProbeError("Need five distinct BVH frames to evaluate")
        neutral = None
        samples = []
        hashes = set()
        for frame in frame_ids:
            scene.frame_set(frame)
            vertices, digest = _evaluated_vertices(bpy, human)
            if neutral is None:
                neutral = vertices
            moved, maximum = _movement(neutral, vertices)
            if not math.isfinite(maximum):
                raise BvhClipProbeError("Nonfinite measured Blender BVH movement")
            samples.append({
                "frame": frame, "evaluated_sha256": digest,
                "moved_vertices": moved, "max_displacement_local": maximum,
                "evaluated_vertex_count": len(vertices),
            })
            hashes.add(digest)
        if len(hashes) < 3 or sum(x["moved_vertices"] >= 16 for x in samples[1:]) < 2:
            raise BvhClipProbeError("Source BVH did not measurably animate the target human")
        if rig_fingerprint(bpy, human) != bound:
            raise BvhClipProbeError("Source BVH preview changed MPFB rig binding or weights")
        if _file_digest(source_bvh) != source_digest:
            raise BvhClipProbeError("Selected BVH changed during Blender evaluation")
        return {
            "status": "REAL_LOCAL_BVH_SOURCE_DRIVEN_MESH_MOTION_MEASURED",
            "source_sha256": source_digest,
            "source_bone": source_name,
            "target_bone": target_name,
            "mapping_method": "DIRECT_NAME_ROTATION_DELTA_NO_REST_CALIBRATION",
            "source_frame_count": motion.frames,
            "source_frame_time": motion.frame_time,
            "keyframes_inserted": motion.frames,
            "frame_sample_count": 5,
            "sampled_frames": samples,
            "distinct_geometry_states": len(hashes),
            "rig_bone_count": bound["bone_count"],
            "rig_weight_sha256": bound["weight_sha256"],
            "rig_rest_sha256": bound["rig_rest_sha256"],
            "blender_version": bpy.app.version_string,
            "source_translation_ignored": True,
            "source_orientation_calibrated": False,
            "user_clip_evaluated_in_blender": True,
            "retargeting_verified": False,
            "animation_visual_quality_verified": False,
            "engine_import_verified": False,
            "source_master_saved": False,
            "source_bvh_modified": False,
        }
    finally:
        if rig.animation_data and created_action is not None:
            rig.animation_data_clear()
            bpy.data.actions.remove(created_action, do_unlink=True)
        bone.rotation_mode = prior_mode
        bone.matrix_basis = prior_basis
        rig.data.pose_position = prior_position
        scene.render.fps, scene.render.fps_base = prior_fps, prior_base
        scene.frame_set(prior_frame)
        bpy.context.view_layer.update()
