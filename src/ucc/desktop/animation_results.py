"""Plain-text, explicit-evidence summaries for local BVH Blender diagnostics.

No Qt, networking, asset copying or engine-ready certification is implied.
"""
from __future__ import annotations

from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck


def format_bvh_motion_evidence(result: LocalBvhClipCheck,
                               *, multibone: bool = False,
                               calibrated: bool = False,
                               reviewed: bool = False) -> str:
    data = result.evidence
    p = data
    lines = [
        ("REAL EXPLICITLY MAPPED BVH FULL-TIMELINE REVIEW IN BLENDER."
         if reviewed else
         "REAL REST-SPACE-CALIBRATED BVH ROTATIONS MEASURED IN BLENDER."
         if calibrated else
         "REAL 2–4 BONE BVH SOURCE CHAIN MEASURED IN BLENDER."
         if multibone else "REAL USER-SELECTED BVH SOURCE MOTION EVALUATED IN BLENDER."),
        f"Saved project revision: {result.revision}",
        f"Selected BVH clip: {result.clip_name}",
        f"Source SHA-256: {result.clip_sha256}",
        f"BVH source frames: {data['source_frame_count']}",
        f"Distinct skinned geometry states: {data['distinct_geometry_states']}",
    ]
    if calibrated:
        lines.extend([
            f"Explicit source up-axis: {data['axis_profile']}",
            f"Measured independent rest landmarks: {data['rest_landmark_count']}",
            f"Maximum landmark angular error: {data['max_rest_residual_degrees']:.4f}°",
            "Ordered source rotations were converted to target rest-bone axes",
            "using measured MPFB rest matrices, not direct Euler copying.",
            f"Mapped MPFB deform bones: {data['mapped_bone_count']}",
        ])
        for mapping, movement in zip(
            data["mapped_bones"], data["per_bone_deformation"]
        ):
            lines.append(
                f"{mapping['source']} → {mapping['target']} | "
                f"individual moved vertices {movement['moved_vertices']:,}"
            )
        lines.extend([
            "Two independent directional rest landmarks establish a shared basis.",
            "Per-bone Blender rest matrices are used to convert local rotations.",
            "Bone-roll quality on arbitrary external skeletons NOT independently certified.",
            "No user animation is imported or attached to the saved master.",
        ])
    elif multibone:
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
            ("Source/target rest-length ratio was measured; scale consistency "
             + ("checked across segments." if p["rest_scale_consistency_verified"] else
                "requires three or more mapped joints.")),
            "Bone roll and full local rotation bases were NOT calibrated.",
        ])
    else:
        lines.append(
            f"Mapped direct source bone: {data['source_bone']} → {data['target_bone']}"
        )
    if reviewed:
        lines.extend([
            f"Every frame measured: {len(data['full_timeline_frames'])}",
            f"Maximum adjacent skin step: {data['max_adjacent_mesh_step_local']:.6f}",
            f"Maximum quaternion step by bone: {data['max_bone_quaternion_step_degrees']}",
            f"Private Blender Action review copy: {result.private_visual_review_blend}",
            "Open that private .blend in Blender and inspect its full Action timeline.",
            "Joint twist and visual motion quality have NOT been manually approved.",
        ])
        mesh = data["mesh_edge_strain"]
        lines.extend([
            f"Evaluated skin edges measured: {mesh['measured_edge_count']:,} "
            f"({mesh['degenerate_baseline_edges_excluded']} degenerate baseline edges excluded)",
            f"Edge length ratios across all frames: "
            f"{min(f['min_edge_length_ratio'] for f in data['full_timeline_frames']):.4f}–"
            f"{max(f['max_edge_stretch_ratio'] for f in data['full_timeline_frames']):.4f}",
            "Target-rest local Y swing/twist maxima (generic bounds, not anatomical approval):",
        ])
        for joint in data["joint_motion_metrics"]:
            lines.append(f"{joint['bone']}: swing {joint['max_swing_degrees']:.3f}° "
                         f"at frame {joint['max_swing_frame']}, twist "
                         f"{joint['max_twist_degrees']:.3f}° at frame {joint['max_twist_frame']}")
        intake = data.get("source_rest_frame_intake")
        if intake is not None:
            lines.extend([
                f"Source rest-frame metadata validated: {intake['joint_count']} joints",
                f"Rest profile SHA-256: {intake['profile_sha256']}",
                "Rest metadata is validated; BVH channel-axis interpretation is unchanged.",
                "Supplied provenance and source roll are not independently certified.",
            ])
        conversion = data.get("source_frame_conversion")
        if conversion is not None:
            lines.extend([
                f"Audited channel-to-bone convention: {conversion['convention']}",
                f"Maximum basis roundtrip residual: {conversion['max_roundtrip_residual']:.3g}",
                f"Maximum target-equivalence residual: {conversion['max_target_equivalence_residual']:.3g}",
                "The coordinate change preserves existing first-frame-relative motion; it is not roll correction.",
            ])
        if data.get("private_review_renders") is not None:
            lines.extend([
                "15 private CPU clay images: five sampled frames, front/side/quarter views.",
                f"Private rendered review: {result.private_render_review}",
                "Open the local index and inspect each joint. Sampled renders do not grant visual approval.",
            ])
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
