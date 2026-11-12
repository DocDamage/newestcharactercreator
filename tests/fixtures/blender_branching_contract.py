"""NON-SHIPPING synthetic Blender skin fixture. This is NOT MPFB/Fab evidence.

Run via Blender --background --factory-startup --disable-autoexec --python
this_file -- --output <unused-folder>. Exercises the real worker twice and
independently reopens all 25 frames. No network or external assets are used.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def create(output: Path) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    data = bpy.data.armatures.new("SYNTHETIC_CONTRACT_ONLY")
    rig = bpy.data.objects.new("SYNTHETIC_CONTRACT_ONLY", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    parents = [None, 0, 1, 2, 3, 2, 5, 0, 7, 8]
    heads = [(0, 0, 0), (0, 0, 1), (0, 0, 2), (1, 0, 2), (2, 0, 2),
             (-1, 0, 2), (-2, 0, 2), (0, 0, -1), (.5, 0, -2), (.5, 0, -3)]
    for i, parent in enumerate(parents):
        bone = data.edit_bones.new(f"Contract{i}")
        bone.head = heads[i]
        bone.tail = (heads[i][0], heads[i][1] + .3, heads[i][2] + .2)
        if parent is not None:
            bone.parent = data.edit_bones[f"Contract{parent}"]
        bone.roll = .1 * i
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = []
    for i, head in enumerate(heads):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=.13, location=head)
        piece = bpy.context.object
        group = piece.vertex_groups.new(name=f"Contract{i}")
        group.add(list(range(len(piece.data.vertices))), 1., "REPLACE")
        pieces.append(piece)
    bpy.ops.object.select_all(action="DESELECT")
    for piece in pieces:
        piece.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.object.join()
    human = bpy.context.object
    human.name = "SYNTHETIC_SKIN_CONTRACT_NOT_A_CHARACTER"
    modifier = human.modifiers.new("Actual Blender skinning contract", "ARMATURE")
    modifier.object = rig
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "synthetic.blend"), compress=False)
    from ci.branching_blender_fixture import author
    author(output / "synthetic.blend", output / "original-synthetic.bvh")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.exists():
        raise RuntimeError("Output must be a new private test directory")
    args.output.mkdir(parents=True)
    create(args.output)
    print("SYNTHETIC_BLENDER_CONTRACT_CREATED_NOT_MPFB")
