"""Blender-only native FBX rest/pose intake. Never converts channels to BVH."""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import struct
from typing import Any

CONVENTION = "BLENDER_FBX_ARMATURE_POSE_MATRICES_V1"
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_BONES, MAX_FRAMES, MAX_STATES = 256, 2400, 100_000
IMPORT_OPTIONS = {"use_anim": True, "anim_offset": 1., "use_image_search": False,
                  "use_custom_props": False, "automatic_bone_orientation": False,
                  "ignore_leaf_bones": False, "force_connect_children": False,
                  "use_prepost_rot": True, "bake_space_transform": False,
                  "use_manual_orientation": False, "global_scale": 1.}


class FbxSourceError(RuntimeError):
    """FBX cannot be represented without ambiguous or unsafe assumptions."""


def matrix_values(matrix: Any) -> list[float]:
    values = [float(matrix[i][j]) for i in range(4) for j in range(4)]
    if any(not math.isfinite(x) or abs(x) > 1e6 for x in values):
        raise FbxSourceError("FBX contains unbounded/nonfinite transforms")
    if max(abs(values[12+i] - (1. if i == 3 else 0.)) for i in range(4)) > 1e-6:
        raise FbxSourceError("FBX transform is not affine")
    # Reflected, collapsed or sheared source transforms are not repaired.
    columns = [[values[row*4+col] for row in range(3)] for col in range(3)]
    lengths = [math.sqrt(sum(x*x for x in c)) for c in columns]
    if any(not 1e-7 < v < 1e4 for v in lengths):
        raise FbxSourceError("Degenerate FBX transform")
    unit = [[x/lengths[i] for x in c] for i, c in enumerate(columns)]
    dot = lambda a, b: sum(x*y for x,y in zip(a,b))
    cross = [unit[1][1]*unit[2][2]-unit[1][2]*unit[2][1],
             unit[1][2]*unit[2][0]-unit[1][0]*unit[2][2],
             unit[1][0]*unit[2][1]-unit[1][1]*unit[2][0]]
    if dot(unit[0], cross) < .9999 or any(abs(dot(unit[i],unit[j])) > 1e-4 for i in range(3) for j in range(i)):
        raise FbxSourceError("Reflected or sheared FBX transform")
    return values


def pose_digest(world: list[float], poses: list[list[float]]) -> str:
    digest = sha256()
    for values in [world, *poses]:
        digest.update(struct.pack("<16q", *(round(v*1_000_000) for v in values)))
    return digest.hexdigest()


