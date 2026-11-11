"""Plain-text, explicit-evidence summaries for local BVH Blender diagnostics.

No Qt, networking, asset copying or engine-ready certification is implied.
"""
from __future__ import annotations

from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck


def format_bvh_motion_evidence(result: LocalBvhClipCheck,
                               *, multibone: bool = False) -> str:
    data = result.evidence
    lines = [
        ("REAL 2–4 BONE BVH SOURCE CHAIN MEASURED IN BLENDER."
         if multibone else "REAL USER-SELECTED BVH SOURCE MOTION EVALUATED IN BLENDER."),
        f"Saved project revision: {result.revision}",
        f"Selected BVH clip: {result.clip_name}",
        f"Source SHA-256: {result.clip_sha256}",
        f"BVH source frames: {data['source_frame_count']}",
        f"Distinct skinned geometry states: {data['distinct_geometry_states']}",
    ]
    if multibone:
        lines.extend([
            f"Explicit up-axis profile: {data['axis_profile']}",
            f"Mapped weighted bones: {data['mapped_bone_count']}",
        ])
        for bone, movement in zip(
            data["mapped_bones"], data["per_bone_deformation"]
        ):
            direction = bone["rest_alignment_cos"]
            lines.append(
                f"{bone['source']} → {bone['target']} | source parent "
                f"{bone['parent'] or '(source root)'} | "
                + (f"rest direction cosine {direction:.4f} | " if direction is not None else "")
                + f"solo moving vertices {movement['moved_vertices']:,}"
            )
        lines.extend([
            "Actual source/target parent links and rest DIRECTION were checked.",
            "Uniform source/target rest length scaling was checked, not applied.",
            "Bone roll and full local rotation bases were NOT calibrated.",
        ])
    else:
        lines.append(
            f"Mapped direct source bone: {data['source_bone']} → {data['target_bone']}"
        )
    lines.append("Measured real skinned vertices from Blender:")
    for row in data["sampled_frames"]:
        lines.append(
            f"Frame {row['frame']}: {row['moved_vertices']:,} moved vertices "
            f"(max {row['max_displacement_local']:.6f} Blender local units)"
        )
    lines.extend([
        "Two independent Blender processes agreed; original master/BVH unmodified.",
        "Permission is USER-ATTESTED for local Blender preview, not independently licensed.",
        "BVH position/root translation is ignored; motion is local rotation DELTAS only.",
        "NOT certified retargeting, visual quality, in-app animation playback",
        "or Godot/Unity/Unreal import. Saved geometry remains generated_unverified.",
    ])
    return "\n".join(lines)
