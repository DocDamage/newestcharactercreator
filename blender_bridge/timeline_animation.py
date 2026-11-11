"""Genuine one-second keyframed skeletal animation diagnostic for saved MPFB rigs.

This creates an ORIGINAL temporary three-keyframe motion on an isolated Blender
copy, then uses Blender scene.frame_set() to evaluate five timeline frames. It
does not import any licensed clip, store an Action in a user master, or claim
retargeting, viewport playback or exported-engine support.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from blender_bridge.pose_deformation import (
    PoseProbeError, _evaluated_vertices, _movement, probe_pose_deformation,
)
from blender_bridge.refit_revision import rig_fingerprint

KEYFRAMES = (1, 13, 25)
SAMPLE_FRAMES = (1, 7, 13, 19, 25)
FRAME_RATE = 24
ANGLE_DEGREES = 20.0
MIN_MOVED = 16
MOVEMENT_MIN = 0.00001
RESTORE_TOLERANCE = 0.000002


class TimelineProbeError(RuntimeError):
    """A real keyed Blender timeline did not animate and restore a skinned mesh."""


def validate_timeline_frame_stats(stats: list[dict[str, Any]]) -> None:
    """Reject non-moving, duplicate, nonrestored or unsampled timeline positions."""
    if len(stats) != len(SAMPLE_FRAMES):
        raise TimelineProbeError("Expected five evaluated frames from Blender timeline")
    if [item.get("frame") for item in stats] != list(SAMPLE_FRAMES):
        raise TimelineProbeError("Blender did not sample the pinned timeline frames")
    starting, middle, peak, leaving, ending = stats
    if any(
        item["evaluated_vertex_count"] != starting["evaluated_vertex_count"]
        for item in stats
    ):
        raise TimelineProbeError("Mesh topology changed while playing keyed animation")
    if ending["evaluated_sha256"] != starting["evaluated_sha256"]:
        raise TimelineProbeError("Animation did not return to its first-frame geometry")
    if peak["evaluated_sha256"] == starting["evaluated_sha256"]:
        raise TimelineProbeError("The keyed peak did not actually deform the mesh")
    if any(item["moved_vertices"] < MIN_MOVED for item in (middle, peak, leaving)):
        raise TimelineProbeError("Intermediate animation frames moved too few vertices")
    if any(
        item["evaluated_sha256"] in
        {starting["evaluated_sha256"], peak["evaluated_sha256"]}
        for item in (middle, leaving)
    ):
        raise TimelineProbeError("Frame sampling did not capture interpolated geometry")
    if max(starting["max_displacement_local"], ending["max_displacement_local"]) > RESTORE_TOLERANCE:
        raise TimelineProbeError("Neutral animation frames unexpectedly displaced vertices")


def verify_keyframed_timeline(bpy: Any, source: Path) -> dict[str, Any]:
    """Run a non-shipping original motion inside Blender without saving the master."""
    # The existing, real pose diagnostic also checks skin weights, finds a
    # genuinely deforming bone+axis and fully restores that transient pose.
    pose = probe_pose_deformation(bpy, source)
    bone_name = pose["selected_deform_bone"]
    axis = pose["rotation_axis_index"]
    humans = [x for x in bpy.data.objects
              if x.type == "MESH" and len(x.data.vertices) > 100]
    rigs = [x for x in bpy.data.objects if x.type == "ARMATURE"]
    if len(humans) != 1 or len(rigs) != 1:
        raise TimelineProbeError("Expected a single saved human and existing armature")
    human, rig = humans[0], rigs[0]
    current = rig.animation_data
    if current and (current.action or len(current.nla_tracks)):
        raise TimelineProbeError(
            "The saved armature already has animation; no diagnostic may overwrite it"
        )

    before = rig_fingerprint(bpy, human)
    if before["weight_sha256"] != pose["rig_weight_sha256"]:
        raise TimelineProbeError("Saved bone weight fingerprint changed before keyframing")

    scene = bpy.context.scene
    prior_frame = scene.frame_current
    prior_fps, prior_fps_base = scene.render.fps, scene.render.fps_base
    prior_position = rig.data.pose_position
    selected = rig.pose.bones[bone_name]
    prior_basis = selected.matrix_basis.copy()
    prior_mode = selected.rotation_mode
    created_action = None
    try:
        rig.data.pose_position = "POSE"
        scene.render.fps = FRAME_RATE
        scene.render.fps_base = 1.0
        scene.frame_set(KEYFRAMES[0])
        selected.rotation_mode = "XYZ"
        original_angles = list(selected.rotation_euler)
        from math import radians
        for frame in KEYFRAMES:
            angles = list(original_angles)
            if frame == KEYFRAMES[1]:
                angles[axis] += radians(ANGLE_DEGREES)
            for index, value in enumerate(angles):
                selected.rotation_euler[index] = value
            if selected.keyframe_insert(
                data_path="rotation_euler", frame=frame,
                group="UCC_DIAGNOSTIC_ONLY",
            ) is not True:
                raise TimelineProbeError("Blender failed to insert actual pose keyframes")

        animation = rig.animation_data
        if animation is None or animation.action is None:
            raise TimelineProbeError("Blender failed to create an assigned Action")
        created_action = animation.action
        neutral = None
        stats: list[dict[str, Any]] = []
        for frame in SAMPLE_FRAMES:
            # Crucially, no manual pose alteration happens between samples:
            # this reads Blender's genuine keyframed scene evaluation.
            scene.frame_set(frame)
            xyz, digest = _evaluated_vertices(bpy, human)
            if neutral is None:
                neutral = xyz
            moved, maximum = _movement(neutral, xyz)
            stats.append({
                "frame": frame,
                "evaluated_sha256": digest,
                "evaluated_vertex_count": len(xyz),
                "moved_vertices": moved,
                "max_displacement_local": maximum,
            })
        validate_timeline_frame_stats(stats)
        after = rig_fingerprint(bpy, human)
        if after != before:
            raise TimelineProbeError("Animation changed the underlying saved rig weights")
        return {
            "status": "REAL_BLENDER_KEYFRAMED_SKIN_TIMELINE_MEASURED",
            "selected_deform_bone": bone_name,
            "rotation_axis_index": axis,
            "rotation_degrees": ANGLE_DEGREES,
            "keyframes": list(KEYFRAMES),
            "sampled_frames": stats,
            "duration_seconds": 1.0,
            "fps": FRAME_RATE,
            "evaluated_vertex_count": stats[0]["evaluated_vertex_count"],
            "rig_bone_count": before["bone_count"],
            "rig_weight_sha256": before["weight_sha256"],
            "rig_rest_sha256": before["rig_rest_sha256"],
            "action_keyframes_inserted": 3,
            "action_assigned": True,
            "timeline_interpolation_evaluated": True,
            "source_master_saved": False,
            "original_animation_imported": False,
            "user_animation_playback_verified": False,
            "retargeting_verified": False,
            "engine_import_verified": False,
            "blender_version": bpy.app.version_string,
        }
    finally:
        # This is only a private in-memory diagnostic. It must never leave an
        # action or changed pose attached to the saved master.
        if rig.animation_data is not None and created_action is not None:
            rig.animation_data_clear()
            bpy.data.actions.remove(created_action, do_unlink=True)
        selected.rotation_mode = prior_mode
        selected.matrix_basis = prior_basis
        rig.data.pose_position = prior_position
        scene.render.fps, scene.render.fps_base = prior_fps, prior_fps_base
        scene.frame_set(prior_frame)
        bpy.context.view_layer.update()
