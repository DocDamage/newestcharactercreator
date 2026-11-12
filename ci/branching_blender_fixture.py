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
    # Exact MPFB default-rig names, verified from genuine CI bone inventory.
    # wrist.L/R are its hand-base deform bones; no invented hand.L/R aliases.
    endpoints = ("head", "wrist.L", "wrist.R", "foot.L", "foot.R")
    if all(rig.data.bones.get(name) is not None for name in endpoints):
        # Prioritize complete torso/head/arm/hand/leg/foot paths rather than
        # consuming the bounded map on toes before reaching distal arm joints.
        chosen = set()
        for name in endpoints:
            bone = rig.data.bones[name]
            while bone is not None:
                if bone.name not in eligible:
                    raise RuntimeError("Required body path contains an unweighted connector: " + bone.name)
                chosen.add(bone.name)
                bone = bone.parent
        if len(chosen) > 64:
            raise RuntimeError("Required body paths exceed the supported 64-bone map")
    ordered = [b for b in bones if b.name in chosen]  # BVH declaration/channel order
    if len(ordered) != len(chosen):
        raise RuntimeError("Required body endpoints do not belong to one weighted tree")
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
    from blender_bridge.bvh_review_timeline import evaluated_edges
    from blender_bridge.motion_quality import EdgeStrain, JointMotion, MotionQualityError
    from blender_bridge.pose_environment import validate_pose_environment
    hashes = []
    strain = None
    edge_frames = []
    joints = {p["target"]: JointMotion(p["target"]) for p in pairs}
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        points, digest = _evaluated_vertices(bpy, human)
        edges = evaluated_edges(bpy, human)
        if strain is None:
            strain = EdgeStrain(points, edges)
        edge_frames.append(strain.measure(points, edges, frame))
        hashes.append(digest)
        for name, tracker in joints.items():
            tracker.add(tuple(rig.pose.bones[name].rotation_quaternion), frame)
    if len(set(hashes)) < 3:
        raise RuntimeError("Reopened branching Action has no changing evaluated skin")
    # Private JSON allows the coordinator to compare ALL reopened frame hashes.
    master.with_suffix(".reopened.json").write_text(json.dumps(hashes), encoding="utf-8")
    master.with_suffix(".quality.json").write_text(json.dumps({
        "mesh_edge_strain": strain.report(), "edge_frames": edge_frames,
        "joint_motion_metrics": [tracker.report() for tracker in joints.values()],
    }), encoding="utf-8")
    # Fault injection stays in memory on an independently reopened PRIVATE copy.
    # The source review Action and original MPFB master are never saved here.
    bpy.context.scene.frame_set(1)
    before, before_hash = _evaluated_vertices(bpy, human)
    strain = EdgeStrain(before, evaluated_edges(bpy, human))
    edge = min(strain.active, key=lambda i: strain.lengths[i])
    a, b = strain.edges[edge]
    distorted = list(before)
    distorted[b] = tuple(before[a][i] + 5 * (before[b][i] - before[a][i]) for i in range(3))
    try:
        strain.measure(distorted, strain.edges, 2)
    except MotionQualityError:
        pass
    else:
        raise RuntimeError("Measured-skin snapshot accepted injected fivefold local edge stretch")
    from mathutils import Quaternion
    bone = rig.pose.bones[pairs[0]["target"]]
    prior = bone.rotation_quaternion.copy()
    try:
        bone.rotation_quaternion = Quaternion((0, 1, 0), math.radians(100))
        try:
            JointMotion(bone.name).add(tuple(bone.rotation_quaternion), 1)
        except MotionQualityError:
            pass
        else:
            raise RuntimeError("Actual Blender quaternion accepted injected excessive twist")
    finally:
        bone.rotation_quaternion = prior
    prior_scale = human.scale.copy()
    try:
        human.scale.x *= 2
        bpy.context.view_layer.update()
        try:
            validate_pose_environment(rig, human, [p["target"] for p in pairs])
        except MotionQualityError:
            pass
        else:
            raise RuntimeError("Actual target accepted injected nonuniform mesh scale")
    finally:
        human.scale = prior_scale
        bpy.context.view_layer.update()
    bpy.context.scene.frame_set(1)
    if _evaluated_vertices(bpy, human)[1] != before_hash:
        raise RuntimeError("Fault tests did not restore real evaluated skin")
    print("QUALITY_FAULTS_REJECTED_AND_PRIVATE_SKIN_RESTORED")
    print("BRANCHING_ACTION_REOPENED_ALL_25_SKINNED_FRAMES")


def reject_partial_action(master: Path, mapping: Path) -> None:
    from hashlib import sha256
    from blender_bridge.bvh_calibration_probe import calibrate_bvh_source
    from blender_bridge.motion_quality import MotionQualityError
    pairs = json.loads(mapping.read_text(encoding="utf-8"))
    source = mapping.with_suffix(".bvh")
    original = sha256(master.read_bytes()).hexdigest(), sha256(source.read_bytes()).hexdigest()
    lines = source.read_text(encoding="utf-8").splitlines()
    motion = lines.index("MOTION")
    # All component changes remain <=45 degrees, but the compound quaternion
    # jumps >80 degrees on frame 2, after frame-1 keys already created an Action.
    row = lines[motion + 4].split()
    row[:3] = ["45", "45", "45"]
    lines[motion + 4] = " ".join(row)
    jump = mapping.with_suffix(".jump.bvh")
    if jump.exists():
        raise RuntimeError("Refuse to overwrite fault source")
    jump.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = mapping.parent / "step-fault" / "review_motion.blend"
    output.parent.mkdir(exist_ok=False)
    try:
        calibrate_bvh_source(bpy, master, jump, "Y_UP_TO_Z_UP", pairs, output)
    except MotionQualityError as error:
        if "step=" not in str(error):
            raise
    else:
        raise RuntimeError("Genuine Blender accepted the injected quaternion step")
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    if (rig.animation_data and rig.animation_data.action) or output.exists():
        raise RuntimeError("Rejected motion retained a partial Action or review file")
    if any(abs(rig.pose.bones[p["target"]].matrix_basis[i][j] - float(i == j)) > 1e-4
           for p in pairs for i in range(4) for j in range(4)):
        raise RuntimeError("Rejected motion did not restore neutral target bone poses")
    if original != (sha256(master.read_bytes()).hexdigest(), sha256(source.read_bytes()).hexdigest()):
        raise RuntimeError("Rejected motion changed original files")
    print("STEP_FAULT_REJECTED_PARTIAL_ACTION_REMOVED_ORIGINALS_UNCHANGED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("create", "inspect", "reject-step"), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.mode == "create":
        author(args.blend, args.output)
    elif args.mode == "inspect":
        inspect(args.blend, args.output)
    else:
        reject_partial_action(args.blend, args.output)
