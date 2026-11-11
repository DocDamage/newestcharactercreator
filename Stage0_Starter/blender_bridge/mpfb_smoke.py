"""Runs *inside* Blender: validate real MPFB operation and save .blend.

Run through tools/run_mpfb_smoke.py. This does NOT install/enable MPFB.
The operator is documented by makehumancommunity/mpfb2 as mpfb.create_human.
It may require an interactive context in a particular Blender/MPFB pairing;
if so, the failure is a useful compatibility finding, not a fake pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    raw = sys.argv
    script_args = raw[raw.index("--") + 1:] if "--" in raw else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend", required=True)
    return parser.parse_args(script_args)


def create_human(blend_path: Path) -> dict:
    starting_mesh_ids = {obj.as_pointer() for obj in bpy.data.objects if obj.type == "MESH"}
    # Checking bpy.ops.mpfb.create_human is necessary but not sufficient:
    # the operator also needs an appropriate installed, enabled MPFB extension.
    try:
        create = bpy.ops.mpfb.create_human
        available = create.get_rna_type() is not None
    except Exception as error:
        raise RuntimeError("MPFB create_human operator unavailable; enable MPFB and retry") from error
    if not available:
        raise RuntimeError("MPFB operator is not registered")
    if not create.poll():
        raise RuntimeError("MPFB create_human.poll() is false in Blender background mode")
    operation = create()
    if "FINISHED" not in operation:
        raise RuntimeError(f"MPFB operator did not finish: {operation}")
    meshes = [obj for obj in bpy.data.objects
              if obj.type == "MESH" and obj.as_pointer() not in starting_mesh_ids]
    if not meshes or not any(len(obj.data.vertices) > 100 for obj in meshes):
        raise RuntimeError("Operator did not create a substantial humanoid mesh")
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    if not blend_path.is_file() or blend_path.stat().st_size == 0:
        raise RuntimeError(".blend save was not produced")
    return {
        "new_mesh_count": len(meshes),
        "new_mesh_vertices": [len(obj.data.vertices) for obj in meshes],
        "all_armatures": [obj.name for obj in bpy.data.objects if obj.type == "ARMATURE"],
        "shape_keys": {obj.name: [key.name for key in obj.data.shape_keys.key_blocks]
                       if obj.data.shape_keys else [] for obj in meshes},
        "output_blend": str(blend_path),
        "output_bytes": blend_path.stat().st_size,
    }


def main() -> None:
    args = parse_args()
    result_path = Path(args.output)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "error", "blender_version": bpy.app.version_string}
    try:
        result.update(create_human(Path(args.blend)))
        result["status"] = "ok"
    except Exception as error:
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()[-6000:]
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("UCC_SMOKE_RESULT=" + json.dumps({
        "status": result["status"], "output": str(result_path),
        "error": result.get("error")
    }))
    if result["status"] != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
