"""Full-frame skinned-geometry diagnostics and private Blender visual-review copy.

Executed only after an explicit reviewed BVH map has passed real rest-space
calibration. Keeping an animated .blend in the PRIVATE job workspace makes
the Action inspectable in Blender; it is NOT an approval of visual quality.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
from typing import Any

from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.motion_quality import EdgeStrain


class ReviewTimelineError(RuntimeError):
    """Full timeline is discontinuous, extreme, or cannot be inspected safely."""


def evaluated_edges(bpy: Any, human: Any) -> tuple[tuple[int, int], ...]:
    evaluated = human.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    if mesh is None:
        raise ReviewTimelineError("No evaluated edge topology")
    try:
        if not 16 <= len(mesh.edges) <= 750000:
            raise ReviewTimelineError("Evaluated skin edge count outside safe bounds")
        return tuple(tuple(int(v) for v in edge.vertices) for edge in mesh.edges)
    finally:
        evaluated.to_mesh_clear()


def evaluate_review_timeline(bpy: Any, human: Any, rig: Any, frames: int,
                             review_path: Path) -> dict[str, Any]:
    scene = bpy.context.scene
    prior_start, prior_end = scene.frame_start, scene.frame_end
    prior_front = rig.show_in_front
    states: list[dict[str, Any]] = []
    before = previous = None
    diagonal = 0.0
    strain = None
    try:
        scene.frame_start, scene.frame_end = 1, frames
        for frame in range(1, frames + 1):
            scene.frame_set(frame)
            points, digest = _evaluated_vertices(bpy, human)
            edges = evaluated_edges(bpy, human)
            if before is None:
                before = points
                strain = EdgeStrain(points, edges)
                if len(strain.active) < 16:
                    raise ReviewTimelineError("Too few non-degenerate evaluated skin edges")
                mins = [min(x[i] for x in points) for i in range(3)]
                maxs = [max(x[i] for x in points) for i in range(3)]
                diagonal = math.sqrt(sum((a-b)**2 for a, b in zip(maxs, mins)))
                if not .01 < diagonal < 100000:
                    raise ReviewTimelineError("Invalid measured skinned-model bounding diagonal")
            moving, maximum = _movement(before, points)
            adjacent = _movement(previous, points)[1] if previous is not None else 0.0
            if maximum > diagonal * 1.5:
                raise ReviewTimelineError(f"Extreme evaluated deformation on frame {frame}")
            if adjacent > diagonal * .8:
                raise ReviewTimelineError(f"Sudden joint/mesh discontinuity on frame {frame}")
            states.append({
                "frame": frame, "evaluated_sha256": digest,
                "moved_vertices": moving,
                "max_displacement_local": maximum,
                "adjacent_max_displacement_local": adjacent,
                **strain.measure(points, edges, frame),
            })
            previous = points
        if (len({x["evaluated_sha256"] for x in states}) < 3 or
                sum(x["moved_vertices"] >= 16 for x in states[1:]) < 2):
            raise ReviewTimelineError("Full source timeline did not move actual skin")
        if review_path.name != "review_motion.blend" or review_path.is_symlink():
            raise ReviewTimelineError("Private review output must have a fixed safe filename")
        if review_path.exists():
            raise ReviewTimelineError("Refuse to overwrite a previous Blender review")
        # The exported COPY contains the temporary Action and all its source
        # keyframes. Only this job-local copy is user-reviewable; no master save.
        scene.frame_set(1)
        rig.show_in_front = True
        outcome = bpy.ops.wm.save_as_mainfile(
            filepath=str(review_path), compress=False, copy=True,
        )
        if "FINISHED" not in outcome or not review_path.is_file():
            raise ReviewTimelineError("Blender failed to write a private review Action copy")
        size = review_path.stat().st_size
        if not 10000 < size <= 512 * 1024 * 1024:
            raise ReviewTimelineError("Blender review copy has invalid size")
        h = sha256()
        with review_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return {
            "motion_quality_schema_version": 1,
            "mesh_edge_strain": strain.report(),
            "full_timeline_frames": states,
            "model_baseline_diagonal_local": diagonal,
            "max_adjacent_mesh_step_local": max(x["adjacent_max_displacement_local"]
                                                 for x in states),
            "visual_review_blend": {
                "name": review_path.name, "bytes": size, "sha256": h.hexdigest(),
            },
            "visual_review_artifact_created": True,
            "animation_visual_quality_verified": False,
            "joint_twist_visual_quality_verified": False,
        }
    finally:
        rig.show_in_front = prior_front
        scene.frame_start, scene.frame_end = prior_start, prior_end
