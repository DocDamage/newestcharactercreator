"""Measure rest-axis-calibrated BVH rotation deltas on a real MPFB weighted rig.

This is a narrow, experimental 2–4-joint, exact-name source chain using
at least two independent anatomical rest-direction correspondences, including
a terminal BVH End Site. The source coordinate system is explicit, source
rotations use their ordered BVH channels and target motion is converted by
rest-bone matrix conjugation. NOTHING is saved to the user's .blend master.

Do not claim general full-body or visual retargeting: unambiguous anatomy,
user-reviewed rights and target-engine playback remain separate gates.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
import struct
from typing import Any

from blender_bridge.bvh_clip_probe import _file_digest
from blender_bridge.bvh_review_timeline import evaluate_review_timeline
from blender_bridge.motion_quality import JointMotion
from blender_bridge.pose_environment import validate_pose_environment
from blender_bridge.source_rest_intake import inspect_source_rest_profile
import json
from blender_bridge.bvh_motion import read_local_bvh
from blender_bridge.bvh_multichain import (
    MIN_WEIGHTED_VERTICES, MultiBvhError, select_explicit_chain,
)
from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.refit_revision import rig_fingerprint
from blender_bridge.rest_calibration import (
    RestCalibrationError, axis_rotation, bvh_ordered_rotation,
    calibrate_rest_frames, calibrated_local_delta,
    Z_UP_IDENTITY,
)


class BvhCalibrationProbeError(RuntimeError):
    """The actual BVH and the MPFB rig cannot be safely rest-calibrated."""


def _digest_matrix(matrix: Any) -> str:
    digest = sha256()
    for row in matrix:
        for value in row:
            if not math.isfinite(float(value)):
                raise BvhCalibrationProbeError("Nonfinite calibrated matrix")
            digest.update(struct.pack("<q", round(float(value) * 1_000_000)))
    return digest.hexdigest()


def _matrix_tuple(blender_matrix: Any) -> tuple:
    return tuple(tuple(float(x) for x in row) for row in blender_matrix)


def _landmarks(motion: Any, selected: list[dict], rig: Any) -> tuple[list, list]:
    source = []
    target = []
    real_bones = {bone.name: bone for bone in rig.data.bones}
    by_source = {item["source"].casefold(): item for item in selected}
    parents = {item["parent"] for item in selected[1:]}
    for item in selected[1:]:
        parent = by_source.get(item["parent"])
        name = item["source"].casefold()
        if parent is None or motion.parents.get(name) != parent["source"].casefold():
            raise BvhCalibrationProbeError("Source hierarchy must have direct mapped parents")
        src = motion.offsets.get(name)
        actual, parent_actual = real_bones[item["target"]], real_bones[parent["target"]]
        if src is None:
            raise BvhCalibrationProbeError("BVH hierarchy missing joint rest offset")
        source.append(src)
        target.append(tuple(float(x - y) for x, y in
                            zip(actual.head_local, parent_actual.head_local)))
    for item in selected:
        if item["source"].casefold() in parents:
            continue
        end = motion.end_site_offsets.get(item["source"].casefold())
        if end is None:
            raise BvhCalibrationProbeError(
                "Every mapped leaf requires a terminal BVH End Site rest landmark"
            )
        leaf = real_bones[item["target"]]
        source.append(end)
        target.append(tuple(float(x - y) for x, y in
                            zip(leaf.tail_local, leaf.head_local)))
    return source, target


def calibrate_bvh_source(bpy: Any, master: Path, source_bvh: Path,
                         axis_profile: str,
                         reviewed_mapping: list[dict[str, str]] | None = None,
                         review_path: Path | None = None,
                         source_rest_profile: Path | None = None,
                         source_rest_profile_sha256: str | None = None) -> dict[str, Any]:
    """Create only ephemeral, measured, axis-calibrated source BVH rotations."""
    motion = read_local_bvh(source_bvh)
    source_sha = _file_digest(source_bvh)
    source_intake = None
    if (source_rest_profile is None) != (source_rest_profile_sha256 is None):
        raise BvhCalibrationProbeError("Source rest profile and SHA-256 must accompany each other")
    if source_rest_profile is not None:
        if reviewed_mapping is None:
            raise BvhCalibrationProbeError("Source rest frames require reviewed source pairs")
        source_intake = inspect_source_rest_profile(
            source_rest_profile, source_rest_profile_sha256, motion, source_sha,
            axis_profile, reviewed_mapping,
        )
    if (master.is_symlink() or not master.is_file() or
            master.suffix.lower() != ".blend"):
        raise BvhCalibrationProbeError("Expected regular staged MPFB master")
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    humans = [o for o in bpy.data.objects if o.type == "MESH"
              and len(o.data.vertices) > 100]
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(humans) != 1 or len(rigs) != 1:
        raise BvhCalibrationProbeError("Existing Blender master needs one human/rig")
    human, rig = humans[0], rigs[0]
    rig_before = rig_fingerprint(bpy, human)
    if rig.animation_data and (
        rig.animation_data.action or len(rig.animation_data.nla_tracks)
    ):
        raise BvhCalibrationProbeError("Refuse to overwrite existing Actions or NLA tracks")
    if (reviewed_mapping is None) != (review_path is None):
        raise BvhCalibrationProbeError("Explicit mapping and private review output must accompany each other")
    selected, chain = select_explicit_chain(
        motion, human, rig, axis_profile, reviewed_mapping,
    )
    if reviewed_mapping is not None:
        validate_pose_environment(rig, human, [item["target"] for item in selected])
    source_vectors, target_vectors = _landmarks(motion, selected, rig)
    try:
        calibration = calibrate_rest_frames(
            source_vectors, target_vectors, axis_profile,
        )
    except RestCalibrationError as exc:
        raise BvhCalibrationProbeError(
            "Rest landmark pair calibration refused: " + str(exc)
        ) from exc
    # Validate the entire measured rest transform, not just a single direction.
    from mathutils import Matrix
    scene = bpy.context.scene
    old_frame = scene.frame_current
    old_fps, old_base = scene.render.fps, scene.render.fps_base
    old_position = rig.data.pose_position
    preserved = [(item["pose"], item["pose"].matrix_basis.copy(),
                  item["pose"].rotation_mode) for item in selected]
    transient_action = None
    try:
        rig.data.pose_position = "POSE"
        scene.render.fps = max(1, min(120, round(1 / motion.frame_time)))
        scene.render.fps_base = 1.0
        for item in selected:
            bone = item["pose"]
            if any(abs(bone.matrix_basis[i][j] - float(i == j)) > 1e-4
                   for i in range(4) for j in range(4)):
                raise BvhCalibrationProbeError(
                    "Non-neutral preexisting bone pose; rest calibration not safe"
                )
            bone.rotation_mode = "QUATERNION"
        bpy.context.view_layer.update()
        neutral, neutral_hash = _evaluated_vertices(bpy, human)
        from blender_bridge.rest_calibration import validate_rotation
        rest_frames = {}
        rest_projections = {}
        initial_motion = {}
        for item in selected:
            name = item["target"]
            raw_rest = _matrix_tuple(item["pose"].bone.matrix_local.to_3x3())
            try:
                from blender_bridge.rest_calibration import project_near_rotation
                rest, raw_det, projection = project_near_rotation(raw_rest)
            except RestCalibrationError as exc:
                from blender_bridge.rest_calibration import determinant
                raise BvhCalibrationProbeError(
                    f"Real Blender rest matrix rejected for bone {name}: "
                    f"det={determinant(raw_rest):.9f}; {exc}"
                ) from exc
            rest_frames[name] = rest
            rest_projections[name] = (raw_det, projection)
            initial_motion[name] = bvh_ordered_rotation(
                motion.channel_orders[item["source"].casefold()],
                item["angles"][0],
            )

        per_bone = []
        axis_checks = []
        for item in selected:
            name, bone = item["target"], item["pose"]
            base = bone.matrix_basis.copy()
            try:
                calibrated_test = calibrated_local_delta(
                    Z_UP_IDENTITY, axis_rotation("Xrotation", 12.0),
                    calibration.source_axes_to_target, rest_frames[name],
                )
            except RestCalibrationError as exc:
                raise BvhCalibrationProbeError(
                    f"Calibrated pose matrix for bone {name} rejected: {exc}"
                ) from exc
            try:
                bone.rotation_quaternion = Matrix(calibrated_test).to_quaternion()
                posed, pose_hash = _evaluated_vertices(bpy, human)
            finally:
                bone.matrix_basis = base
                bpy.context.view_layer.update()
            count, distance = _movement(neutral, posed)
            restored, restored_hash = _evaluated_vertices(bpy, human)
            if (count < MIN_WEIGHTED_VERTICES or distance <= 1e-5
                    or pose_hash == neutral_hash or restored_hash != neutral_hash):
                raise BvhCalibrationProbeError(
                    "Calibrated bone did not move actual skinned mesh and restore pose"
                )
            per_bone.append({
                "bone": name, "moved_vertices": count,
                "max_displacement_local": distance,
            })
            axis_checks.append({
                "source": item["source"], "target": name,
                "source_axes_to_target_sha256": _digest_matrix(
                    calibration.source_axes_to_target,
                ),
                "target_rest_matrix_sha256": _digest_matrix(rest_frames[name]),
                "calibrated_test_delta_sha256": _digest_matrix(calibrated_test),
                "measured_rest_raw_determinant": rest_projections[name][0],
                "bounded_rest_projection_delta": rest_projections[name][1],
            })

        previous_quaternions = {}
        max_quaternion_steps = {item["target"]: 0.0 for item in selected}
        joint_metrics = {item["target"]: JointMotion(item["target"]) for item in selected}
        for frame in range(motion.frames):
            for item in selected:
                name, bone = item["target"], item["pose"]
                current = bvh_ordered_rotation(
                    motion.channel_orders[item["source"].casefold()],
                    item["angles"][frame],
                )
                try:
                    converted = calibrated_local_delta(
                        initial_motion[name], current,
                        calibration.source_axes_to_target, rest_frames[name],
                    )
                except RestCalibrationError as exc:
                    raise BvhCalibrationProbeError(
                        f"Source frame {frame + 1}, bone {name} rotation refused: {exc}"
                    ) from exc
                quaternion = Matrix(converted).to_quaternion()
                if reviewed_mapping is not None:
                    quaternion = type(quaternion)(joint_metrics[name].add(tuple(quaternion), frame + 1))
                prior = previous_quaternions.get(name)
                if prior is not None:
                    if prior.dot(quaternion) < 0:
                        quaternion.negate()
                    step = math.degrees(prior.rotation_difference(quaternion).angle)
                    if reviewed_mapping is not None:
                        step = joint_metrics[name].maxima["max_step_degrees"]
                    if step > 80.0:
                        raise BvhCalibrationProbeError(
                            f"Bone {name} has a {step:.2f}-degree single-frame rotation jump"
                        )
                    max_quaternion_steps[name] = max(max_quaternion_steps[name], step)
                previous_quaternions[name] = quaternion.copy()
                bone.rotation_quaternion = quaternion
                if bone.keyframe_insert(
                    data_path="rotation_quaternion", frame=frame + 1,
                    group="UCC_TEMP_REST_AXES_PROBE",
                ) is not True:
                    raise BvhCalibrationProbeError(
                        "Failed to insert real calibrated Blender quaternion keys"
                    )
        transient_action = rig.animation_data.action if rig.animation_data else None
        if transient_action is None:
            raise BvhCalibrationProbeError("No actual Blender Action from source motion")

        frames = sorted(set((
            1, 1 + (motion.frames - 1) // 4, 1 + (motion.frames - 1) // 2,
            1 + 3 * (motion.frames - 1) // 4, motion.frames,
        )))
        if len(frames) != 5:
            raise BvhCalibrationProbeError("Five distinct animation frames required")
        baseline = None
        sampled = []
        hashes = set()
        for frame in frames:
            scene.frame_set(frame)
            coords, digest = _evaluated_vertices(bpy, human)
            if baseline is None:
                baseline = coords
            count, distance = _movement(baseline, coords)
            sampled.append({
                "frame": frame, "evaluated_sha256": digest,
                "evaluated_vertex_count": len(coords),
                "moved_vertices": count,
                "max_displacement_local": distance,
            })
            hashes.add(digest)
        if (len(hashes) < 3 or
                sum(item["moved_vertices"] >= 16 for item in sampled[1:]) < 2):
            raise BvhCalibrationProbeError(
                "Calibrated source motion did not produce real changing frame geometry"
            )
        if rig_fingerprint(bpy, human) != rig_before:
            raise BvhCalibrationProbeError("Calibrated test changed original rig weights")
        if _file_digest(source_bvh) != source_sha:
            raise BvhCalibrationProbeError("BVH changed while evaluating motion")
        if source_rest_profile is not None and _file_digest(source_rest_profile) != source_rest_profile_sha256:
            raise BvhCalibrationProbeError("Source rest frames changed while evaluating motion")
        review_metrics = {}
        if reviewed_mapping is not None:
            assert review_path is not None
            review_metrics = evaluate_review_timeline(
                bpy, human, rig, motion.frames, review_path,
            )
            if rig_fingerprint(bpy, human) != rig_before:
                raise BvhCalibrationProbeError("Visual review Action changed skin/rig rest state")
            from hashlib import sha256 as _hash
            mapping_bytes = json.dumps(
                reviewed_mapping, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
            review_metrics.update({
                "reviewed_mapping_sha256": _hash(mapping_bytes).hexdigest(),
                "explicit_mapping_reviewed_by_user": True,
                "max_bone_quaternion_step_degrees": max_quaternion_steps,
                "joint_motion_metrics": [joint_metrics[item["target"]].report() for item in selected],
                "target_pose_environment_checked": True,
                "source_rest_frame_intake": source_intake,
            })
        return {
            "status": ("REAL_REVIEWED_BVH_FULL_TIMELINE_MOTION"
                       if reviewed_mapping is not None else
                       "REAL_BVH_REST_AXES_CALIBRATED_MESH_MOTION"),
            "source_sha256": source_sha,
            "source_frame_count": motion.frames,
            "source_frame_time": motion.frame_time,
            "axis_profile": axis_profile,
            "source_to_target_axes_sha256": _digest_matrix(
                calibration.source_axes_to_target,
            ),
            "rest_landmark_count": len(source_vectors),
            "rest_reference_pair": list(calibration.landmark_pair),
            "rest_residual_degrees": list(calibration.rest_residual_degrees),
            "max_rest_residual_degrees": calibration.max_rest_residual_degrees,
            "rest_axes_calibrated": True,
            "raw_rest_rotation_projected_with_bound": True,
            "maximum_rest_projection_delta": max(
                item[1] for item in rest_projections.values()
            ),
            "bone_roll_independently_verified": False,
            "mapped_bone_count": len(selected),
            "mapped_bones": [
                {"source": x["source"], "target": x["target"],
                 "parent": x["parent"],
                 **({"target_parent": x["target_parent"]}
                    if reviewed_mapping is not None else {})}
                for x in selected
            ],
            "per_bone_deformation": per_bone,
            "local_axis_proofs": axis_checks,
            "sampled_frames": sampled,
            "distinct_geometry_states": len(hashes),
            "keyframes_inserted": motion.frames * len(selected),
            "real_quaternion_action_inserted": True,
            "rig_bone_count": rig_before["bone_count"],
            "rig_weight_sha256": rig_before["weight_sha256"],
            "rig_rest_sha256": rig_before["rig_rest_sha256"],
            "blender_version": bpy.app.version_string,
            "source_translation_ignored": True,
            "user_clip_evaluated_in_blender": True,
            "retargeting_verified": False,
            "animation_visual_quality_verified": False,
            "engine_import_verified": False,
            "source_master_saved": False,
            "source_bvh_modified": False,
            **review_metrics,
        }
    finally:
        # A bound can fail halfway through key insertion, before the completed
        # Action is assigned to transient_action. No Action existed on entry.
        partial_action = rig.animation_data.action if rig.animation_data else None
        action_to_remove = transient_action or partial_action
        if rig.animation_data and action_to_remove is not None:
            rig.animation_data_clear()
            bpy.data.actions.remove(action_to_remove, do_unlink=True)
        for bone, basis, mode in preserved:
            bone.rotation_mode = mode
            bone.matrix_basis = basis
        rig.data.pose_position = old_position
        scene.render.fps, scene.render.fps_base = old_fps, old_base
        scene.frame_set(old_frame)
        bpy.context.view_layer.update()
