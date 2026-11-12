"""Author original NON-SHIPPING test motion from a genuine MPFB weighted tree.

This is structural/deformation test input, never proof of Fab compatibility or
natural movement. Only JSON diagnostics may leave the isolated CI workspace.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def author(master: Path, output: Path) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    human = next(o for o in bpy.data.objects if o.type == "MESH" and len(o.data.vertices) > 100)
    groups = {g.index: g.name for g in human.vertex_groups}
    counts = {b.name: 0 for b in rig.data.bones}
    for vertex in human.data.vertices:
        for weight in vertex.groups:
            name = groups.get(weight.group)
            if name in counts and weight.weight >= .1:
                counts[name] += 1
    eligible = {b.name for b in rig.data.bones if b.use_deform and counts[b.name] >= 16}

    def subtree(bone):
        if bone.name not in eligible:
            return []
        return [bone] + [b for child in sorted(bone.children, key=lambda b: b.name)
                         for b in subtree(child)]

    candidates = [subtree(b) for b in rig.data.bones if b.name in eligible]
    bones = max(candidates, key=len)
    if len(bones) < 9:
        raise RuntimeError("Real MPFB lacks a connected nine-bone weighted hierarchy")
    # Breadth first bounds the map while retaining proximal torso/limb branches.
    queue, selected = [bones[0]], []
    while queue and len(selected) < 48:
        bone = queue.pop(0)
        selected.append(bone)
        queue.extend(c for c in sorted(bone.children, key=lambda b: b.name) if c.name in eligible)
    chosen = {b.name for b in selected}
    ordered = [b for b in bones if b.name in chosen]  # BVH declaration/channel order
    if not any(sum(c.name in chosen for c in b.children) > 1 for b in ordered):
        raise RuntimeError("Real weighted hierarchy did not exercise any branching")
    sources = {b.name: f"CI_Source_{i:02}" for i, b in enumerate(ordered)}
    lines = ["HIERARCHY"]

    def offset(vector):
        # inverse of explicit Y-up to Z-up conversion
        return "OFFSET " + " ".join(f"{v:.9f}" for v in (vector.x, vector.z, -vector.y))

    def emit(bone, root=False):
        lines.extend([f'{"ROOT" if root else "JOINT"} {sources[bone.name]}', "{"])
        lines.append("OFFSET 0 0 0" if root else offset(bone.head_local - bone.parent.head_local))
        lines.append("CHANNELS 3 Xrotation Yrotation Zrotation")
        children = [b for b in sorted(bone.children, key=lambda b: b.name) if b.name in chosen]
        for child in children:
            emit(child)
        if not children:
            lines.extend(["End Site", "{", offset(bone.tail_local - bone.head_local), "}"])
        lines.append("}")

    emit(ordered[0], True)
    lines.extend(["MOTION", "Frames: 25", "Frame Time: 0.041666667"])
    for frame in range(25):
        factor = math.sin(math.pi * frame / 24)
        # Deliberately include static mapped joints; their independent skin probe
        # must still pass. Small multi-axis input prevents excessive accumulation.
        lines.append(" ".join(
            "0 0 0" if i % 5 == 0 else f"{(2 + i % 3)*factor:.7f} {factor:.7f} 0"
            for i in range(len(ordered))))
    if output.exists() or output.with_suffix(".json").exists():
        raise RuntimeError("Refuse to overwrite previous fixture evidence")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps([
        {"source": sources[b.name], "target": b.name} for b in ordered
    ], indent=2), encoding="utf-8")
    print("ORIGINAL_CI_BRANCHING_FIXTURE", len(ordered), "actual weighted rig bones")


def inspect(master: Path, mapping: Path) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False)
    pairs = json.loads(mapping.read_text(encoding="utf-8"))
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    action = rig.animation_data.action if rig.animation_data else None
    if action is None or tuple(action.frame_range) != (1., 25.):
        raise RuntimeError("Private branching Action missing or incomplete")
    if any(rig.pose.bones[p["target"]].rotation_mode != "QUATERNION" for p in pairs):
        raise RuntimeError("Mapped quaternion joint missing")
    human = next(o for o in bpy.data.objects if o.type == "MESH" and len(o.data.vertices) > 100)
    from blender_bridge.pose_deformation import _evaluated_vertices
    hashes = []
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        hashes.append(_evaluated_vertices(bpy, human)[1])
    if len(set(hashes)) < 3:
        raise RuntimeError("Reopened branching Action has no changing evaluated skin")
    # Private JSON allows the coordinator to compare ALL reopened frame hashes.
    master.with_suffix(".reopened.json").write_text(json.dumps(hashes), encoding="utf-8")
    print("BRANCHING_ACTION_REOPENED_ALL_25_SKINNED_FRAMES")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("create", "inspect"), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.mode == "create":
        author(args.blend, args.output)
    else:
        inspect(args.blend, args.output)
