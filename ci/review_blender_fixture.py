#!/usr/bin/env python3
"""CI-only, self-authored motion from ACTUAL MPFB rest coordinates.

Nothing generated here is a licensed user clip or a production-quality motion
fixture. Creation and independent Blender review-Action reopen occur in separate
genuine Blender subprocesses; no private asset is committed or uploaded.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_offset(vector):
    """Inverse of the review's explicitly selected Y-up -> Blender Z-up."""
    return float(vector.x), float(vector.z), -float(vector.y)


def write_ci_fixture(master: Path, output: Path) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    rig = next(x for x in bpy.data.objects if x.type == "ARMATURE")
    target_names = ("neck02", "neck03", "head")
    bones = [rig.data.bones[name] for name in target_names]
    for i in (1, 2):
        if bones[i].parent != bones[i - 1] or not bones[i].use_deform:
            raise RuntimeError("The real MPFB 3-joint neck/head hierarchy differs")
    offsets = [(0.0, 0.0, 0.0)]
    for i in (1, 2):
        offsets.append(source_offset(bones[i].head_local - bones[i - 1].head_local))
    end_offset = source_offset(bones[-1].tail_local - bones[-1].head_local)
    if any(math.sqrt(sum(c*c for c in x)) < .000001 for x in offsets[1:] + [end_offset]):
        raise RuntimeError("Real Blender rig had a degenerate anatomical rest vector")
    src = ("UCC_Source_Neck02", "UCC_Source_Neck03", "UCC_Source_Head")
    def offset_line(values):
        return "OFFSET " + " ".join(f"{v:.9f}" for v in values)
    lines = ["HIERARCHY", f"ROOT {src[0]}", "{", offset_line(offsets[0]),
             "CHANNELS 3 Xrotation Yrotation Zrotation"]
    for i in (1, 2):
        lines.extend([f"JOINT {src[i]}", "{", offset_line(offsets[i]),
                      "CHANNELS 3 Xrotation Yrotation Zrotation"])
    lines.extend(["End Site", "{", offset_line(end_offset), "}", "}", "}", "}",
                  "MOTION", "Frames: 25", "Frame Time: 0.041666667"])
    for i in range(25):
        factor = math.sin(math.pi * i / 24.0)
        lines.append(" ".join(
            f"{a * factor:.7f} 0 0" for a in (9.0, 14.0, 19.0)
        ))
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("CI_REVIEW_SOURCE_AUTHORED_FROM_REAL_MPFB_REST_GEOMETRY")


def inspect_private_review(master: Path) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(rigs) != 1 or not rigs[0].animation_data:
        raise RuntimeError("Privately saved review lacks Blender armature/Action")
    action = rigs[0].animation_data.action
    if action is None:
        raise RuntimeError("Private review did not retain actual quaternion Action")
    start, end = [float(x) for x in action.frame_range]
    if start > 1.001 or end < 24.999:
        raise RuntimeError("Saved Blender Action frame range does not cover the source")
    for key in ("neck02", "neck03", "head"):
        bone = rigs[0].pose.bones.get(key)
        if bone is None or bone.rotation_mode != "QUATERNION":
            raise RuntimeError("Mapped MPFB quaternion bone missing from review Action")
    human = next(o for o in bpy.data.objects
                 if o.type == "MESH" and len(o.data.vertices) > 100)
    from blender_bridge.pose_deformation import _evaluated_vertices
    bpy.context.scene.frame_set(1)
    _, base = _evaluated_vertices(bpy, human)
    bpy.context.scene.frame_set(13)
    _, posed = _evaluated_vertices(bpy, human)
    if base == posed:
        raise RuntimeError("Independently reopened Action did not move skinned mesh")
    print("CI_REVIEWED_BLENDER_ACTION_REOPENED_WITH_REAL_SKIN_MOVEMENT")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("create", "inspect"), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if opts.mode == "create":
        if opts.output is None:
            raise RuntimeError("CI BVH output path missing")
        write_ci_fixture(opts.blend, opts.output)
    else:
        inspect_private_review(opts.blend)