def inspect_fbx_source(bpy: Any, source: Path, output: Path, expected_sha: str) -> dict[str, Any]:
    if (source.is_symlink() or not source.is_file() or source.suffix.lower() != ".fbx" or
            not 0 < source.stat().st_size <= MAX_SOURCE_BYTES):
        raise FbxSourceError("Expected bounded regular staged FBX")
    original = sha256(source.read_bytes()).hexdigest()
    if original != expected_sha:
        raise FbxSourceError("FBX SHA-256 differs before import")
    if output.exists() or output.is_symlink():
        raise FbxSourceError("Refuse to overwrite source snapshot")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # `use_image_search=False` still loads explicit file references in Blender.
    # Fail before that loader can read external images; no search or placeholders.
    from bpy_extras import image_utils
    original_loader = image_utils.load_image
    def deny_images(*args, **kwargs):
        raise FbxSourceError("Skeleton intake does not load FBX image resources")
    image_utils.load_image = deny_images
    try:
        # Read the object bind transform with animation disabled. Frame 1 can
        # already carry hip/root motion and is not a trustworthy bind matrix.
        static_result = bpy.ops.import_scene.fbx(filepath=str(source), **{**IMPORT_OPTIONS,"use_anim":False})
        static_rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
        if static_result != {"FINISHED"} or len(static_rigs) != 1:
            raise FbxSourceError("FBX bind intake requires exactly one armature")
        static = static_rigs[0]
        rest_world = matrix_values(static.matrix_world)
        static_bones = {b.name: matrix_values(b.matrix_local) for b in static.data.bones}
        bpy.ops.wm.read_factory_settings(use_empty=True)
        result = bpy.ops.import_scene.fbx(filepath=str(source), **IMPORT_OPTIONS)
    finally:
        image_utils.load_image = original_loader
    if result != {"FINISHED"}:
        raise FbxSourceError("Blender FBX import did not finish")
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(rigs) != 1:
        raise FbxSourceError("FBX intake requires exactly one armature")
    rig = rigs[0]
    if static_bones != {b.name: matrix_values(b.matrix_local) for b in rig.data.bones}:
        raise FbxSourceError("FBX static bind and animated imports disagree on bone rest matrices")
    animation = rig.animation_data
    if (len(bpy.data.actions) != 1 or animation is None or animation.action is None or
            animation.action != bpy.data.actions[0] or len(animation.nla_tracks) or
            len(animation.drivers) or len(rig.constraints) or any(len(p.constraints) for p in rig.pose.bones)):
        raise FbxSourceError("FBX requires one unambiguous bound Action without NLA/drivers/constraints")
    action = animation.action
    start, end = (float(x) for x in action.frame_range)
    if (not all(math.isfinite(x) and abs(x-round(x)) < 1e-5 and abs(x) <= 100_000 for x in (start,end))):
        raise FbxSourceError("FBX Action needs bounded integral frame endpoints")
    first, last = round(start), round(end)
    frames, bones = last-first+1, list(rig.data.bones)
    if not 2 <= frames <= MAX_FRAMES or not 1 <= len(bones) <= MAX_BONES or frames*len(bones) > MAX_STATES:
        raise FbxSourceError("FBX full timeline exceeds frame/bone/state intake limits; no cropping performed")
    names = set()
    ordered = []
    pending = list(bones)
    while pending:
        ready = [b for b in pending if b.parent is None or b.parent.name in names]
        if not ready:
            raise FbxSourceError("FBX hierarchy is cyclic")
        for bone in ready:
            if (not 0 < len(bone.name) <= 128 or any(ord(c) < 32 for c in bone.name) or
                    bone.name.casefold() in {n.casefold() for n in names}):
                raise FbxSourceError("Unsafe or duplicate FBX bone name")
            names.add(bone.name)
            ordered.append(bone)
            pending.remove(bone)
    scene = bpy.context.scene
    rest = [{"name": b.name, "parent": b.parent.name if b.parent else None,
             "head": [float(x) for x in b.head_local], "tail": [float(x) for x in b.tail_local],
             "matrix": matrix_values(b.matrix_local)} for b in ordered]
    states = []
    for frame in range(first,last+1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        world = matrix_values(rig.matrix_world)
        poses = [matrix_values(rig.pose.bones[b.name].matrix) for b in ordered]
        states.append({"frame": frame, "armature_world": world, "poses": poses,
                       "pose_sha256": pose_digest(world, poses)})
    if len({r["pose_sha256"] for r in states}) < 2:
        raise FbxSourceError("FBX Action has no measured skeletal motion")
    snapshot = {"schema_version": 1, "convention": CONVENTION, "source_sha256": original,
                "blender_version": bpy.app.version_string, "import_options": IMPORT_OPTIONS,
                "rest_import_options": {**IMPORT_OPTIONS,"use_anim":False}, "armature_rest_world": rest_world,
                "action": action.name, "fps": scene.render.fps/scene.render.fps_base,
                "first_frame": first, "last_frame": last, "bones": rest, "frames": states,
                "retargeting_verified": False, "animation_visual_quality_verified": False,
                "engine_import_verified": False}
    payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise FbxSourceError("FBX pose snapshot exceeds private output limit")
    if sha256(source.read_bytes()).hexdigest() != original:
        raise FbxSourceError("FBX changed during import")
    with output.open("xb") as stream:
        stream.write(payload)
    return {"status": "REAL_BLENDER_FBX_SOURCE_SNAPSHOT", "convention": CONVENTION,
            "source_sha256": original, "bone_count": len(ordered), "root_count": sum(b.parent is None for b in ordered),
            "frame_count": frames, "first_frame": first, "last_frame": last, "fps": snapshot["fps"],
            "action": action.name, "blender_version": bpy.app.version_string,
            "snapshot": {"name": output.name, "bytes": len(payload), "sha256": sha256(payload).hexdigest()},
            "retargeting_verified": False, "animation_visual_quality_verified": False,
            "engine_import_verified": False}
